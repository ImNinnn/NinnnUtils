from discord.ext.commands import Cog, Context, hybrid_command, hybrid_group
from discord import app_commands
import random

async def setup(bot):
    await bot.add_cog(Fun())

class Fun(Cog):
    @hybrid_command(name="roll", description="Roll a 6-sided die")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def roll(self, ctx: Context):
        result = random.randint(1, 6)
        await ctx.send(f"🎲 You rolled a **{result}**!")

    @hybrid_command(name="random", description="Pick a random number between two values")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(min_value="The lowest number", max_value="The highest number")
    async def random_cmd(self, ctx: Context, min_value: int, max_value: int):
        low, high = min(min_value, max_value), max(min_value, max_value)
        result = random.randint(low, high)
        await ctx.send(
            f"<:list:1517497572770451567> Your random number between **{low}** and **{high}** is: **{result}**"
        )

