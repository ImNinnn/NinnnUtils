from LowerLeveled.timestamp import parse_duration_to_seconds
from Shared.Moderation import get_guild_automod_config, sync_guild_word_block_rule
from . import *

class AutomodSettingsView(LayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color, bot):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.color = color
        self.bot = bot
        self.build_components()

    def build_components(self):
        self.clear_items()
        automod, _ = get_guild_automod_config(self.guild_id)
        blocked_words = automod.get("blocked_words", [])
        warning_sanctions = automod.get("warning_sanctions", [])
        blocked_summary = "\n".join(f"- {item.get('phrase', '')}{' (regex)' if item.get('use_regex') else ''}" for item in blocked_words[:6]) or "None"
        sanctions_summary = []
        for item in warning_sanctions[:6]:
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def handle_back(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

    async def handle_word_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.send_message(
            "What would you like to do with blocked words?",
            view=AutomodWordChoiceView(self.user_id, self.guild_id, self.open_word_add, self.open_word_remove, settings_message),
            ephemeral=True,
        )

    async def open_word_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(AutomodWordAddModal(self.add_word_block, self.guild_id, settings_message))

    async def open_word_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(AutomodWordRemoveModal(self.remove_word_block, self.guild_id, settings_message))

    async def add_word_block(self, interaction: discord.Interaction, phrase: str, use_regex: bool, warn_on_match: bool, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        automod.setdefault("blocked_words", []).append({"phrase": phrase, "use_regex": use_regex, "warn_on_match": warn_on_match})
        save_guild_data(data)
        await sync_guild_word_block_rule(self.bot, self.guild_id)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Blocked phrase saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color, self.bot), settings_message)

    async def remove_word_block(self, interaction: discord.Interaction, phrase: str, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        blocked_words = automod.get("blocked_words", [])
        filtered = [item for item in blocked_words if str(item.get("phrase", "")).strip().lower() != phrase.strip().lower()]
        if len(filtered) != len(blocked_words):
            automod["blocked_words"] = filtered
            save_guild_data(data)
            await sync_guild_word_block_rule(self.bot, self.guild_id)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Blocked phrase removed.", ephemeral=True)
            await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color, self.bot), settings_message)
        else:
            await interaction.response.send_message("<:disapprove:1517452151012589662> No matching blocked phrase was found.", ephemeral=True)

    async def handle_sanctions_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.send_message(
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
        save_guild_data(data)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Warning sanction saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color, self.bot), settings_message)

    async def remove_sanction_rule(self, interaction: discord.Interaction, warns: int, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        sanctions = automod.get("warning_sanctions", [])
        filtered = [item for item in sanctions if int(item.get("warns", 0)) != warns]
        if len(filtered) != len(sanctions):
            automod["warning_sanctions"] = filtered
            save_guild_data(data)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Warning sanction removed.", ephemeral=True)
            await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color, self.bot), settings_message)
        else:
            await interaction.response.send_message("<:disapprove:1517452151012589662> No matching warning sanction was found.", ephemeral=True)

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


class AutomodWordChoiceView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: str, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
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
        self.phrase_input = TextInput(label="Word or phrase", placeholder="Enter a word or phrase", required=True, max_length=200)
        self.regex_input = TextInput(label="Regex? (true/false)", placeholder="false", required=True, max_length=5)
        self.warn_input = TextInput(label="Warn on match? (true/false)", placeholder="false", required=True, max_length=5)
        self.add_item(self.phrase_input)
        self.add_item(self.regex_input)
        self.add_item(self.warn_input)

    async def on_submit(self, interaction: discord.Interaction):
        def parse_bool(value: str) -> bool:
            return value.strip().lower() in {"true", "yes", "y", "1"}

        use_regex = parse_bool(self.regex_input.value)
        warn_on_match = parse_bool(self.warn_input.value)
        await self.callback(interaction, self.phrase_input.value.strip(), use_regex, warn_on_match, self.settings_message)


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


class AutomodSanctionChoiceView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: str, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Warn count must be a number.", ephemeral=True)
            return

        action = self.action_input.value.strip().lower()
        if action not in {"timeout", "kick", "ban"}:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Action must be timeout, kick, or ban.", ephemeral=True)
            return

        duration_text = self.duration_input.value.strip() if self.duration_input.value else ""
        duration_seconds = None
        if action == "timeout":
            if not duration_text:
                duration_text = "1d"
            duration_seconds = parse_duration_to_seconds(duration_text)
            if duration_seconds is None or duration_seconds <= 0:
                await interaction.response.send_message("<:disapprove:1517452151012589662> Timeout duration must be a valid value like 1d, 10s, or 50m.", ephemeral=True)
                return
        else:
            duration_seconds = 0
            if duration_text:
                await interaction.response.send_message("<:disapprove:1517452151012589662> Duration is only valid for timeout actions.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Warn count must be a number.", ephemeral=True)
            return
        await self.callback(interaction, warns, self.settings_message)
