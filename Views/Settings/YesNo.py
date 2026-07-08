from . import *

class YesNoView(discord.ui.View):
    def __init__(self, user_id: int, yes_callback, no_callback):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.yes_callback = yes_callback
        self.no_callback = no_callback
        self.yes_button = Button(label="Yes", style=discord.ButtonStyle.success, custom_id="yes_option")
        self.no_button = Button(label="No", style=discord.ButtonStyle.danger, custom_id="no_option")
        self.yes_button.callback = self.on_yes
        self.no_button.callback = self.on_no
        self.add_item(self.yes_button)
        self.add_item(self.no_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_yes(self, interaction: discord.Interaction):
        self.yes_button.disabled = True
        self.no_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
        await self.yes_callback(interaction)

    async def on_no(self, interaction: discord.Interaction):
        self.yes_button.disabled = True
        self.no_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
        await self.no_callback(interaction)
