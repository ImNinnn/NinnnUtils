from . import *

class ConfirmRemoveView(discord.ui.View):
    def __init__(self, user_id: int, confirm_callback, original_message: discord.Message):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.confirm_callback = confirm_callback
        self.original_message = original_message
        self.confirm_button = Button(label="Confirm", style=discord.ButtonStyle.danger, custom_id="confirm_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_remove")
        self.confirm_button.callback = self.on_confirm
        self.cancel_button.callback = self.on_cancel
        self.add_item(self.confirm_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This confirmation is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_confirm(self, interaction: discord.Interaction):
        self.confirm_button.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
        await self.confirm_callback(interaction, self.original_message)

    async def on_cancel(self, interaction: discord.Interaction):
        self.confirm_button.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
