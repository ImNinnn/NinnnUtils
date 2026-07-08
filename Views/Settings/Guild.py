from . import *

class GuildSettingsView(LayoutView):
    def __init__(self, user_id: int, guild_id: str, ghost_pings: bool, history_enabled: bool, level_up_enabled: bool, bot):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.ghost_pings = ghost_pings
        self.history_enabled = history_enabled
        self.level_up_enabled = level_up_enabled
        self.color = get_user_color_value(str(user_id))
        self.bot = bot
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.ghost_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_ghost_pings",
        )
        self.history_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_history",
        )
        self.level_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_level_up",
        )
        self.auto_reply_button = discord.ui.Button(
            label="Edit",
            style=discord.ButtonStyle.primary,
            custom_id="guild_auto_reply",
        )

        fun_data = load_fun_data()
        auto_reply_triggers = sorted(fun_data.get(self.guild_id, {}).keys()) if self.guild_id in fun_data else []
        auto_reply_text = "\n".join(auto_reply_triggers) if auto_reply_triggers else "None"

        async def ghost_callback(interaction: discord.Interaction):
            guild_config, data = get_guild_config(self.guild_id)
            self.ghost_pings = not self.ghost_pings
            guild_config["ghost_ping_enabled"] = self.ghost_pings
            save_guild_data(data)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.level_up_enabled))

        async def history_callback(interaction: discord.Interaction):
            guild_config, data = get_guild_config(self.guild_id)
            self.history_enabled = not self.history_enabled
            guild_config["edit_delete_history_enabled"] = self.history_enabled
            save_guild_data(data)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.level_up_enabled))

        async def level_callback(interaction: discord.Interaction):
            guild_config, guild_data = get_guild_config(self.guild_id)
            levels = load_levels()
            if self.guild_id not in levels:
                levels[self.guild_id] = {"config": {}}
            config = levels[self.guild_id].get("config", {})

            self.level_up_enabled = not self.level_up_enabled
            guild_config["level_up_message_enabled"] = self.level_up_enabled
            save_guild_data(guild_data)

            config["level_up_message_enabled"] = self.level_up_enabled
            levels[self.guild_id]["config"] = config
            save_levels(levels)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.level_up_enabled))

        self.ghost_button.callback = ghost_callback
        self.history_button.callback = history_callback
        self.level_button.callback = level_callback
        self.auto_reply_button.callback = self.handle_auto_reply_edit

        self.back_button = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="guild_settings_back")

        async def back_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

        self.back_button.callback = back_callback

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **Guild settings**"),
            TextDisplay("Adjust guild-wide behavior below."),
            Separator(),
            Section(f"<:ghost:1517497569939558470> Ghost pings: {'Enabled' if self.ghost_pings else 'Disabled'}", accessory=self.ghost_button),
            Section(f"<:trash:1517497581058527404> Edit/Delete history: {'Enabled' if self.history_enabled else 'Disabled'}", accessory=self.history_button),
            Section(f"<:chalice:1517579767573123092> Level-up messages: {'Enabled' if self.level_up_enabled else 'Disabled'}", accessory=self.level_button),
            Section(f"<:spark:1517583248421552305> Auto-reply triggers\n{auto_reply_text}", accessory=self.auto_reply_button),
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

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
            channel = self.bot.get_channel(settings_message.channel.id)
            if channel is not None:
                settings_message = await channel.fetch_message(settings_message.id)
                await settings_message.edit(view=view)
                return
        except Exception:
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

    async def get_settings_message(self, channel_id: int, message_id: int) -> discord.Message | None:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return None

        try:
            return await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def handle_auto_reply_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message or await interaction.original_response()
        if settings_message is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Unable to determine the settings message.", ephemeral=True)
            return

        await interaction.response.send_message(
            "What would you like to do with Auto-reply triggers?",
            view=AutoReplyChoiceView(
                self.user_id,
                self.open_auto_reply_add,
                self.open_auto_reply_remove,
                settings_message,
            ),
            ephemeral=True,
        )

    async def open_auto_reply_add(self, interaction: discord.Interaction, settings_message: discord.Message | None):
        await interaction.response.send_modal(AutoReplyAddModal(self.add_auto_reply, self.guild_id, settings_message))

    async def open_auto_reply_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None):
        await interaction.response.send_modal(AutoReplyRemoveModal(self.remove_auto_reply, self.guild_id, settings_message))

    async def add_auto_reply(self, interaction: discord.Interaction, word: str, replies: list[str], settings_message: discord.Message | None):
        fun_data = load_fun_data()
        if self.guild_id not in fun_data:
            fun_data[self.guild_id] = {}
        fun_data[self.guild_id][word.lower()] = replies
        save_fun_data(fun_data)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Auto reply for '{word}' saved.", ephemeral=True)

        await self.refresh_settings_message(
            interaction,
            GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.level_up_enabled),
            settings_message,
        )

    async def remove_auto_reply(self, interaction: discord.Interaction, word: str, settings_message: discord.Message | None):
        fun_data = load_fun_data()
        if self.guild_id in fun_data and word.lower() in fun_data[self.guild_id]:
            del fun_data[self.guild_id][word.lower()]
            if not fun_data[self.guild_id]:
                del fun_data[self.guild_id]
            save_fun_data(fun_data)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Auto reply for '{word}' removed.", ephemeral=True)

            await self.refresh_settings_message(
                interaction,
                GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.level_up_enabled),
                settings_message,
            )
        else:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> No auto reply found for '{word}'.", ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True
