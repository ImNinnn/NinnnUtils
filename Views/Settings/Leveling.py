from . import *

class LevelRoleSelectionView(discord.ui.View):
    def __init__(self, user_id: int, guild: discord.Guild, prompt: str, level: int, reward_data: dict, settings_message: discord.Message | None, callback, is_temp_role: bool):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Level, duration, money, and XP must be numbers.", ephemeral=True)
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


class LevelSettingsView(LayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color, settings_message: discord.Message | None = None):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.color = color
        self.settings_message = settings_message
        self.build_components()

    def build_components(self):
        self.clear_items()
        levels = load_levels()
        rewards = levels.get(self.guild_id, {}).get("config", {}).get("rewards", {})
        guild = bot.get_guild(int(self.guild_id)) if self.guild_id.isdigit() else None

        summary_lines = []
        for level_key, reward_data in sorted(rewards.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 999999)[:6]:
            summary_lines.append(f"Lvl {level_key}: {format_level_reward_summary(guild, level_key, reward_data) if guild else 'Configured'}")

        self.set_button = Button(label="Set reward", style=discord.ButtonStyle.primary, custom_id="level_settings_set")
        self.set_button.callback = self.handle_set
        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="level_settings_back")
        self.back_button.callback = self.handle_back

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **Level settings**"),
            TextDisplay("Configure level-based rewards below."),
            Separator(),
            Section("<:box:1517581439552585759> Current rewards\n" + ("\n".join(summary_lines) if summary_lines else "None"), accessory=self.set_button),
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View):
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
        await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

    async def handle_set(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LevelRewardModal(self.handle_reward_submit, self.guild_id, self.settings_message))

    async def handle_reward_submit(self, interaction: discord.Interaction, reward_data: dict, level: int, settings_message: discord.Message | None):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This can only be used in a server.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"<:approve:1517452125687513158> Level {level} reward details saved. Choose a role to grant when this level is reached. Press No to skip.",
            view=LevelRoleSelectionView(self.user_id, guild, "Choose a role", level, reward_data, settings_message, self.handle_level_role_selection, False),
            ephemeral=True,
        )

    async def handle_level_role_selection(self, interaction: discord.Interaction, reward_data: dict, level: int, settings_message: discord.Message | None, is_temp_role: bool):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This can only be used in a server.", ephemeral=True)
            return

        role_id = reward_data.get("temp_role_id" if is_temp_role else "role_id")
        role = guild.get_role(role_id) if role_id else None
        if role_id and role is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> The selected role is no longer available.", ephemeral=True)
            return

        role_error = validate_role_selection(interaction, role, "temporary role reward" if is_temp_role else "role reward")
        if role_error:
            await interaction.response.send_message(role_error, ephemeral=True)
            return

        if is_temp_role:
            save_level_reward_data(str(guild.id), level, reward_data)
            await interaction.response.send_message(f"<:approve:1517452125687513158> Level {level} reward saved.", ephemeral=True)
            await self.refresh_settings_message(interaction, LevelSettingsView(self.user_id, self.guild_id, self.color, settings_message=self.settings_message))
            return

        if role_id is None:
            await interaction.response.send_message(
                f"<:approve:1517452125687513158> Role setup skipped for level {level}. Choose a temporary role next, or press No to skip.",
                view=LevelRoleSelectionView(self.user_id, guild, "Choose a temporary role", level, reward_data, settings_message, self.handle_level_role_selection, True),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"<:approve:1517452125687513158> Role saved for level {level}. Choose a temporary role next, or press No to skip.",
            view=LevelRoleSelectionView(self.user_id, guild, "Choose a temporary role", level, reward_data, settings_message, self.handle_level_role_selection, True),
            ephemeral=True,
        )
