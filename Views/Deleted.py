import discord
from discord.ui import LayoutView, MediaGallery, TextDisplay, Separator, Container, Button

from LowerLeveled.timestamp import discord_timestamp


class DeletedMessagesView(LayoutView):
    def __init__(self, full_description: str, media_messages: list, requester):
        super().__init__(timeout=60)
        self.full_description = full_description
        self.messages = media_messages
        self.requester = requester
        self.index = 0
        self.revealed = False
        self.build_components()

    def build_components(self):
        self.clear_items()

        body = self.full_description
        gallery = None

        if self.messages:
            current_msg = self.messages[self.index]
            content_text = current_msg.get('content') or "*[Media only]*"
            media_text = current_msg['media'] if self.revealed else "Media hidden. Press Reveal Media to view."
            body += (
                f"\n\n---\n\n"
                f"**Current media preview ({self.index + 1}/{len(self.messages)})**\n"
                f"**{current_msg['author'].display_name}**: {content_text}\n"
                f"-# Sent at {current_msg['created_at']}\n"
                f"-# {media_text}"
            )

            if self.revealed:
                gallery = MediaGallery()
                gallery.add_item(media=current_msg['media'], description=f"{current_msg['author'].display_name} - deleted at {discord_timestamp(current_msg['created_at'])}")

        container_items = [
            TextDisplay("<:trash:1517497581058527404> Recent deleted messages"),
            Separator(),
            TextDisplay(body),
        ]
        if gallery is not None:
            container_items.extend([Separator(), gallery])

        container = Container(
            *container_items,
            accent_color=discord.Color.red(),
        )
        self.add_item(container)

        if self.messages:
            self.reveal_button = Button(label="Reveal Media", style=discord.ButtonStyle.danger, custom_id="deleted_media_reveal")
            self.prev_button = Button(label="Previous media", style=discord.ButtonStyle.primary, custom_id="deleted_media_prev")
            self.next_button = Button(label="Next media", style=discord.ButtonStyle.primary, custom_id="deleted_media_next")

            async def reveal_callback(interaction: discord.Interaction):
                if interaction.user != self.requester:
                    await interaction.response.send_message("<:disapprove:1517452151012589662> Only the person who ran the command can reveal media!", ephemeral=True)
                    return
                self.revealed = not self.revealed
                self.build_components()
                await interaction.response.edit_message(view=self)

            async def prev_callback(interaction: discord.Interaction):
                if interaction.user != self.requester:
                    await interaction.response.send_message("<:disapprove:1517452151012589662> Only the person who ran the command can flip pages!", ephemeral=True)
                    return
                if self.index > 0:
                    self.index -= 1
                    self.build_components()
                    await interaction.response.edit_message(view=self)

            async def next_callback(interaction: discord.Interaction):
                if interaction.user != self.requester:
                    await interaction.response.send_message("<:disapprove:1517452151012589662> Only the person who ran the command can flip pages!", ephemeral=True)
                    return
                if self.index < len(self.messages) - 1:
                    self.index += 1
                    self.build_components()
                    await interaction.response.edit_message(view=self)

            self.reveal_button.callback = reveal_callback
            self.prev_button.callback = prev_callback
            self.next_button.callback = next_callback
            self.update_button_states()
            self.add_item(discord.ui.ActionRow(self.prev_button, self.reveal_button, self.next_button))

    def update_button_states(self):
        self.prev_button.disabled = (self.index == 0)
        self.next_button.disabled = (self.index == len(self.messages) - 1)
        if self.revealed:
            self.reveal_button.label = "Hide Media"
            self.reveal_button.style = discord.ButtonStyle.secondary
        else:
            self.reveal_button.label = f"Reveal Media ({self.index + 1}/{len(self.messages)})"
            self.reveal_button.style = discord.ButtonStyle.danger

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if hasattr(self, 'message'):
                await self.message.edit(view=self)
        except Exception:
            pass
