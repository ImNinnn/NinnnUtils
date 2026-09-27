"""Moderation: the _adm commands, warnings, automod (blocked words and sanctions) and the honeypot channel."""

import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Container, Modal, Section, Separator, TextDisplay, TextInput

import save
from utils.audit import add_bot_error_entry, send_audit_log
from utils.automod import (
    add_guild_warning,
    apply_warning_sanctions,
    find_blocked_word_match,
    get_automod_match_mode,
    get_guild_automod_config,
    get_guild_warnings,
    is_honeypot_channel,
    send_automod_channel_reply,
    send_warning_dm,
    set_warning_sanction_state,
    sync_guild_word_block_rule,
)
from utils.formatting import format_duration, format_user_reference, parse_duration_to_seconds
from utils.permissions import guild_owner_bypasses_role_checks, validate_role_selection
from utils.views import TimeoutDisabledLayoutView, TimeoutDisabledView

MAX_TIMEOUT_SECONDS = 28 * 86400
NUKE_GIF_URL = "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExN2x1ZW82ZGdlZzV1MTFzNGF6ajJzZ3Bmc3I2MDlxaXp0cWpkcTY4YyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/fXhYwggfsp3yHBsdlr/giphy.gif"


def _shorten(text, limit: int = 1024) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit - 3] + "..."


def resolve_member_from_input(guild: discord.Guild, member_input: str | discord.Member | discord.User | None) -> discord.Member | None:
    if not guild:
        return None

    if isinstance(member_input, discord.Member):
        return member_input

    if isinstance(member_input, discord.User):
        return guild.get_member(member_input.id)

    if not member_input:
        return None

    value = str(member_input).strip()
    if not value:
        return None

    if value.startswith("<@") and value.endswith(">"):
        value = value[2:-1].lstrip("!")

    if value.isdigit():
        return guild.get_member(int(value))

    return guild.get_member_named(value) or discord.utils.find(
        lambda member: member.name.lower() == value.lower() or member.display_name.lower() == value.lower(),
        guild.members,
    )


def bot_can_moderate(guild: discord.Guild, member: discord.Member, action: str | None = None) -> bool:
    """Whether Discord will let the bot act on this member (owner and role hierarchy)."""
    me = guild.me
    if me is None or member.id == guild.owner_id:
        return False
    # Discord refuses to time out administrators.
    if action == "timeout" and member.guild_permissions.administrator:
        return False
    return me.top_role > member.top_role


# ---------------------------------------------------------------- honeypot

async def send_honeypot_dm(member: discord.Member, guild: discord.Guild, channel: discord.abc.GuildChannel, sanction: str, message_preview: str) -> None:
    if member.bot:
        return

    title = "<:honey:1524116282075512842> Sent a message in a honeypot channel"
    description = f"**Server:** {guild.name}\n**Channel:** {getattr(channel, 'mention', str(channel.id))}\n**Action:** {sanction}"

    embed = discord.Embed(title=title, description=description, color=discord.Color.gold())
    embed.add_field(name="Message preview", value=message_preview, inline=False)

    try:
        await member.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def apply_honeypot_sanction(member: discord.Member | discord.User, guild: discord.Guild, channel: discord.abc.GuildChannel, message_content: str | None = None) -> bool:
    if member.bot or not guild or not isinstance(member, discord.Member):
        return False

    if not is_honeypot_channel(guild, channel):
        return False

    guild_config, _ = save.get_guild_config(str(guild.id))
    sanction = guild_config.get("honeypot_sanction") or {}
    action = str(sanction.get("action", "timeout")).lower()
    if action not in {"timeout", "kick", "ban"}:
        return False

    content_preview = (message_content or "").strip()
    if not content_preview:
        content_preview = "[no text content]"
    if len(content_preview) > 500:
        content_preview = content_preview[:497] + "..."

    duration_seconds = 0
    if action == "timeout":
        duration_seconds = min(max(1, int(sanction.get("duration_seconds", 86400) or 86400)), MAX_TIMEOUT_SECONDS)
        sanction_text = f"Timeout for {format_duration(duration_seconds)}"
    elif action == "kick":
        sanction_text = "Kick"
    else:
        sanction_text = "Ban"

    # Only tell the member about a sanction the bot can actually apply.
    can_sanction = bot_can_moderate(guild, member, action)
    if can_sanction:
        await send_honeypot_dm(member, guild, channel, sanction_text, content_preview)

    embed = discord.Embed(
        title="<:honey:1524116282075512842> Honeypot Triggered",
        color=discord.Color.gold()
    )
    embed.add_field(name="User", value=format_user_reference(member), inline=True)
    embed.add_field(name="Channel", value=channel.mention if hasattr(channel, 'mention') else str(channel), inline=True)
    embed.add_field(name="Action", value=action.title(), inline=True)
    embed.add_field(name="Message", value=content_preview or "*[Empty or Media]*", inline=False)
    embed.timestamp = datetime.now(timezone.utc)
    await send_audit_log(guild, "honeypot", embed=embed)

    if not can_sanction:
        return True

    try:
        if action == "timeout":
            timed_out_until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            await member.edit(timed_out_until=timed_out_until, reason="Sent a message in the honeypot channel")
        elif action == "kick":
            await member.kick(reason="Sent a message in the honeypot channel")
        elif action == "ban":
            await member.ban(reason="Sent a message in the honeypot channel")
    except (discord.Forbidden, discord.HTTPException) as error:
        add_bot_error_entry(guild.id, getattr(channel, "id", None), member, "honeypot sanction", error)

    return True


# ---------------------------------------------------------------- automod settings panel (opened from /settings)

class AutomodSettingsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.color = color
        self.build_components()

    def build_components(self):
        self.clear_items()
        automod, _ = get_guild_automod_config(self.guild_id)
        blocked_words = automod.get("blocked_words", [])
        warning_sanctions = automod.get("warning_sanctions", [])
        blocked_summary = "\n".join(
            f"- {item.get('phrase', '')}{' (custom regex)' if get_automod_match_mode(item) == 'custom_regex' else ' (regex)' if get_automod_match_mode(item) == 'generated_regex' else ''}"
            for item in blocked_words
        ) or "None"
        sanctions_summary = []
        for item in warning_sanctions:
            action = item.get('action', 'timeout')
            display = f"{item.get('warns')} warns -> {action}"
            if action == 'timeout':
                duration = item.get('duration') or f"{item.get('duration_seconds', 0)}s"
                display += f" ({duration})"
            sanctions_summary.append(display)
        sanctions_summary = "\n".join(sanctions_summary) or "None"

        self.word_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="automod_word_edit")
        self.sanctions_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="automod_sanctions_edit")
        self.word_button.callback = self.handle_word_edit
        self.sanctions_button.callback = self.handle_sanctions_edit

        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="automod_settings_back")
        self.back_button.callback = self.handle_back

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **Automod settings**"),
            TextDisplay("Manage blocked words and warning sanctions below."),
            Separator(),
            Section(f"<:warning:1517452174991556758> Blocked words\n{blocked_summary}", accessory=self.word_button),
            Section(f"<:warning:1517452174991556758> Warning sanctions\n{sanctions_summary}", accessory=self.sanctions_button),
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def handle_back(self, interaction: discord.Interaction):
        from cogs.settings import GuildSettingsMenuView  # imported here: cogs.settings imports this cog

        await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

    async def handle_word_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with blocked words?",
            view=AutomodWordChoiceView(self.user_id, self.guild_id, self.open_word_add, self.open_word_remove, settings_message),
            ephemeral=True,
        )

    async def open_word_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(AutomodWordAddModal(self.add_word_block, self.guild_id, settings_message))

    async def open_word_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(AutomodWordRemoveModal(self.remove_word_block, self.guild_id, settings_message))

    async def add_word_block(self, interaction: discord.Interaction, phrase: str, match_mode: str, warn_on_match: bool, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        automod.setdefault("blocked_words", []).append({"phrase": phrase, "match_mode": match_mode, "use_regex": match_mode != "word", "warn_on_match": warn_on_match})
        save.save_guild_data(data)
        await interaction.response.defer(ephemeral=True)
        await sync_guild_word_block_rule(interaction.guild)
        await interaction.followup.send("<:approve:1517452125687513158> Blocked phrase saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_word_block(self, interaction: discord.Interaction, phrase: str, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        blocked_words = automod.get("blocked_words", [])
        filtered = [item for item in blocked_words if str(item.get("phrase", "")).strip().lower() != phrase.strip().lower()]
        if len(filtered) != len(blocked_words):
            automod["blocked_words"] = filtered
            save.save_guild_data(data)
            await interaction.response.defer(ephemeral=True)
            await sync_guild_word_block_rule(interaction.guild)
            await interaction.followup.send("<:trash:1517497581058527404> Blocked phrase removed.", ephemeral=True)
            await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No matching blocked phrase was found.", ephemeral=True)

    async def handle_sanctions_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with warning sanctions?",
            view=AutomodSanctionChoiceView(self.user_id, self.guild_id, self.open_sanction_add, self.open_sanction_remove, settings_message),
            ephemeral=True,
        )

    async def open_sanction_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(AutomodSanctionAddModal(self.add_sanction_rule, self.guild_id, settings_message))

    async def open_sanction_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(AutomodSanctionRemoveModal(self.remove_sanction_rule, self.guild_id, settings_message))

    async def add_sanction_rule(self, interaction: discord.Interaction, warns: int, action: str, duration_seconds: int, duration_text: str, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        automod.setdefault("warning_sanctions", []).append({"warns": warns, "action": action, "duration_seconds": duration_seconds, "duration": duration_text})
        save.save_guild_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Warning sanction saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_sanction_rule(self, interaction: discord.Interaction, warns: int, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        sanctions = automod.get("warning_sanctions", [])
        filtered = [item for item in sanctions if int(item.get("warns", 0)) != warns]
        if len(filtered) != len(sanctions):
            automod["warning_sanctions"] = filtered
            save.save_guild_data(data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:trash:1517497581058527404> Warning sanction removed.", ephemeral=True)
            await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No matching warning sanction was found.", ephemeral=True)

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
        if settings_message is None:
            settings_message = interaction.message
            if settings_message is None:
                try:
                    settings_message = await interaction.original_response()
                except (discord.NotFound, discord.HTTPException):
                    settings_message = None
        if settings_message is None:
            return
        try:
            await settings_message.edit(view=view)
            return
        except (discord.NotFound, discord.HTTPException):
            pass
        try:
            await interaction.followup.edit_message(message_id=settings_message.id, view=view)
            return
        except Exception:
            pass
        try:
            await interaction.edit_original_response(view=view)
        except Exception:
            pass


class AutomodWordChoiceView(TimeoutDisabledView):
    def __init__(self, user_id: int, guild_id: str, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="automod_word_add")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="automod_word_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="automod_word_cancel")
        self.add_button.callback = self.add_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)


class AutomodWordAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add blocked phrase")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.phrase_input = TextInput(label="Word or phrase", placeholder="Enter a word, phrase, or regex", required=True, max_length=200)
        self.regex_input = TextInput(label="Regex? (false/true/is)", placeholder="false", required=True, max_length=10)
        self.warn_input = TextInput(label="Warn on match? (true/false)", placeholder="false", required=True, max_length=5)
        self.add_item(self.phrase_input)
        self.add_item(self.regex_input)
        self.add_item(self.warn_input)

    async def on_submit(self, interaction: discord.Interaction):
        def parse_mode(value: str) -> str:
            normalized = value.strip().lower()
            if normalized in {"is", "custom", "custom_regex", "raw_regex"}:
                return "custom_regex"
            if normalized in {"true", "regex", "generated", "generated_regex", "yes", "y", "1"}:
                return "generated_regex"
            return "word"

        def parse_bool(value: str) -> bool:
            return value.strip().lower() in {"true", "yes", "y", "1"}

        match_mode = parse_mode(self.regex_input.value)
        warn_on_match = parse_bool(self.warn_input.value)
        await self.callback(interaction, self.phrase_input.value.strip(), match_mode, warn_on_match, self.settings_message)


class AutomodWordRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove blocked phrase")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.phrase_input = TextInput(label="Word or phrase", placeholder="Enter the phrase to remove", required=True, max_length=200)
        self.add_item(self.phrase_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction, self.phrase_input.value.strip(), self.settings_message)


class AutomodSanctionChoiceView(TimeoutDisabledView):
    def __init__(self, user_id: int, guild_id: str, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="automod_sanction_add")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="automod_sanction_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="automod_sanction_cancel")
        self.add_button.callback = self.add_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)


class AutomodSanctionAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add warning sanction")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.warns_input = TextInput(label="Warn count", placeholder="5", required=True, max_length=10)
        self.action_input = TextInput(label="Action (timeout/kick/ban)", placeholder="timeout", required=True, max_length=20)
        self.duration_input = TextInput(label="Timeout duration (1d, 10s, 50m)", placeholder="1d", required=False, max_length=20)
        self.add_item(self.warns_input)
        self.add_item(self.action_input)
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            warns = int(self.warns_input.value)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Warn count must be a number.", ephemeral=True)
            return

        action = self.action_input.value.strip().lower()
        if action not in {"timeout", "kick", "ban"}:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Action must be timeout, kick, or ban.", ephemeral=True)
            return

        duration_text = self.duration_input.value.strip() if self.duration_input.value else ""
        duration_seconds = None
        if action == "timeout":
            if not duration_text:
                duration_text = "1d"
            duration_seconds = parse_duration_to_seconds(duration_text)
            if duration_seconds is None or duration_seconds <= 0:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Timeout duration must be a valid value like 1d, 10s, or 50m.", ephemeral=True)
                return
        else:
            duration_seconds = 0
            if duration_text:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Duration is only valid for timeout actions.", ephemeral=True)
                return

        await self.callback(interaction, warns, action, duration_seconds, duration_text, self.settings_message)


class AutomodSanctionRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove warning sanction")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.warns_input = TextInput(label="Warn count", placeholder="5", required=True, max_length=10)
        self.add_item(self.warns_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            warns = int(self.warns_input.value)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Warn count must be a number.", ephemeral=True)
            return
        await self.callback(interaction, warns, self.settings_message)


# ---------------------------------------------------------------- cog

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._background_tasks: set[asyncio.Task] = set()

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def cog_unload(self):
        for task in list(self._background_tasks):
            task.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not is_honeypot_channel(message.guild, message.channel):
            return

        # Message.delete() takes no audit-log reason. Delete first so the message goes away right away.
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass
        await apply_honeypot_sanction(message.author, message.guild, message.channel, message.content)

    @commands.Cog.listener()
    async def on_automod_action(self, action: discord.AutoModAction) -> None:
        guild = action.guild
        if guild is None:
            return

        automod, _ = get_guild_automod_config(str(guild.id))
        blocked_rule_ids = set()
        for rule_id in list(automod.get("blocked_rule_ids", []) or []) + [automod.get("blocked_rule_id")]:
            try:
                if rule_id is not None:
                    blocked_rule_ids.add(int(rule_id))
            except (TypeError, ValueError):
                pass

        if action.rule_id not in blocked_rule_ids:
            return

        text = action.matched_content or action.matched_keyword or action.content or ""
        if not text:
            return

        # Check the full message first: matched_content is only the matched part.
        matched_entry = find_blocked_word_match(automod, action.content or "") or find_blocked_word_match(automod, text)
        should_warn = bool(matched_entry and matched_entry.get("warn_on_match", False))

        member_id = action.user_id
        warnings = None
        sanction_text = None
        if should_warn:
            warnings, _ = await add_guild_warning(str(guild.id), member_id, f"Discord AutoMod blocked a message via rule {action.rule_id}", moderator_id=None, moderator_name="Discord AutoMod")

        member = action.member or guild.get_member(member_id)
        if member is None:
            try:
                member = await guild.fetch_member(member_id)
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                member = None

        if member is not None and not member.bot and should_warn:
            sanction_text = await apply_warning_sanctions(member, guild, len(warnings))
            await send_warning_dm(
                member,
                guild,
                "Discord AutoMod blocked a message",
                total_warnings=len(warnings),
                automod_triggered=True,
                sanction=sanction_text
            )

        await send_automod_channel_reply(
            action.channel,
            member,
            member_id,
            "Discord AutoMod blocked a message",
            sanction=sanction_text,
            warning_given=should_warn,
            total_warnings=len(warnings) if warnings is not None else None,
        )

    @app_commands.command(name='purge_adm', description='Mass delete messages from the channel')
    @app_commands.describe(amount='Number of messages to remove', user='Optional user filter')
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def purge_adm(self, interaction: discord.Interaction, amount: int, user: discord.Member | None = None):
        if amount <= 0:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please specify a number greater than 0.", ephemeral=True)
            return
        if amount > 100:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:warning:1517452174991556758> For safety, you can only purge up to 100 messages at a time.", ephemeral=True)
            return
        if interaction.guild is None or not hasattr(interaction.channel, "purge"):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please run this in a text channel.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        def is_user(m):
            return m.author == user if user else True

        try:
            deleted = await interaction.channel.purge(
                limit=amount,
                check=is_user,
                before=interaction.created_at,
                reason=f"Purged by {interaction.user} via bot"
            )
            user_str = f" from {format_user_reference(user)}" if user else ""
            await interaction.followup.send(f"<:explosive:1517578642723573880> Successfully deleted **{len(deleted)}** messages{user_str}.", ephemeral=False)
        except Exception as e:
            await interaction.followup.send(_shorten(f"<:disapprove:1517452151012589662> Failed to purge messages. Error: {e}", 2000), ephemeral=True)

    @app_commands.command(name='timeout_adm', description='Timeout a member for a specific duration')
    @app_commands.describe(member='Member to timeout', days='Days', hours='Hours', minutes='Minutes', seconds='Seconds', reason='Reason')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def timeout_adm(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        reason: str = 'No reason provided',
    ):
        try:
            duration = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        except OverflowError:
            duration = timedelta(days=29)
        if duration.total_seconds() <= 0:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You must specify a duration greater than 0!", ephemeral=True)
            return
        if duration.total_seconds() > MAX_TIMEOUT_SECONDS:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Timeout cannot exceed 28 days.", ephemeral=True)
            return

        target_member = resolve_member_from_input(interaction.guild, member)
        if target_member is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't find that user in this server.", ephemeral=True)
            return

        if target_member == interaction.user:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot timeout yourself.", ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(interaction) and interaction.user != target_member and target_member.top_role >= interaction.user.top_role:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot timeout someone with an equal or higher role than yours.", ephemeral=True)
            return

        # Checked before the DM so the member is not told about a timeout that Discord will refuse.
        if not bot_can_moderate(interaction.guild, target_member, "timeout"):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to timeout this user (Hierarchy issue).", ephemeral=True)
            return

        time_str = f"{days}d {hours}h {minutes}m {seconds}s"
        if not target_member.bot:
            try:
                dm_embed = discord.Embed(
                    title="<:hourglass:1517574046252924938> You have been timed out",
                    description=_shorten(f"**Server:** {interaction.guild.name}\n**Duration:** {time_str}\n**Reason:** {reason}", 4096),
                    color=discord.Color.orange()
                )
                await target_member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            await target_member.timeout(duration, reason=reason[:512])
            confirm_embed = discord.Embed(
                title="<:approve:1517452125687513158> User Timed Out",
                description=f"**{format_user_reference(target_member)}** has been timed out for {time_str}.",
                color=discord.Color.green()
            )
            confirm_embed.add_field(name="Reason", value=_shorten(reason))
            await interaction.response.defer(); await interaction.followup.send(embed=confirm_embed)
        except discord.Forbidden:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to timeout this user (Hierarchy issue).", ephemeral=True)
        except Exception as e:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(_shorten(f"<:disapprove:1517452151012589662> An error occurred: {e}", 2000), ephemeral=True)

    @app_commands.command(name='slowmode_adm', description='Set channel slowmode (up to 6 hours)')
    @app_commands.describe(seconds='Seconds', minutes='Minutes', hours='Hours', channel='Channel to update')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def slowmode_adm(
        self,
        interaction: discord.Interaction,
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
        channel: discord.TextChannel | None = None,
    ):
        total_seconds = int(seconds or 0) + int(minutes or 0) * 60 + int(hours or 0) * 3600

        if total_seconds < 0:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid slowmode value.", ephemeral=True)
            return
        if total_seconds > 21600:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Slowmode cannot exceed 6 hours.", ephemeral=True)
            return

        target_channel = channel or interaction.channel
        if target_channel is None or not isinstance(target_channel, discord.TextChannel):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please run this in a text channel or specify a valid text channel.", ephemeral=True)
            return

        try:
            await target_channel.edit(slowmode_delay=total_seconds, reason=f"Set by {interaction.user}")
            if total_seconds == 0:
                desc = f"Disabled slowmode in {target_channel.mention}."
            else:
                desc = f"Set slowmode in {target_channel.mention} to {format_duration(total_seconds)}."
            embed = discord.Embed(title="<:approve:1517452125687513158> Slowmode updated", description=desc, color=discord.Color.green())
            await interaction.response.defer(); await interaction.followup.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to edit this channel.", ephemeral=True)
        except Exception as e:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(_shorten(f"<:disapprove:1517452151012589662> An error occurred: {e}", 2000), ephemeral=True)

    @app_commands.command(name='kick_adm', description='Kick a member from the server')
    @app_commands.describe(member='Member to kick', reason='Kick reason')
    @app_commands.default_permissions(kick_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def kick_adm(self, interaction: discord.Interaction, member: discord.Member | None = None, reason: str = 'No reason provided'):
        target_member = resolve_member_from_input(interaction.guild, member)
        if target_member is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't find that user in this server.", ephemeral=True)
            return

        if target_member == interaction.user:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot kick yourself.", ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(interaction) and interaction.user != target_member and target_member.top_role >= interaction.user.top_role:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot kick someone with an equal or higher role than yours.", ephemeral=True)
            return

        if not bot_can_moderate(interaction.guild, target_member):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to kick this user (Hierarchy issue).", ephemeral=True)
            return

        if not target_member.bot:
            try:
                dm_embed = discord.Embed(
                    title="<:warning:1517452174991556758> You have been kicked",
                    description=_shorten(f"**Server:** {interaction.guild.name}\n**Reason:** {reason}", 4096),
                    color=discord.Color.orange()
                )
                await target_member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            await target_member.kick(reason=reason[:512])
            confirm_embed = discord.Embed(
                title="<:approve:1517452125687513158> User Kicked",
                description=f"**{format_user_reference(target_member)}** has been kicked from the server.",
                color=discord.Color.green()
            )
            confirm_embed.add_field(name="Reason", value=_shorten(reason))
            await interaction.response.defer(); await interaction.followup.send(embed=confirm_embed)
        except discord.Forbidden:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to kick this user (Hierarchy issue).", ephemeral=True)
        except Exception as e:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(_shorten(f"<:disapprove:1517452151012589662> An error occurred: {e}", 2000), ephemeral=True)

    @app_commands.command(name='ban_adm', description='Ban a member from the server')
    @app_commands.describe(member='Member to ban', reason='Ban reason', delete_days='Messages to delete from the past x days')
    @app_commands.default_permissions(ban_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def ban_adm(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        reason: str = 'No reason provided',
        delete_days: int = 0,
    ):
        if delete_days < 0 or delete_days > 7:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Delete days must be between 0 and 7.", ephemeral=True)
            return

        target_member = resolve_member_from_input(interaction.guild, member)
        if target_member is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't find that user in this server.", ephemeral=True)
            return

        if target_member == interaction.user:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot ban yourself.", ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(interaction) and interaction.user != target_member and target_member.top_role >= interaction.user.top_role:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot ban someone with an equal or higher role than yours.", ephemeral=True)
            return

        if not bot_can_moderate(interaction.guild, target_member):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to ban this user (Hierarchy issue).", ephemeral=True)
            return

        if not target_member.bot:
            try:
                dm_embed = discord.Embed(
                    title="<:disapprove:1517452151012589662> You have been banned",
                    description=_shorten(f"**Server:** {interaction.guild.name}\n**Reason:** {reason}", 4096),
                    color=discord.Color.red()
                )
                await target_member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            await target_member.ban(reason=reason[:512], delete_message_seconds=delete_days * 86400)
            confirm_embed = discord.Embed(
                title="<:approve:1517452125687513158> User Banned",
                description=f"**{format_user_reference(target_member)}** has been banned from the server.",
                color=discord.Color.green()
            )
            confirm_embed.add_field(name="Reason", value=_shorten(reason))
            if delete_days > 0:
                confirm_embed.add_field(name="Deleted Messages", value=f"{delete_days} day(s)", inline=True)
            await interaction.response.defer(); await interaction.followup.send(embed=confirm_embed)
        except discord.Forbidden:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to ban this user (Hierarchy issue).", ephemeral=True)
        except Exception as e:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(_shorten(f"<:disapprove:1517452151012589662> An error occurred: {e}", 2000), ephemeral=True)

    @app_commands.command(name='warn_adm', description='Add or remove a warning for a user')
    @app_commands.describe(user='User to warn', reason='Warning reason', remove='Remove a warning instead of adding one')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def warn_adm(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = 'No reason provided',
        remove: bool = False,
    ):
        member = user
        if member == interaction.user:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot warn yourself.", ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(interaction) and member.top_role >= interaction.user.top_role:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot manage warnings for someone with an equal or higher role than yours.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        if not remove:
            warnings, _ = await add_guild_warning(
                guild_id,
                member.id,
                reason,
                moderator_id=interaction.user.id,
                moderator_name=str(interaction.user),
            )
            # Sanctions and DMs can take a while; answer first so the interaction cannot expire.
            await interaction.response.defer()

            total = len(warnings)
            sanction_text = await apply_warning_sanctions(member, interaction.guild, total)

            if not member.bot:
                await send_warning_dm(
                    member,
                    interaction.guild,
                    reason,
                    total_warnings=total,
                    sanction=sanction_text
                )

            confirm_embed = discord.Embed(
                title="<:warning:1517452174991556758> Warning added",
                description=f"**{format_user_reference(member)}** has been warned.",
                color=discord.Color.yellow()
            )
            confirm_embed.add_field(name="Reason", value=_shorten(reason), inline=False)
            confirm_embed.add_field(name="Total warnings", value=str(total), inline=False)
            if sanction_text:
                confirm_embed.add_field(name="Sanction", value=sanction_text, inline=True)
            await interaction.followup.send(embed=confirm_embed)
            return

        user_warnings, data = get_guild_warnings(guild_id, member.id)
        if not user_warnings:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> **{format_user_reference(member)}** has no warnings to remove.", ephemeral=True)
            return

        removed = user_warnings.pop()
        save.save_guild_data(data)
        set_warning_sanction_state(guild_id, member.id, len(user_warnings))
        await interaction.response.defer()

        if not member.bot:
            try:
                dm_embed = discord.Embed(
                    title="<:warning:1517452174991556758> A warning has been removed",
                    description=_shorten(f"**Server:** {interaction.guild.name}\n**Note:** {reason}", 4096),
                    color=discord.Color.green()
                )
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        total = len(user_warnings)
        confirm_embed = discord.Embed(
            title="<:warning:1517452174991556758> Warning removed",
            description=f"A warning has been removed from **{format_user_reference(member)}**.",
            color=discord.Color.green()
        )
        confirm_embed.add_field(name="Removed warning reason", value=_shorten(removed.get("reason", "No reason provided")), inline=False)
        confirm_embed.add_field(name="Note", value=_shorten(reason), inline=False)
        confirm_embed.add_field(name="Remaining warnings", value=str(total), inline=True)
        await interaction.followup.send(embed=confirm_embed)

    @app_commands.command(name='warns_adm', description='Show warnings for a user')
    @app_commands.describe(user='User to inspect')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def warns_adm(self, interaction: discord.Interaction, user: discord.Member):
        member = user
        if member == interaction.user:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot view warnings for yourself with this command.", ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(interaction) and member.top_role >= interaction.user.top_role:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot view warnings for someone with an equal or higher role than yours.", ephemeral=True)
            return

        user_warnings, _ = get_guild_warnings(str(interaction.guild.id), member.id)
        if not user_warnings:
            await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> **{format_user_reference(member)}** has no warnings.", ephemeral=False)
            return

        embed = discord.Embed(
            title=f"Warnings for {member.display_name}",
            description=f"Total warnings: **{len(user_warnings)}**",
            color=discord.Color.orange()
        )

        for index, warn_entry in enumerate(user_warnings[-10:], start=max(1, len(user_warnings) - 9)):
            raw_timestamp = warn_entry.get("timestamp")
            timestamp = "Unknown time"
            if raw_timestamp:
                try:
                    dt = datetime.fromisoformat(raw_timestamp)
                    timestamp = discord.utils.format_dt(dt, style="f")
                except Exception:
                    timestamp = raw_timestamp
            reason = warn_entry.get("reason", "No reason provided")
            moderator = warn_entry.get("moderator_name", "Unknown moderator")
            # 10 fields must stay under the 6000 character embed limit.
            embed.add_field(
                name=f"Warn {index}",
                value=f"**Reason:** {_shorten(reason, 400)}\n**Moderator:** {moderator}\n**Time:** {timestamp}",
                inline=False
            )

        if len(user_warnings) > 10:
            embed.set_footer(text=f"Showing the last 10 of {len(user_warnings)} warnings")

        await interaction.response.defer(); await interaction.followup.send(embed=embed, ephemeral=False)

    @app_commands.command(name='voice-move_adm', description='Move a member to another voice channel')
    @app_commands.describe(channel='Voice channel to move the user to')
    @app_commands.default_permissions(move_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def voice_move_adm(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        member = interaction.user
        if not isinstance(member, discord.Member) and interaction.guild is not None:
            member = interaction.guild.get_member(interaction.user.id)

        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You must be connected to a voice channel to use this command.", ephemeral=True)
            return

        source_channel = member.voice.channel
        if source_channel.id == channel.id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> You are already in the target voice channel.", ephemeral=True)
            return

        # Moving many members takes longer than the 3 second interaction window.
        await interaction.response.defer()

        moved_members = []
        failed_members = []
        for target_member in list(source_channel.members):
            try:
                await target_member.move_to(channel, reason=f"Voice move initiated by {interaction.user}")
                moved_members.append(target_member.display_name)
            except Exception as e:
                failed_members.append(f"{target_member.display_name}: {e}")

        embed = discord.Embed(
            title="Voice Move Complete",
            description=f"Moved {len(moved_members)} user(s) from **{source_channel.name}** to **{channel.name}**.",
            color=discord.Color.blurple()
        )
        if moved_members:
            embed.add_field(name="Moved", value=_shorten("\n".join(moved_members[:25])), inline=False)
        if failed_members:
            embed.add_field(name="Failed", value=_shorten("\n".join(failed_members[:25])), inline=False)
        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name='rename_adm', description='Rename a user or reset their nickname')
    @app_commands.describe(user='User to rename', name='New nickname to set (leave empty to reset)')
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def rename_adm(self, interaction: discord.Interaction, user: discord.Member, name: str | None = None):
        if interaction.guild.me.top_role <= user.top_role:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I cannot rename this user. Their role is higher than or equal to mine!", ephemeral=True)
            return
        # The bot renames on the moderator's behalf, so enforce the moderator's own hierarchy too.
        if not guild_owner_bypasses_role_checks(interaction) and interaction.user != user and user.top_role >= interaction.user.top_role:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot rename someone with an equal or higher role than yours.", ephemeral=True)
            return
        try:
            old_name = user.display_name
            await user.edit(nick=name)
            if name:
                await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Changed **{old_name}**'s nickname to **{name}**.")
            else:
                await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Reset **{old_name}**'s nickname to their original username.")
        except discord.Forbidden:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have the 'Manage Nicknames' permission or the user is the Server Owner.", ephemeral=True)
        except Exception as e:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(_shorten(f"<:disapprove:1517452151012589662> An error occurred: {e}", 2000), ephemeral=True)

    @app_commands.command(name='purge-nuke_adm', description='Fully clear a channel')
    @app_commands.describe(archive='Archive the channel before deleting it')
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def purge_nuke_adm(self, interaction: discord.Interaction, archive: bool = False):
        try:
            channel = await interaction.guild.fetch_channel(interaction.channel_id)
        except discord.Forbidden:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I cannot 'see' this channel. Please check my permissions in this specific channel's settings.", ephemeral=True)
            return

        await interaction.response.defer(); await interaction.followup.send("<:explosive:1517578642723573880> Target locked. Nuking...", ephemeral=False)
        try:
            new_channel = await channel.clone(reason=f"Nuke by {interaction.user}")
            await new_channel.edit(position=channel.position)
        except (AttributeError, discord.Forbidden, discord.HTTPException) as error:
            add_bot_error_entry(interaction.guild.id, channel.id, interaction.user, "nuke clone", error)
            try:
                await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't recreate this channel. Please check my Manage Channels permission.", ephemeral=True)
            except (discord.NotFound, discord.HTTPException):
                pass
            return

        embed = discord.Embed(
            title="<:nuke:1517497573986926732> Channel Nuked",
            description=f"This is {format_user_reference(interaction.user)}'s fault, THEY DID THIS",
            color=discord.Color.red()
        )
        embed.set_image(url=NUKE_GIF_URL)
        try:
            await new_channel.send(embed=embed)
        except discord.Forbidden as error:
            add_bot_error_entry(interaction.guild.id, new_channel.id, interaction.user, "nuke result message", error)

        try:
            if archive:
                everyone_role = interaction.guild.default_role
                await channel.edit(
                    name=f"{channel.name}-archived",
                    overwrites={everyone_role: discord.PermissionOverwrite(view_channel=False)},
                    reason="Channel Archived via Nuke"
                )
            else:
                await channel.delete(reason="Nuked")
        except discord.Forbidden:
            try:
                await new_channel.send("<:warning:1517452174991556758> **Warning:** I couldn't delete or hide the old channel. Check if my role is high enough!")
            except discord.Forbidden as error:
                add_bot_error_entry(interaction.guild.id, new_channel.id, interaction.user, "nuke cleanup warning", error)
        except Exception as e:
            print(f"Error during nuke cleanup: {e}")

    @app_commands.command(name='role_adm', description='Give or remove a role from a user')
    @app_commands.describe(action='Whether to add or remove the role', member='Member to update', role='Role to add or remove', reason='Reason for this role change')
    @app_commands.choices(action=[app_commands.Choice(name='Add', value='add'), app_commands.Choice(name='Remove', value='remove')])
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def role_adm(self, interaction: discord.Interaction, action: str, member: discord.Member, role: discord.Role, reason: str = 'No reason provided'):
        role_error = validate_role_selection(interaction, role, "role")
        if role_error:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(role_error, ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(interaction) and interaction.user != member and member.top_role >= interaction.user.top_role:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot modify the roles of someone with an equal or higher role than yours.", ephemeral=True)
            return

        audit_reason = f"Role admin by {interaction.user} - {reason}"[:512]
        try:
            if action == "add":
                if role in member.roles:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:warning:1517452174991556758> **{format_user_reference(member)}** already has **{role.name}**.", ephemeral=True)
                    return
                await member.add_roles(role, reason=audit_reason)
                await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Added **{role.name}** to **{format_user_reference(member)}**.", ephemeral=False)
            else:
                if role not in member.roles:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:warning:1517452174991556758> **{format_user_reference(member)}** does not have **{role.name}**.", ephemeral=True)
                    return
                await member.remove_roles(role, reason=audit_reason)
                await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Removed **{role.name}** from **{format_user_reference(member)}**.", ephemeral=False)
        except discord.Forbidden:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).", ephemeral=True)
        except Exception as e:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(_shorten(f"<:disapprove:1517452151012589662> An error occurred: {e}", 2000), ephemeral=True)

    @app_commands.command(name='temp-role_adm', description='Grant or remove a temporary role from a user')
    @app_commands.describe(action='Whether to grant or remove the temporary role', member='The user to update', role='The temporary role to grant or remove', duration='How long the temporary role should last (for example 30m, 2h, 1d)', reason='Why this temporary role change is being made')
    @app_commands.choices(action=[app_commands.Choice(name='Grant', value='grant'), app_commands.Choice(name='Remove', value='remove')])
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def temp_role_adm(self, interaction: discord.Interaction, action: str, member: discord.Member, role: discord.Role, duration: str | None = None, reason: str = 'No reason provided'):
        role_error = validate_role_selection(interaction, role, "temporary role")
        if role_error:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(role_error, ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(interaction) and interaction.user != member and member.top_role >= interaction.user.top_role:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot modify the roles of someone with an equal or higher role than yours.", ephemeral=True)
            return

        if action == "grant":
            if not duration:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide a duration like 30m, 2h, or 1d.", ephemeral=True)
                return

            duration_seconds = parse_duration_to_seconds(duration)
            if duration_seconds is None or duration_seconds <= 0:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide a valid duration like 30m, 2h, or 1d.", ephemeral=True)
                return

            try:
                if role in member.roles:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:warning:1517452174991556758> **{format_user_reference(member)}** already has **{role.name}**.", ephemeral=True)
                    return
                await member.add_roles(role, reason=f"Temporary role admin by {interaction.user} - {reason}"[:512])

                async def remove_temp_role():
                    await asyncio.sleep(duration_seconds)
                    try:
                        await member.remove_roles(role, reason=f"Temporary role expired after {duration} (admin command)"[:512])
                    except (discord.Forbidden, discord.HTTPException):
                        pass

                self._spawn(remove_temp_role())
                await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Granted **{role.name}** to **{format_user_reference(member)}** for {duration}.", ephemeral=False)
            except discord.Forbidden:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).", ephemeral=True)
            except Exception as e:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(_shorten(f"<:disapprove:1517452151012589662> An error occurred: {e}", 2000), ephemeral=True)
            return

        try:
            if role not in member.roles:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:warning:1517452174991556758> **{format_user_reference(member)}** does not have **{role.name}**.", ephemeral=True)
                return
            await member.remove_roles(role, reason=f"Temporary role admin removal by {interaction.user} - {reason}"[:512])
            await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Removed **{role.name}** from **{format_user_reference(member)}**.", ephemeral=False)
        except discord.Forbidden:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).", ephemeral=True)
        except Exception as e:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(_shorten(f"<:disapprove:1517452151012589662> An error occurred: {e}", 2000), ephemeral=True)

    @app_commands.command(name='role-for_adm', description='Add or remove a role from all members who have a target role')
    @app_commands.describe(action='Whether to add or remove the role', role='The role to add or remove', target_role='The role filter; members with this role will be affected (use @everyone for everyone)')
    @app_commands.choices(action=[app_commands.Choice(name='Add', value='add'), app_commands.Choice(name='Remove', value='remove')])
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def role_for_adm(self, interaction: discord.Interaction, action: str, role: discord.Role, target_role: discord.Role):
        role_error = validate_role_selection(interaction, role, "role")
        if role_error:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(role_error, ephemeral=True)
            return

        if role is None or target_role is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Both role options are required.", ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        updated = 0
        skipped = 0
        failed = 0
        processed = 0
        stop_progress_updates = asyncio.Event()
        affected_members = []

        if target_role == interaction.guild.default_role:
            if len(interaction.guild.members) < interaction.guild.member_count:
                try:
                    await interaction.guild.chunk(cache=True)
                except Exception:
                    pass
            affected_members = list(interaction.guild.members)
        else:
            affected_members = list(target_role.members)
            if not affected_members and len(interaction.guild.members) < interaction.guild.member_count:
                try:
                    await interaction.guild.chunk(cache=True)
                except Exception:
                    pass
                affected_members = [member for member in interaction.guild.members if target_role in member.roles]

        def build_progress_embed() -> discord.Embed:
            progress_percent = (processed / len(affected_members) * 100) if affected_members else 100.0
            action_text = "adding" if action == "add" else "removing"
            embed = discord.Embed(
                title="<:gear:1517576939097952496> Role Update In Progress",
                description=f"{action_text.capitalize()} role **{role.name}** from members with **{target_role.name}**...",
                color=discord.Color.blurple()
            )
            embed.add_field(name="<:list:1517497572770451567> Processed", value=f"{processed}/{len(affected_members)} ({progress_percent:.1f}%)", inline=True)
            embed.add_field(name="<:approve:1517452125687513158> Updated", value=str(updated), inline=True)
            embed.add_field(name="<:warning:1517452174991556758> Skipped", value=str(skipped), inline=True)
            embed.add_field(name="<:disapprove:1517452151012589662> Failed", value=str(failed), inline=True)
            return embed

        async def update_progress_message(message: discord.Message):
            while not stop_progress_updates.is_set():
                await asyncio.sleep(10)
                if stop_progress_updates.is_set():
                    break
                try:
                    await message.edit(embed=build_progress_embed())
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    break

        progress_message = await interaction.followup.send(embed=build_progress_embed(), ephemeral=False)
        progress_task = self._spawn(update_progress_message(progress_message))

        if not affected_members:
            stop_progress_updates.set()
            if progress_task and not progress_task.done():
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
                except Exception as error:
                    print(f"Progress task cleanup failed: {error}")
            await progress_message.edit(content=f"<:warning:1517452174991556758> No members with the role **{target_role.name}** were found.", embed=build_progress_embed())
            return

        try:
            for member in affected_members:
                try:
                    if action == "add":
                        if role not in member.roles:
                            await member.add_roles(role, reason=f"Role mass update by {interaction.user}")
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        if role in member.roles:
                            await member.remove_roles(role, reason=f"Role mass update by {interaction.user}")
                            updated += 1
                        else:
                            skipped += 1
                except discord.Forbidden:
                    failed += 1
                except Exception as error:
                    failed += 1
                    print(f"Error updating role for {member}: {error}")
                finally:
                    processed += 1
        finally:
            stop_progress_updates.set()
            if progress_task and not progress_task.done():
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
                except Exception as error:
                    print(f"Progress task cleanup failed: {error}")

        action_text = "added to" if action == "add" else "removed from"
        embed = discord.Embed(
            title="<:gear:1517576939097952496> Role Update Complete",
            description=f"The role **{role.name}** was {action_text} **{target_role.name}** members.",
            color=discord.Color.green() if action == "add" else discord.Color.orange()
        )
        embed.add_field(name="<:graph:1517584522877866065> Affected Members", value=str(len(affected_members)), inline=True)
        embed.add_field(name="<:approve:1517452125687513158> Updated", value=str(updated), inline=True)
        embed.add_field(name="<:warning:1517452174991556758> Skipped", value=str(skipped), inline=True)
        if failed:
            embed.add_field(name="<:disapprove:1517452151012589662> Failed", value=str(failed), inline=True)

        try:
            await progress_message.edit(content="<:approve:1517452125687513158> Finished updating roles.", embed=embed)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            await interaction.followup.send(embed=embed, ephemeral=False)


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
