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

            new_view = GuildSettingsMenuView(
                interaction.user.id,
                str(interaction.guild.id),
            )
            await interaction.response.edit_message(view=new_view)

        self.user_button.callback = open_user
        self.guild_button.callback = open_guild

        container = Container(
            TextDisplay(f"<:gear:1517576939097952496> **Settings for {self.username}**"),
            Separator(),
            Section("<:edit:1517497568421085256> User settings", accessory=self.user_button),
            Section("<:drawer:1517497564189036574> Guild settings", accessory=self.guild_button),
            Separator(),
            TextDisplay("Found a bug ? Report it in the [support server](https://discord.gg/FSBPvc9zqY)"),
            accent_color=self.color,
        )
        self.add_item(container)
