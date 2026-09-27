"""Leveling: XP from messages, reactions and voice, level-up rewards, rank commands and level settings."""

import asyncio
import random
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, Container, Modal, Section, Separator, TextDisplay, TextInput

import save
from utils import runtime
from utils.audit import add_bot_error_entry
from utils.automod import is_honeypot_channel
from utils.banners import create_levelup_card
from utils.counters import is_counter_number_message
from utils.economy import get_user_data, inventory_add, normalize_item, parse_item_amount_entry
from utils.formatting import COLOR_EMOJIS, format_user_reference, format_user_reference_with_setting
from utils.permissions import validate_role_selection
from utils.user_settings import get_user_color, get_user_color_value, get_user_settings_entry, resolve_user_color_name
from utils.views import EconomyChoiceView, TimeoutDisabledLayoutView, TimeoutDisabledView

REACTION_XP_COOLDOWN_SECONDS = 15


def get_xp_needed(level: int) -> int:
    return 100 + (level * 10)


def ensure_guild_levels(levels: dict, guild_id: str) -> dict:
    guild_levels = levels.setdefault(guild_id, {})
    guild_levels.setdefault("config", {}).setdefault("rewards", {})
    guild_levels["config"].setdefault("channel_id", None)
    guild_levels.setdefault("users", {})
    return guild_levels


def get_user_has_leveled_up_before(user_id: str) -> bool:
    settings = save.load_user_settings()
    user_settings = get_user_settings_entry(settings, user_id)

    if "has_leveled_up_before" in user_settings:
        return bool(user_settings["has_leveled_up_before"])

    user_settings["has_leveled_up_before"] = False
    save.save_user_settings(settings)
    return False


def set_user_has_leveled_up_before(user_id: str, value: bool) -> None:
    settings = save.load_user_settings()
    get_user_settings_entry(settings, user_id)["has_leveled_up_before"] = value
    save.save_user_settings(settings)


def save_level_reward_data(guild_id: str, level: int, reward_data: dict) -> None:
    levels = save.load_levels()
    ensure_guild_levels(levels, guild_id)["config"]["rewards"][str(level)] = reward_data
    save.save_levels(levels)


def format_level_reward_summary(guild: discord.Guild, level: str, reward_data: dict) -> str:
    parts = []

    role_id = reward_data.get("role_id")
    if role_id:
        role = guild.get_role(role_id)
        parts.append(f"Role: {role.mention if role else f'`{role_id}`'}")

    temp_role_id = reward_data.get("temp_role_id")
    if temp_role_id:
        role = guild.get_role(temp_role_id)
        duration = reward_data.get("duration", 0)
        parts.append(f"Temp role: {role.mention if role else f'`{temp_role_id}`'} for `{duration}s`")

    money = reward_data.get("money", 0)
    if money > 0:
        parts.append(f"Money: `${money}`")

    xp = reward_data.get("xp", 0)
    if xp > 0:
        parts.append(f"XP: `{xp}`")

    give_item = reward_data.get("give_item")
    if give_item:
        amount = reward_data.get("give_item_amount", 1)
        parts.append(f"Item: `{amount}x {give_item}`")

    if not parts:
        return f"Level {level}: No rewards configured."

    return f"Level {level}: " + " | ".join(parts)


async def ensure_levels_enabled(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return True
    if not save.is_levels_enabled(str(interaction.guild.id)):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Levels are disabled in this server.", ephemeral=True)
        return False
    return True


# -------------------------------------------------------------------------------------------------------------
#                                               Level settings (opened from /settings)
# -------------------------------------------------------------------------------------------------------------


class LevelRewardActionModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None = None):
        super().__init__(title="Find level reward to edit")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.level_input = TextInput(label="Level number", placeholder="Level (e.g. 5)", required=True, max_length=10)
        self.add_item(self.level_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            level = int(self.level_input.value.strip())
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Level must be a number.", ephemeral=True)
            return
        levels = save.load_levels()
        rewards = levels.get(self.guild_id, {}).get("config", {}).get("rewards", {})
        reward = rewards.get(str(level))
        if reward is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No reward configured for level {level}.", ephemeral=True)
            return
        await self.callback(interaction, level, reward, self.settings_message)


class LevelRewardEditLaunchView(TimeoutDisabledView):
    def __init__(self, user_id: int, settings_message: discord.Message | None, level: int, reward_data: dict, parent_view: 'LevelSettingsView'):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.settings_message = settings_message
        self.level = level
        self.reward_data = reward_data or {}
        self.parent = parent_view
        self.open_button = Button(label="Open edit modal", style=discord.ButtonStyle.primary, custom_id="open_level_reward_edit")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_level_reward_edit")
        self.open_button.callback = self.open_edit
        self.cancel_button.callback = self.cancel
        self.add_item(self.open_button)
        self.add_item(self.cancel_button)

    async def open_edit(self, interaction: discord.Interaction):
        modal = LevelRewardModal(None, self.parent.guild_id, self.settings_message)
        modal.level_input.default = str(self.level)
        modal.duration_input.default = str(self.reward_data.get("duration", 0))
        modal.money_input.default = str(self.reward_data.get("money", 0))
        modal.xp_input.default = str(self.reward_data.get("xp", 0))
        give_item = self.reward_data.get("give_item")
        if give_item:
            modal.item_input.default = f"{give_item}:{self.reward_data.get('give_item_amount', 1)}"

        async def _on_submit(inner_interaction: discord.Interaction, reward_data: dict, level: int, settings_message_inner: discord.Message | None):
            # The edit modal has no role fields, so keep the roles that were already configured.
            reward_data["role_id"] = self.reward_data.get("role_id")
            reward_data["temp_role_id"] = self.reward_data.get("temp_role_id")
            save_level_reward_data(str(inner_interaction.guild.id), level, reward_data)
            await inner_interaction.response.defer(ephemeral=True); await inner_interaction.followup.send(f"<:approve:1517452125687513158> Level {level} reward updated.", ephemeral=True)
            try:
                await self.parent.refresh_settings_message(inner_interaction, LevelSettingsView(self.user_id, self.parent.guild_id, self.parent.color, settings_message=self.settings_message))
            except Exception:
                pass

        modal.callback = _on_submit
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Level reward edit cancelled.", ephemeral=True)


class LevelRoleSelectionView(TimeoutDisabledView):
    def __init__(self, user_id: int, guild: discord.Guild, prompt: str, level: int, reward_data: dict, settings_message: discord.Message | None, callback, is_temp_role: bool):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild = guild
        self.level = level
        self.reward_data = reward_data
        self.settings_message = settings_message
        self.callback = callback
        self.is_temp_role = is_temp_role
        self.role_select = None

        role_options = []
        for role in sorted(guild.roles, key=lambda r: (r.position, r.name), reverse=True):
            if role.is_default():
                continue
            role_options.append(discord.SelectOption(label=role.name[:100], value=str(role.id)))

        if role_options:
            self.role_select = discord.ui.Select(
                placeholder=prompt,
                options=role_options[:25],
                min_values=1,
                max_values=1,
                custom_id=f"level_role_select_{'temp' if is_temp_role else 'normal'}",
            )
            self.role_select.callback = self.on_role_selected
            self.add_item(self.role_select)

        self.no_button = Button(label="No", style=discord.ButtonStyle.secondary, custom_id=f"level_role_none_{'temp' if is_temp_role else 'normal'}")
        self.no_button.callback = self.on_no_selected
        self.add_item(self.no_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_role_selected(self, interaction: discord.Interaction):
        role_id = int(self.role_select.values[0])
        if self.is_temp_role:
            self.reward_data["temp_role_id"] = role_id
        else:
            self.reward_data["role_id"] = role_id
        await self.callback(interaction, self.reward_data, self.level, self.settings_message, self.is_temp_role)

    async def on_no_selected(self, interaction: discord.Interaction):
        if self.is_temp_role:
            self.reward_data["temp_role_id"] = None
        else:
            self.reward_data["role_id"] = None
        await self.callback(interaction, self.reward_data, self.level, self.settings_message, self.is_temp_role)


class LevelRewardModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Set level reward")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.level_input = TextInput(label="Level", placeholder="1", required=True, max_length=10)
        self.duration_input = TextInput(label="Temp role duration (seconds)", placeholder="0", required=True, max_length=10)
        self.money_input = TextInput(label="Money reward", placeholder="0", required=True, max_length=10)
        self.xp_input = TextInput(label="XP reward", placeholder="0", required=True, max_length=10)
        self.item_input = TextInput(label="Item (Item:Amount)", placeholder="Optional item:amount", required=False, max_length=100)
        self.add_item(self.level_input)
        self.add_item(self.duration_input)
        self.add_item(self.money_input)
        self.add_item(self.xp_input)
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            level = int(self.level_input.value.strip())
            duration = int(self.duration_input.value.strip() or 0)
            money = int(self.money_input.value.strip() or 0)
            xp = int(self.xp_input.value.strip() or 0)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Level, duration, money, and XP must be numbers.", ephemeral=True)
            return

        give_item, give_amount = parse_item_amount_entry(self.item_input.value, default_amount=1)
        reward_data = {
            "role_id": None,
            "temp_role_id": None,
            "duration": max(0, duration),
            "money": money,
            "xp": xp,
            "give_item": normalize_item(give_item) if give_item else None,
            "give_item_amount": give_amount,
        }
        await self.callback(interaction, reward_data, level, self.settings_message)


class LevelSettingsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color, settings_message: discord.Message | None = None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.color = color
        self.settings_message = settings_message
        self.build_components()

    def build_components(self):
        self.clear_items()
        levels = save.load_levels()
        rewards = levels.get(self.guild_id, {}).get("config", {}).get("rewards", {})
        guild = runtime.bot.get_guild(int(self.guild_id)) if self.guild_id.isdigit() else None

        summary_lines = []
        for level_key, reward_data in sorted(rewards.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 999999)[:6]:
            summary_lines.append(f"Lvl {level_key}: {format_level_reward_summary(guild, level_key, reward_data) if guild else 'Configured'}")

        self.edit_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id=f"level_settings_edit_{self.user_id}")
        self.edit_button.callback = self.handle_edit
        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id=f"level_settings_back_{self.user_id}")
        self.back_button.callback = self.handle_back

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **Level settings**"),
            TextDisplay("Configure level-based rewards below."),
            Separator(),
            Section("<:box:1517581439552585759> Current rewards\n" + ("\n".join(summary_lines) if summary_lines else "None"), accessory=self.edit_button),
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
        if settings_message is None:
            settings_message = self.settings_message
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

    async def handle_back(self, interaction: discord.Interaction):
        from cogs.settings import GuildSettingsMenuView  # imported here: cogs.settings imports this cog

        await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

    async def handle_set(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LevelRewardModal(self.handle_reward_submit, self.guild_id, self.settings_message))

    async def handle_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Level rewards?",
            view=EconomyChoiceView(self.user_id, self.open_level_add, self.open_level_remove, "levels", self.open_level_edit, settings_message),
            ephemeral=True,
        )

    async def open_level_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(LevelRewardModal(self.handle_reward_submit, self.guild_id, settings_message))

    async def open_level_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(LevelRewardActionModal(self._perform_level_remove, self.guild_id, settings_message))

    async def open_level_edit(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(LevelRewardActionModal(self.open_level_edit_launch, self.guild_id, settings_message))

    async def _perform_level_remove(self, interaction: discord.Interaction, level: int, reward_data: dict, settings_message: discord.Message | None = None):
        levels = save.load_levels()
        guild_rewards = ensure_guild_levels(levels, self.guild_id)["config"]["rewards"]
        if str(level) in guild_rewards:
            del guild_rewards[str(level)]
            save.save_levels(levels)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Level {level} reward removed.", ephemeral=True)
            await self.refresh_settings_message(interaction, LevelSettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Specified level reward was not found.", ephemeral=True)

    async def open_level_edit_launch(self, interaction: discord.Interaction, level: int, reward_data: dict, settings_message: discord.Message | None = None):
        view = LevelRewardEditLaunchView(self.user_id, settings_message, level, reward_data, self)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Reward found. Click below to continue editing.", view=view, ephemeral=True)

    async def handle_reward_submit(self, interaction: discord.Interaction, reward_data: dict, level: int, settings_message: discord.Message | None):
        guild = interaction.guild
        if guild is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This can only be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:approve:1517452125687513158> Level {level} reward details saved. Choose a role to grant when this level is reached. Press No to skip.",
            view=LevelRoleSelectionView(self.user_id, guild, "Choose a role", level, reward_data, settings_message, self.handle_level_role_selection, False),
            ephemeral=True,
        )

    async def handle_level_role_selection(self, interaction: discord.Interaction, reward_data: dict, level: int, settings_message: discord.Message | None, is_temp_role: bool):
        guild = interaction.guild
        if guild is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This can only be used in a server.", ephemeral=True)
            return

        role_id = reward_data.get("temp_role_id" if is_temp_role else "role_id")
        role = guild.get_role(role_id) if role_id else None
        if role_id and role is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> The selected role is no longer available.", ephemeral=True)
            return

        role_error = validate_role_selection(interaction, role, "temporary role reward" if is_temp_role else "role reward")
        if role_error:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(role_error, ephemeral=True)
            return

        if is_temp_role:
            save_level_reward_data(str(guild.id), level, reward_data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Level {level} reward saved.", ephemeral=True)
            await self.refresh_settings_message(interaction, LevelSettingsView(self.user_id, self.guild_id, self.color, settings_message=self.settings_message))
            return

        if role_id is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:approve:1517452125687513158> Role setup skipped for level {level}. Choose a temporary role next, or press No to skip.",
                view=LevelRoleSelectionView(self.user_id, guild, "Choose a temporary role", level, reward_data, settings_message, self.handle_level_role_selection, True),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:approve:1517452125687513158> Role saved for level {level}. Choose a temporary role next, or press No to skip.",
            view=LevelRoleSelectionView(self.user_id, guild, "Choose a temporary role", level, reward_data, settings_message, self.handle_level_role_selection, True),
            ephemeral=True,
        )


# -------------------------------------------------------------------------------------------------------------
#                                               Cog
# -------------------------------------------------------------------------------------------------------------


class LevelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reaction_xp_cooldowns: dict[tuple[int, int], datetime] = {}
        self._background_tasks: set[asyncio.Task] = set()

    def _spawn(self, coro) -> None:
        # Keep a reference so the task isn't garbage-collected before it finishes.
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def start_tasks(self):
        if not self.voice_xp_tracker.is_running():
            self.voice_xp_tracker.start()

    async def cog_unload(self):
        if self.voice_xp_tracker.is_running():
            self.voice_xp_tracker.cancel()

    # ---------------------------------------------------------------- XP

    async def _apply_level_reward(self, member: discord.Member, guild: discord.Guild, guild_id: str, reward, announce_channel) -> None:
        if isinstance(reward, (str, int)):
            reward = {"role_id": int(reward)}

        if reward.get("money", 0) > 0 or reward.get("give_item"):
            data = save.load_data()
            economy_user = get_user_data(data, guild_id, member.id)
            if reward.get("money", 0) > 0:
                economy_user["balance"] += reward["money"]
            if reward.get("give_item"):
                inventory_add(economy_user["inventory"], reward["give_item"], reward.get("give_item_amount", 1))
            save.save_data(data)

        if reward.get("role_id"):
            role = guild.get_role(int(reward["role_id"]))
            if role and role not in member.roles:
                try:
                    await member.add_roles(role)
                except discord.Forbidden as error:
                    add_bot_error_entry(guild.id, None, member, f"level reward role: {role.name}", error)

        if reward.get("temp_role_id"):
            role = guild.get_role(int(reward["temp_role_id"]))
            if role and role not in member.roles:
                try:
                    await member.add_roles(role)
                except discord.Forbidden as error:
                    add_bot_error_entry(guild.id, None, member, f"level temp role: {role.name}", error)
                    role = None
            if role and reward.get("duration", 0) > 0:
                async def remove_temp_role(r, duration):
                    await asyncio.sleep(duration)
                    try:
                        await member.remove_roles(r)
                    except discord.Forbidden as error:
                        add_bot_error_entry(guild.id, None, member, f"level temp role remove: {r.name}", error)
                self._spawn(remove_temp_role(role, reward.get("duration", 0)))

        if reward.get("xp", 0) > 0:
            await self.add_xp(member, guild, reward["xp"], announce_channel=announce_channel)

    async def add_xp(self, member: discord.Member, guild: discord.Guild, xp_to_add: int, announce_channel=None):
        if member.bot:
            return

        if not save.is_levels_enabled(str(guild.id)):
            return

        levels = save.load_levels()
        guild_id = str(guild.id)
        user_id = str(member.id)

        guild_levels = ensure_guild_levels(levels, guild_id)
        if user_id not in guild_levels["users"]:
            guild_levels["users"][user_id] = {"xp": 0, "level": 0, "color": get_user_color(user_id) or "white"}

        user_data = guild_levels["users"][user_id]
        user_data["xp"] += xp_to_add

        start_level = user_data["level"]
        while user_data["xp"] >= get_xp_needed(user_data["level"]):
            user_data["xp"] -= get_xp_needed(user_data["level"])
            user_data["level"] += 1
        leveled_up = user_data["level"] > start_level

        save.save_levels(levels)
        if not leveled_up:
            return

        has_leveled_up_before = get_user_has_leveled_up_before(user_id)
        first_time_level_up = not has_leveled_up_before
        current_level = user_data["level"]
        level_up_notification_sent = False

        # Give the reward of every level crossed, not only the last one.
        rewards = guild_levels["config"].get("rewards", {})
        for reached_level in range(start_level + 1, current_level + 1):
            reward = rewards.get(str(reached_level))
            if reward:
                await self._apply_level_reward(member, guild, guild_id, reward, announce_channel)

        guild_config = save.get_guild_config(guild_id)[0]
        if guild_config.get("level_up_message_enabled", False) and announce_channel is not None:
            try:
                settings = save.load_user_settings()
                level_up_message = f"{format_user_reference_with_setting(member, settings)} just reached **Level {current_level}**!"
                if first_time_level_up:
                    level_up_message += "\n-# Use /settings and go to the user settings to disable pings."
                await announce_channel.send(level_up_message)
                level_up_notification_sent = True
            except discord.Forbidden as error:
                add_bot_error_entry(guild.id, announce_channel.id, member, "level up message", error)
            except Exception:
                pass

        channel_id = guild_levels["config"].get("channel_id")
        target_channel = guild.get_channel(int(channel_id)) if channel_id else None

        if target_channel:
            file = await create_levelup_card(member, current_level)
            if file:
                try:
                    settings = save.load_user_settings()
                    level_banner_message = f"{format_user_reference_with_setting(member, settings)}, you just reached **Level {current_level}**!"
                    if first_time_level_up:
                        level_banner_message += "\n-# Use /settings and go to the user settings to disable pings."
                    await target_channel.send(
                        content=level_banner_message,
                        file=file
                    )
                    level_up_notification_sent = True
                except discord.Forbidden as error:
                    add_bot_error_entry(guild.id, target_channel.id, member, "level banner", error)

        if first_time_level_up and level_up_notification_sent:
            set_user_has_leveled_up_before(user_id, True)

    # ---------------------------------------------------------------- XP sources

    @tasks.loop(minutes=2.0)
    async def voice_xp_tracker(self):
        for guild in self.bot.guilds:
            for voice_channel in guild.voice_channels:
                real_members = [
                    member for member in voice_channel.members
                    if not member.bot and not member.voice.self_deaf and not member.voice.deaf
                ]
                for member in real_members:
                    try:
                        await self.add_xp(member, guild, random.randint(5, 10))
                    except Exception as exc:
                        print(f"[levels] voice XP failed for {member} in {guild}: {type(exc).__name__}: {exc}")

    @voice_xp_tracker.before_loop
    async def before_voice_xp_tracker(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if is_honeypot_channel(message.guild, message.channel):
            return
        # Counting messages in a counter channel don't give XP.
        if is_counter_number_message(str(message.guild.id), message.channel.id, message.content):
            return

        await self.add_xp(message.author, message.guild, random.randint(5, 10), announce_channel=message.channel)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        reactor = guild.get_member(payload.user_id)
        if not reactor or reactor.bot:
            return

        cooldown_key = (payload.guild_id, payload.user_id)
        now = datetime.now()
        last_xp = self.reaction_xp_cooldowns.get(cooldown_key)
        if last_xp and (now - last_xp).total_seconds() < REACTION_XP_COOLDOWN_SECONDS:
            return
        self.reaction_xp_cooldowns[cooldown_key] = now

        channel = guild.get_channel(payload.channel_id)
        await self.add_xp(reactor, guild, random.randint(1, 3), announce_channel=channel)
        try:
            message = await channel.fetch_message(payload.message_id)
            if message.author and not message.author.bot and message.author.id != payload.user_id:
                await self.add_xp(message.author, guild, random.randint(3, 5), announce_channel=channel)
        except discord.Forbidden as error:
            add_bot_error_entry(payload.guild_id, payload.channel_id, None, "reaction xp source fetch", error)
        except Exception:
            pass

    # ---------------------------------------------------------------- commands

    @app_commands.command(name='level', description='View your current server tier standing level rank card')
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(user='Optional member to inspect')
    async def level(self, interaction: discord.Interaction, user: discord.Member | None = None):
        if not await ensure_levels_enabled(interaction):
            return
        target = user or interaction.user
        levels = save.load_levels()
        g_id, u_id = str(interaction.guild_id), str(target.id)

        user_data = levels.get(g_id, {}).get("users", {}).get(u_id, {"xp": 0, "level": 0, "color": "white"})

        current_xp = user_data["xp"]
        current_lvl = user_data["level"]
        chosen_color = resolve_user_color_name(get_user_color(u_id) or user_data.get("color", "white") or "white")
        xp_needed = get_xp_needed(current_lvl)

        ratio = current_xp / xp_needed if xp_needed > 0 else 0
        filled_blocks = min(max(int(ratio * 10), 0), 10)
        empty_blocks = 10 - filled_blocks

        filled_emoji = COLOR_EMOJIS.get(chosen_color, "<:Square_White:1517679898414813427>")
        empty_emoji = COLOR_EMOJIS.get("black", "<:Square_Black:1517679889615032540>")

        progress_bar = (filled_emoji * filled_blocks) + (empty_emoji * empty_blocks)

        embed = discord.Embed(
            title=f"<:chalice:1517579767573123092> Rank Profile - {target.display_name}",
            color=get_user_color_value(str(target.id))
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Current Tier", value=f"<:spark:1517583248421552305> **Level {current_lvl}**", inline=True)
        embed.add_field(name="Experience Nodes", value=f"<:Vial:1517681553377857628> `{current_xp:,}` / `{xp_needed:,}` XP", inline=True)
        embed.add_field(name="Progress Metrics", value=progress_bar, inline=False)

        await interaction.response.defer(); await interaction.followup.send(embed=embed)

    @app_commands.command(name='level-leaderboard', description='Display the top 10 highest-level users in this guild')
    @app_commands.allowed_installs(guilds=True, users=False)
    async def level_leaderboard(self, interaction: discord.Interaction):
        if not await ensure_levels_enabled(interaction):
            return
        levels = save.load_levels()
        g_id = str(interaction.guild_id)

        users_dict = levels.get(g_id, {}).get("users", {})
        if not users_dict:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("📭 No active XP statistics logged in this server yet.", ephemeral=True)
            return

        sorted_users = sorted(users_dict.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)

        embed = discord.Embed(
            title=f"<:graph:1517584522877866065> Level Standings Leaderboard - {interaction.guild.name}",
            color=get_user_color_value(str(interaction.user.id))
        )

        description_text = ""
        for index, (u_id, data) in enumerate(sorted_users[:10], start=1):
            member = interaction.guild.get_member(int(u_id))
            name_str = member.display_name if member else f"User left server (`{u_id}`)"
            description_text += f"`#{index}` **{name_str}** - Lvl {data['level']} ({data['xp']} XP)\n"

        embed.description = description_text
        await interaction.response.defer(); await interaction.followup.send(embed=embed)

    @app_commands.command(name='level-edit', description='Manually adjust or set a target user\'s level and XP indexes')
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def level_edit(self, interaction: discord.Interaction, user: discord.Member, level: int, xp: int = 0):
        if not await ensure_levels_enabled(interaction):
            return
        levels = save.load_levels()
        g_id, u_id = str(interaction.guild_id), str(user.id)

        guild_users = ensure_guild_levels(levels, g_id)["users"]
        guild_users[u_id] = {
            "xp": max(0, xp),
            "level": max(0, level),
            "color": guild_users.get(u_id, {}).get("color", "white")
        }
        save.save_levels(levels)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:gear:1517576939097952496> Action complete. Set {format_user_reference(user)} to **Level {level}** with **{xp} XP**.", ephemeral=True)

    @app_commands.command(name='rewards_info', description='Show the level rewards configured for this guild')
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(level='Optional specific level to inspect')
    async def rewards_info(self, interaction: discord.Interaction, level: int | None = None):
        if not await ensure_levels_enabled(interaction):
            return
        levels = save.load_levels()
        g_id = str(interaction.guild_id)
        guild_data = levels.get(g_id, {})
        rewards = guild_data.get("config", {}).get("rewards", {})

        if not rewards:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("📭 No level rewards are configured for this server yet.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"<:box:1517581439552585759> Level Rewards - {interaction.guild.name}",
            color=discord.Color.gold()
        )

        if level is not None:
            reward_data = rewards.get(str(level))
            if not reward_data:
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(f"<:disapprove:1517452151012589662> No rewards are configured for level {level} in this server.", ephemeral=True)
                return

            embed.description = format_level_reward_summary(interaction.guild, str(level), reward_data)
        else:
            sorted_levels = sorted(rewards.items(), key=lambda item: int(item[0]))
            embed.description = "\n".join(
                format_level_reward_summary(interaction.guild, lvl, reward_data)
                for lvl, reward_data in sorted_levels
            )

        await interaction.response.defer(); await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    cog = LevelsCog(bot)
    await bot.add_cog(cog)
    if bot.is_ready():
        cog.start_tasks()
