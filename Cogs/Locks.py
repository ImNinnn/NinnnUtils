from discord.ext.commands import Cog, Context, hybrid_group
from discord import app_commands
import discord

async def setup(bot):
    await bot.add_cog(Locks(bot))

class Locks(Cog):
    """STUB"""