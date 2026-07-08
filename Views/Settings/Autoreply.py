from . import *

class AutoReplyAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add auto reply")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.word_input = TextInput(label="Trigger word", placeholder="Enter the trigger word", required=True, max_length=100)
        self.reply1 = TextInput(label="Reply 1", placeholder="First reply", required=True, max_length=200)
        self.reply2 = TextInput(label="Reply 2", placeholder="Second reply (optional)", required=False, max_length=200)
        self.reply3 = TextInput(label="Reply 3", placeholder="Third reply (optional)", required=False, max_length=200)
        self.reply4 = TextInput(label="Reply 4", placeholder="Fourth reply (optional)", required=False, max_length=200)
        self.add_item(self.word_input)
        self.add_item(self.reply1)
        self.add_item(self.reply2)
        self.add_item(self.reply3)
        self.add_item(self.reply4)

    async def on_submit(self, interaction: discord.Interaction):
        replies = [value for value in [self.reply1.value, self.reply2.value, self.reply3.value, self.reply4.value] if value]
        await self.callback(
            interaction,
            self.word_input.value.strip(),
            replies,
            self.settings_message,
        )

class AutoReplyRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove auto reply")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.word_input = TextInput(label="Trigger word to remove", placeholder="Enter the exact trigger word", required=True, max_length=100)
        self.add_item(self.word_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(
            interaction,
            self.word_input.value.strip(),
            self.settings_message,
        )

class AutoReplyChoiceView(discord.ui.View):
    def __init__(self, user_id: int, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="auto_reply_add")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="auto_reply_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="auto_reply_cancel")
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
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
