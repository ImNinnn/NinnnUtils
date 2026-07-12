from datetime import datetime

import discord
from discord.ui import Button


class WarnsAdminView(discord.ui.View):
    def __init__(self, author_id: int, member: discord.Member, warnings: list[dict], page: int = 0, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.member = member
        self.warnings = warnings
        self.page = page
        self.items_per_page = 10

        self.prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary)
        self.next_button = Button(label="Next", style=discord.ButtonStyle.secondary)
        self.close_button = Button(label="Close", style=discord.ButtonStyle.danger)

        self.prev_button.callback = self.previous_page
        self.next_button.callback = self.next_page
        self.close_button.callback = self.close_view

        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.add_item(self.close_button)
        self.update_buttons()

    def update_buttons(self) -> None:
        total_pages = max(1, (len(self.warnings) + self.items_per_page - 1) // self.items_per_page)
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= total_pages - 1

    def get_page_embed(self) -> discord.Embed:
        total_warnings = len(self.warnings)
        total_pages = max(1, (total_warnings + self.items_per_page - 1) // self.items_per_page)
        page = min(max(self.page, 0), total_pages - 1)
        start = page * self.items_per_page
        end = start + self.items_per_page
        page_warnings = self.warnings[start:end]

        embed = discord.Embed(
            title=f"Warnings for {self.member.display_name}",
            description=f"Total warnings: **{total_warnings}**",
            color=discord.Color.orange()
        )

        for index, warn_entry in enumerate(page_warnings, start=start + 1):
            raw_timestamp = warn_entry.get("timestamp")
            timestamp = "Unknown time"
            if raw_timestamp:
                try:
                    dt = datetime.fromisoformat(raw_timestamp)
                    timestamp = discord.utils.format_dt(dt, style="f")
                except Exception:
                    timestamp = raw_timestamp
            reason = warn_entry.get("reason", "No reason provided")
            moderator = warn_entry.get("moderator_name", "Unknown moderator")
            embed.add_field(
                name=f"Warn {index}",
                value=f"**Reason:** {reason}\n**Moderator:** {moderator}\n**Time:** {timestamp}",
                inline=False
            )

        embed.set_footer(text=f"Page {page + 1}/{total_pages}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("<:disapprove:1517452151012589462> Only the command user can navigate these pages.", ephemeral=True)
            return False
        return True

    async def previous_page(self, interaction: discord.Interaction) -> None:
        self.page = max(0, self.page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction) -> None:
        total_pages = max(1, (len(self.warnings) + self.items_per_page - 1) // self.items_per_page)
        self.page = min(total_pages - 1, self.page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    async def close_view(self, interaction: discord.Interaction) -> None:
        self.prev_button.disabled = True
        self.next_button.disabled = True
        self.close_button.disabled = True
        await interaction.response.edit_message(view=self)
