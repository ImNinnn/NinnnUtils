from . import *

class ChannelSelectorView(discord.ui.View):
    def __init__(self, user_id: int, guild: discord.Guild, placeholder: str, callback, settings_message: discord.Message):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild = guild
        self.callback = callback
        self.settings_message = settings_message
        self.channel_select = ChannelSelect(placeholder=placeholder, custom_id="channel_selector", min_values=1, max_values=1)
        self.channel_select.callback = self.on_channel_selected
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="channel_select_cancel")
        self.cancel_button.callback = self.on_cancel
        self.add_item(self.channel_select)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_channel_selected(self, interaction: discord.Interaction):
        if not self.channel_select.values:
            await interaction.response.send_message("<:disapprove:1517452151012589662> No channel was selected.", ephemeral=True)
            return

        channel = self.channel_select.values[0]
        self.channel_select.disabled = True
        self.cancel_button.disabled = True
        await self.callback(interaction, channel, self.settings_message)
        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass

    async def on_cancel(self, interaction: discord.Interaction):
        self.channel_select.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(content="Channel selection cancelled.", view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
