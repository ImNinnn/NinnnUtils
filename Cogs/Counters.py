from discord.ext.commands import Cog, Context, hybrid_group
from discord import app_commands
import discord

from Shared.Counters import set_counter_value

async def setup(bot):
    await bot.add_cog(Counters(bot))

class Counters(Cog):
    @hybrid_group(name="counter", description="Counter management commands", invoke_without_command=True)
    async def c(self, ctx): pass

    @hybrid_group(name="number", description="Number management", invoke_without_command=True)
    async def n(self, ctx): pass

    @n.command(name="set", description="Set the current count in a counter channel")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        channel="The counter channel to update",
        value="The new current count value"
    )
    async def counter_number_set(self, ctx: Context, channel: discord.TextChannel, value: int):
        success = set_counter_value(str(ctx.guild.id), channel.id, value)
        if success:
            await ctx.send(
                f"<:approve:1517452125687513158> Counter in {channel.mention} is now set to {value}.", ephemeral=False)
        else:
            await ctx.send(
                f"<:warning:1517452174991556758> That channel does not have an active counter.", ephemeral=True)
