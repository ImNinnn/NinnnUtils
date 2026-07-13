import asyncio

from LowerLeveled.messages import safe_send
from Shared.Boards import get_guild_board_entries, load_board_data, save_board_data
from Shared.Counters import get_guild_counter_entries
from Shared.Guilds import format_channel_reference
from Shared.Leveling import get_level_channel_id, set_level_channel
from Shared.Locks import save_lock_config
from Shared.Moderation import get_admin_log_channel_mentions, get_guild_admin_log_channel_ids
from main import admin_log_channels, locked_channels
from . import *
from .YesNo import YesNoView


def get_locked_channel_mentions(guild):
    pass


class ChannelSettingsView(LayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color, page: int = 1, bot = None):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.page = page
        self.color = color
        self.bot = bot
        self.build_components()

    def build_components(self):
        self.clear_items()
        guild = self.bot.get_guild(int(self.guild_id))
        guild_config, _ = get_guild_config(self.guild_id)
        welcome_channel = format_channel_reference(guild, guild_config.get("welcome_channel_id")) if guild else "None"
        goodbye_channel = format_channel_reference(guild, guild_config.get("goodbye_channel_id")) if guild else "None"
        level_channel = "None"
        level_id = get_level_channel_id(self.guild_id)
        if level_id:
            level_channel = format_channel_reference(guild, level_id) if guild else "None"
        admin_channels = get_admin_log_channel_mentions(guild) if guild else []
        admin_label = "Remove" if admin_channels else "Set"
        admin_value = "\n".join(admin_channels) if admin_channels else "None"

        board_entries = get_guild_board_entries(self.guild_id)
        counter_entries = get_guild_counter_entries(guild) if guild else []
        locked_entries = get_locked_channel_mentions(guild) if guild else []
        honeypot_channel = format_channel_reference(guild, guild_config.get("honeypot_channel_id")) if guild else "None"
        honeypot_sanction = guild_config.get("honeypot_sanction") or {}
        honeypot_action = str(honeypot_sanction.get("action", "timeout")).lower()
        honeypot_duration = str(honeypot_sanction.get("duration", "") or "")
        if honeypot_action == "timeout":
            honeypot_summary = f"Timeout ({honeypot_duration or '1d'})"
        else:
            honeypot_summary = honeypot_action.title() if honeypot_action in {"kick", "ban"} else "None"
        honeypot_value = f"{honeypot_channel}\nSanction: {honeypot_summary}" if guild_config.get("honeypot_channel_id") else f"{honeypot_channel}\nSanction: None"


        if self.page == 1:
            self.welcome_button = Button(label="Remove" if guild_config.get("welcome_channel_id") else "Set", style=discord.ButtonStyle.primary, custom_id="channel_welcome_toggle")
            self.goodbye_button = Button(label="Remove" if guild_config.get("goodbye_channel_id") else "Set", style=discord.ButtonStyle.primary, custom_id="channel_goodbye_toggle")
            self.level_button = Button(label="Remove" if level_id else "Set", style=discord.ButtonStyle.primary, custom_id="channel_level_toggle")
            self.admin_button = Button(label=admin_label, style=discord.ButtonStyle.primary, custom_id="channel_admin_toggle")
            self.honeypot_button = Button(label="Remove" if guild_config.get("honeypot_channel_id") else "Set", style=discord.ButtonStyle.primary, custom_id="channel_honeypot_toggle")

            self.welcome_button.callback = self.handle_welcome_toggle
            self.goodbye_button.callback = self.handle_goodbye_toggle
            self.level_button.callback = self.handle_level_toggle
            self.admin_button.callback = self.handle_admin_toggle
            self.honeypot_button.callback = self.handle_honeypot_toggle

            page_button = Button(label="Page 2", style=discord.ButtonStyle.secondary, custom_id="channel_settings_next")
            page_button.callback = self.open_page_two
        else:
            self.board_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="channel_board_edit")
            self.counter_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="channel_counter_edit")
            self.locked_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="channel_locked_edit")

            self.board_button.callback = self.handle_board_edit
            self.counter_button.callback = self.handle_counter_edit
            self.locked_button.callback = self.handle_locked_edit

            page_button = Button(label="Page 1", style=discord.ButtonStyle.secondary, custom_id="channel_settings_prev")
            page_button.callback = self.open_page_one

        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="channel_settings_back")
        self.back_button.callback = self.handle_back

        container_items = [
            TextDisplay("<:gear:1517576939097952496> **Channel settings**"),
            TextDisplay(f"Page {self.page}/2 - Set and remove channel settings below."),
            Separator(),
        ]

        if self.page == 1:
            container_items += [
                Section(f"<:plus:1518348756570079262> Welcome Channel\n{welcome_channel}", accessory=self.welcome_button),
                Section(f"<:minus:1518348754111959150> Goodbye Channel\n{goodbye_channel}", accessory=self.goodbye_button),
                Section(f"<:chalice:1517579767573123092> Level-up Announce Channel\n{level_channel}", accessory=self.level_button),
                Section(f"<:unlocked:1517574880034558102> Admin Log Channel\n{admin_value}", accessory=self.admin_button),
                Section(f"<:honey:1524116282075512842> Honeypot Channel\n{honeypot_value}",
                        accessory=self.honeypot_button),
            ]
        else:
            board_text = "\n".join(board_entries) if board_entries else "None"
            counter_text = "\n".join(counter_entries) if counter_entries else "None"
            locked_text = "\n".join(locked_entries) if locked_entries else "None"
            container_items += [
                Section(f"<:list:1517497572770451567> Board Channels\n{board_text}", accessory=self.board_button),
                Section(f"<:multi:1518348755261460661> Counter Channels\n{counter_text}", accessory=self.counter_button),
                Section(f"<:locked:1517574877257924809> Locked Channels\n{locked_text}", accessory=self.locked_button),
            ]

        container = Container(*container_items, accent_color=self.color)
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(page_button, self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True

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

    async def handle_back(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

    async def handle_close(self, interaction: discord.Interaction):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(view=self)

    async def open_page_two(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2))

    async def open_page_one(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1))

    async def handle_welcome_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("welcome_channel_id"):
            await interaction.response.send_message("Please confirm removal of the welcome channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_welcome, interaction.message), ephemeral=True)
            return
        await interaction.response.send_message(
            "Select the welcome channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select welcome channel", self.set_welcome_channel, interaction.message),
            ephemeral=True,
        )

    async def set_welcome_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["welcome_channel_id"] = channel.id
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Welcome channel set to {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_welcome(self, interaction: discord.Interaction, original_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["welcome_channel_id"] = None
        save_guild_data(data)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Welcome channel has been removed.", ephemeral=True)

    async def handle_goodbye_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("goodbye_channel_id"):
            await interaction.response.send_message("Please confirm removal of the goodbye channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_goodbye, interaction.message), ephemeral=True)
            return
        await interaction.response.send_message(
            "Select the goodbye channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select goodbye channel", self.set_goodbye_channel, interaction.message),
            ephemeral=True,
        )

    async def set_goodbye_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["goodbye_channel_id"] = channel.id
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Goodbye channel set to {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_goodbye(self, interaction: discord.Interaction, original_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["goodbye_channel_id"] = None
        save_guild_data(data)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Goodbye channel has been removed.", ephemeral=True)

    async def handle_level_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        level_id = get_level_channel_id(self.guild_id)
        if level_id:
            await interaction.response.send_message("Please confirm removal of the level-up announce channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_level_channel, interaction.message), ephemeral=True)
            return
        await interaction.response.send_message(
            "Select the level-up announce channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select level-up announce channel", self.set_level_channel, interaction.message),
            ephemeral=True,
        )

    async def set_level_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        set_level_channel(self.guild_id, channel.id)
        await safe_send(interaction, f"<:approve:1517452125687513158> Level-up announce channel set to {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_level_channel(self, interaction: discord.Interaction, original_message: discord.Message):
        set_level_channel(self.guild_id, None)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Level-up announce channel has been removed.", ephemeral=True)

    async def handle_admin_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        admin_ids = get_guild_admin_log_channel_ids(guild)
        if admin_ids:
            channel = guild.get_channel(admin_ids[0])
            if channel:
                await interaction.response.send_message(
                    f"Confirm removing admin logging from {channel.mention}?",
                    view=ConfirmRemoveView(self.user_id, self.confirm_remove_admin_log, interaction.message),
                    ephemeral=True,
                )
                return
        await interaction.response.send_message(
            "Select the admin log channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select admin log channel", self.add_admin_log_channel, interaction.message),
            ephemeral=True,
        )

    async def add_admin_log_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        admin_log_channels[channel.id] = True
        save_lock_config(locked_channels, admin_log_channels)
        await safe_send(interaction, f"<:approve:1517452125687513158> Admin logging enabled in {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_admin_log(self, interaction: discord.Interaction, original_message: discord.Message):
        admin_ids = get_guild_admin_log_channel_ids(interaction.guild)
        if admin_ids:
            admin_log_channels.pop(admin_ids[0], None)
            save_lock_config(locked_channels, admin_log_channels)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send(f"<:trash:1517497581058527404> Admin logging disabled.", ephemeral=True)

    async def handle_board_edit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "What would you like to do with Board Channels?",
            view=ChannelEditChoiceView(self.user_id, "Board Channels", self.open_board_add, self.open_board_remove, interaction.message),
            ephemeral=True,
        )

    async def open_board_add(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_message(
            "Select the board channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select board channel", self.board_channel_selected, settings_message),
            ephemeral=True,
        )

    async def board_channel_selected(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> Unable to continue board configuration.", ephemeral=True)
        prompt = await interaction.channel.send(
            f"{interaction.user.mention}, react to this message with the emoji you want to use for the board. You have 60 seconds.",
        )
        await interaction.response.send_message("React to the channel prompt to choose the board emoji.", ephemeral=True)

        def check(reaction, user):
            return (
                user.id == interaction.user.id
                and reaction.message.id == prompt.id
            )

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await prompt.delete()
            return await interaction.followup.send("<:disapprove:1517452151012589662> Emoji selection timed out.", ephemeral=True)

        emoji = str(reaction.emoji)
        await prompt.delete()
        await interaction.followup.send(
            "Emoji received. Set the required reaction count.",
            view=BoardCountPromptView(self.user_id, channel, emoji, settings_message, self.add_board_channel),
            ephemeral=True,
        )

    async def add_board_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, emoji: str, required_count: int, settings_message: discord.Message):
        board_data = load_board_data()
        if self.guild_id not in board_data:
            board_data[self.guild_id] = {}
        board_data[self.guild_id][emoji] = {
            "channel_id": channel.id,
            "required_count": required_count,
            "tracked_messages": {},
        }
        save_board_data(board_data)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Board for {emoji} saved to {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def open_board_remove(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_message(
            "Select the board channel to remove:",
            view=ChannelSelectorView(self.user_id, guild, "Select board channel to remove", self.remove_board_channel, settings_message),
            ephemeral=True,
        )

    async def remove_board_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        board_data = load_board_data()
        if self.guild_id not in board_data:
            await interaction.response.send_message("<:disapprove:1517452151012589662> No board channels are configured.", ephemeral=True)
            return
        removed = False
        for emoji_key, cfg in list(board_data[self.guild_id].items()):
            if cfg.get("channel_id") == channel.id:
                del board_data[self.guild_id][emoji_key]
                removed = True
        if removed:
            if not board_data[self.guild_id]:
                del board_data[self.guild_id]
            save_board_data(board_data)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Removed board channel {channel.mention}.", ephemeral=True)
            await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)
        else:
            await interaction.response.send_message("<:disapprove:1517452151012589662> That channel is not configured as a board channel.", ephemeral=True)

    async def handle_counter_edit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "What would you like to do with Counter Channels?",
            view=ChannelEditChoiceView(self.user_id, "Counter Channels", self.open_counter_add, self.open_counter_remove, interaction.message),
            ephemeral=True,
        )

    async def open_counter_add(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_message(
            "Select the counter channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select counter channel", self.counter_channel_selected, settings_message),
            ephemeral=True,
        )

    async def counter_channel_selected(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        async def yes_callback(interact: discord.Interaction):
            await self.add_counter_channel(interact, channel, True, settings_message)

        async def no_callback(interact: discord.Interaction):
            await self.add_counter_channel(interact, channel, False, settings_message)

        await interaction.response.send_message(
            f"Should failures reset the counter in {channel.mention}?",
            view=YesNoView(self.user_id, yes_callback, no_callback),
            ephemeral=True,
        )

    async def add_counter_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, reset_on_fail: bool, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config.setdefault("counter_channels", {})[str(channel.id)] = {
            "current_value": 0,
            "last_user_id": None,
            "reset_on_fail": reset_on_fail,
        }
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Counter channel configured for {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def open_counter_remove(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_message(
            "Select the counter channel to remove:",
            view=ChannelSelectorView(self.user_id, guild, "Select counter channel to remove", self.remove_counter_channel, settings_message),
            ephemeral=True,
        )

    async def remove_counter_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        if str(channel.id) not in guild_config.get("counter_channels", {}):
            await safe_send(interaction, "<:disapprove:1517452151012589662> That channel is not configured as a counter channel.", ephemeral=True)
            return
        del guild_config["counter_channels"][str(channel.id)]
        save_guild_data(data)
        await safe_send(interaction, f"<:trash:1517497581058527404> Removed counter channel {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def handle_locked_edit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "What would you like to do with Locked Channels?",
            view=ChannelEditChoiceView(self.user_id, "Locked Channels", self.open_locked_add, self.open_locked_remove, interaction.message),
            ephemeral=True,
        )

    async def handle_honeypot_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("honeypot_channel_id"):
            await interaction.response.send_message("Please confirm removal of the honeypot channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_honeypot, interaction.message), ephemeral=True)
            return
        await interaction.response.send_message(
            "Select the honeypot channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select honeypot channel", self.open_honeypot_sanction, interaction.message),
            ephemeral=True,
        )

    async def open_honeypot_sanction(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        resolved_channel = channel
        if interaction.guild and getattr(channel, "id", None):
            resolved_channel = interaction.guild.get_channel(channel.id) or await interaction.guild.fetch_channel(channel.id)
        if not resolved_channel or getattr(resolved_channel, "type", None) != discord.ChannelType.text:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> Please select a text channel for the honeypot.", ephemeral=True)
        await interaction.response.send_modal(HoneypotSanctionModal(self.set_honeypot_channel, resolved_channel, settings_message))

    async def set_honeypot_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, action: str, duration_seconds: int, duration_text: str, settings_message: discord.Message):
        resolved_channel = channel
        if interaction.guild and getattr(channel, "id", None):
            resolved_channel = interaction.guild.get_channel(channel.id) or await interaction.guild.fetch_channel(channel.id)

        guild_config, data = get_guild_config(self.guild_id)
        guild_config["honeypot_channel_id"] = getattr(resolved_channel, "id", channel.id)
        guild_config["honeypot_sanction"] = {
            "action": action,
            "duration_seconds": duration_seconds,
            "duration": duration_text,
        }
        save_guild_data(data)
        try:
            if resolved_channel and hasattr(resolved_channel, "send"):
                await resolved_channel.send(f"<:honey:1524116282075512842> This channel is a honeypot. Please do not send messages here. Any message sent here will trigger a sanction.")
        except (discord.Forbidden, discord.HTTPException):
            pass
        await safe_send(interaction, f"<:approve:1517452125687513158> Honeypot channel set to {getattr(resolved_channel, 'mention', str(channel.id))}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_honeypot(self, interaction: discord.Interaction, original_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["honeypot_channel_id"] = None
        guild_config["honeypot_sanction"] = {}
        save_guild_data(data)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Honeypot channel has been removed.", ephemeral=True)

    async def open_locked_add(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_message(
            "Select the locked channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select locked channel", self.add_locked_channel, settings_message),
            ephemeral=True,
        )

    async def add_locked_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        locked_channels[channel.id] = True
        save_lock_config(locked_channels, admin_log_channels)
        await safe_send(interaction, f"<:approve:1517452125687513158> Locked channel enabled for {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def open_locked_remove(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_message(
            "Select the locked channel to remove:",
            view=ChannelSelectorView(self.user_id, guild, "Select locked channel to remove", self.remove_locked_channel, settings_message),
            ephemeral=True,
        )

    async def remove_locked_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        if channel.id not in locked_channels:
            await interaction.response.send_message("<:disapprove:1517452151012589662> That channel is not configured as locked.", ephemeral=True)
            return
        locked_channels.pop(channel.id, None)
        save_lock_config(locked_channels, admin_log_channels)
        await interaction.response.send_message(f"<:trash:1517497581058527404> Removed locked channel {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

class ChannelEditChoiceView(discord.ui.View):
    def __init__(self, user_id: int, setting_name: str, on_add, on_remove, settings_message: discord.Message):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.setting_name = setting_name
        self.on_add = on_add
        self.on_remove = on_remove
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="channel_edit_add")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="channel_edit_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="channel_edit_cancel")
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
