from . import *

class SettingsMenuView(LayoutView):
    def __init__(self, user_id: int, username: str, color: discord.Color):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.username = username
        self.color = color
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.user_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="settings_open_user",
        )
        self.guild_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="settings_open_guild",
        )
        self.channel_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="settings_open_channel",
        )
        self.economy_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="settings_open_economy",
        )
        self.level_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="settings_open_level",
        )

        async def open_user(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            new_view = UserSettingsView(
                interaction.user.id,
                current_color=user_settings.get("color", "white"),
                current_pings=user_settings.get("user_pings", True),
            )
            await interaction.response.edit_message(view=new_view)

        async def open_guild(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use guild settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            guild_id = str(interaction.guild.id)
            guild_config, _ = get_guild_config(guild_id)
            new_view = GuildSettingsView(
                interaction.user.id,
                guild_id,
                ghost_pings=guild_config.get("ghost_ping_enabled", False),
                history_enabled=guild_config.get("edit_delete_history_enabled", True),
                level_up_enabled=guild_config.get("level_up_message_enabled", False),
            )
            await interaction.response.edit_message(view=new_view)

        async def open_channel_settings(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use channel settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_channels:
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Channels permission.",
                    ephemeral=True,
                )
                return

            guild_id = str(interaction.guild.id)
            new_view = ChannelSettingsView(
                interaction.user.id,
                guild_id,
                get_user_color_value(str(interaction.user.id)),
            )
            await interaction.response.edit_message(view=new_view)

        async def open_economy_settings(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use economy settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            guild_id = str(interaction.guild.id)
            new_view = EconomySettingsView(
                interaction.user.id,
                guild_id,
                get_user_color_value(str(interaction.user.id)),
            )
            await interaction.response.edit_message(view=new_view)

        async def open_level_settings(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use level settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            guild_id = str(interaction.guild.id)
            new_view = LevelSettingsView(
                interaction.user.id,
                guild_id,
                get_user_color_value(str(interaction.user.id)),
                settings_message=interaction.message,
            )
            await interaction.response.edit_message(view=new_view)

        self.user_button.callback = open_user
        self.guild_button.callback = open_guild
        self.channel_button.callback = open_channel_settings
        self.economy_button.callback = open_economy_settings
        self.level_button.callback = open_level_settings

        container = Container(
            TextDisplay(f"<:gear:1517576939097952496> **Settings for {self.username}**"),
            Separator(),
            Section("<:edit:1517497568421085256> User settings", accessory=self.user_button),
            Section("<:drawer:1517497564189036574> Guild settings", accessory=self.guild_button),
            Section("<:list:1517497572770451567> Channel settings", accessory=self.channel_button),
            Section("<:money:1517580310395486239> Economy settings", accessory=self.economy_button),
            Section("<:chalice:1517579767573123092> Level settings", accessory=self.level_button),
            Separator(),
            TextDisplay("Found a bug ? Report it in the [support server](https://discord.gg/FSBPvc9zqY)"),
            accent_color=self.color,
        )
        self.add_item(container)
