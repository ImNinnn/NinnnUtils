from . import *

class BoardCountPromptView(discord.ui.View):
    def __init__(self, user_id: int, channel: discord.abc.GuildChannel, emoji: str, settings_message: discord.Message, callback):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.channel = channel
        self.emoji = emoji
        self.settings_message = settings_message
        self.callback = callback
        self.count_button = Button(label="Set required count", style=discord.ButtonStyle.primary, custom_id="board_set_count")
        self.count_button.callback = self.on_set_count
        self.add_item(self.count_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_set_count(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BoardCountModal(self.callback, self.channel, self.emoji, self.settings_message))

class BoardCountModal(Modal):
    def __init__(self, callback, channel: discord.abc.GuildChannel, emoji: str, settings_message: discord.Message):
        super().__init__(title="Board required count")
        self.callback = callback
        self.channel = channel
        self.emoji = emoji
        self.settings_message = settings_message
        self.count_input = TextInput(label="Required count", placeholder="How many reactions are required?", required=True, max_length=10)
        self.add_item(self.count_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            required_count = int(self.count_input.value)
        except ValueError:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Required count must be a number.", ephemeral=True)
            return
        await self.callback(interaction, self.channel, self.emoji, required_count, self.settings_message)
