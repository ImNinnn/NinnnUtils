from discord.ext.commands import Cog, hybrid_command, Context
import discord
from discord import app_commands

from Shared.User import get_user_color_value
from Views.Settings import SettingsMenuView


async def setup(bot):
    await bot.add_cog(Settings(bot))

class Settings(Cog):
    def __init__(self, bot):
        self.bot = bot

    @hybrid_command(name="settings", description="Open a quick settings menu for your personal and guild preferences")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def settings(self, ctx: Context):
        view = SettingsMenuView(
            ctx.author.id,
            ctx.author.display_name,
            get_user_color_value(str(ctx.author.id)),
        )
        await ctx.send(view=view, ephemeral=True)
