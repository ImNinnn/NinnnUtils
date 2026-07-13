import discord

from . import *

class UserSettingsView(LayoutView):
    def __init__(self, user_id: int, current_color: str, current_pings: bool, current_style: str = "normal"):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.current_color = current_color or "white"
        self.current_pings = current_pings
        self.current_style = current_style if current_style in {"normal", "alt"} else "normal"
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.ping_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.secondary,
            custom_id="user_settings_pings",
        )

        async def ping_callback(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            self.current_pings = not self.current_pings
            user_settings["user_pings"] = self.current_pings
            save_user_settings(settings)
            await interaction.response.edit_message(view=UserSettingsView(self.user_id, self.current_color, self.current_pings, self.current_style))

        self.ping_button.callback = ping_callback

        self.color_select = discord.ui.Select(
            placeholder="Select a profile color",
            options=[
                discord.SelectOption(label=color.title(), value=color, description=f"Use the {color} color")
                for color in USER_COLOR_OPTIONS
            ],
            custom_id="user_color_select",
            min_values=1,
            max_values=1,
        )

        async def color_select_callback(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            self.current_color = self.color_select.values[0]
            user_settings["color"] = self.current_color
            save_user_settings(settings)
            await interaction.response.edit_message(view=UserSettingsView(self.user_id, self.current_color, self.current_pings, self.current_style))

        self.color_select.callback = color_select_callback

        self.banner_style_button = discord.ui.Button(
            label=f"Switch to {'Alternate' if self.current_style == 'normal' else 'Normal'}",
            style=discord.ButtonStyle.secondary,
            custom_id="user_banner_style_toggle",
        )

        async def banner_style_button_callback(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            self.current_style = "alt" if self.current_style == "normal" else "normal"
            user_settings["banner_style"] = self.current_style
            save_user_settings(settings)
            await interaction.response.edit_message(view=UserSettingsView(self.user_id, self.current_color, self.current_pings, self.current_style))

        self.banner_style_button.callback = banner_style_button_callback



        self.back_button = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="user_settings_back")

        async def back_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

        self.back_button.callback = back_callback

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **User settings**"),
            TextDisplay("Adjust your personal preferences below."),
            Separator(),
            Section(f"<:bell:1517497562184024275> Ping notifications: {'Enabled' if self.current_pings else 'Disabled'}", accessory=self.ping_button),
            Section(
                f"<:frames:1517497568421085256> Banner style: {self.current_style.title()}",
                accessory=self.banner_style_button,
            ),
            TextDisplay(f"<:rainbow:1518708398772846722> User color: {COLOR_EMOJIS.get(self.current_color, self.current_color)} {self.current_color.title()}"),
            accent_color=get_user_color_value(str(self.user_id)),
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.color_select))
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True
