import discord


class ServersListView(discord.ui.View):
    def __init__(self, author_id: int, guilds: list[discord.Guild], page: int = 0):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.guilds = guilds
        self.page = page
        self.guilds_per_page = 15

    def get_page_embed(self) -> discord.Embed:
        total_pages = max(1, (len(self.guilds) + self.guilds_per_page - 1) // self.guilds_per_page)
        page = min(max(self.page, 0), total_pages - 1)
        start = page * self.guilds_per_page
        end = start + self.guilds_per_page
        chunk = self.guilds[start:end]

        embed = discord.Embed(
            title="Bot Servers",
            description=f"Showing servers {start + 1}-{min(end, len(self.guilds))} of {len(self.guilds)}",
            color=discord.Color.blue(),
        )

        for guild in chunk:
            embed.add_field(
                name=guild.name,
                value=f"ID: `{guild.id}`\nMembers: {guild.member_count}",
                inline=False,
            )

        embed.set_footer(text=f"Page {page + 1}/{total_pages}")
        return embed

    async def update_message(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command owner can navigate these pages.", ephemeral=True)
            return
        self.page = max(0, self.page - 1)
        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command owner can navigate these pages.", ephemeral=True)
            return
        total_pages = max(1, (len(self.guilds) + self.guilds_per_page - 1) // self.guilds_per_page)
        self.page = min(total_pages - 1, self.page + 1)
        await self.update_message(interaction)
