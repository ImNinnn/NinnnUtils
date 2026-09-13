"""Uncategorized bot functionality."""

import helper as main
import discord
from discord import app_commands
from discord.ext import commands


class MiscCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api = main

    @app_commands.command(name='counter-number-set', description='Set the current count in a counter channel')
    @app_commands.describe(channel='The counter channel to update', value='The new current count value')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def counter_number_set(self, interaction: discord.Interaction, channel: discord.TextChannel, value: int):
        await main.counter_number_set.callback(interaction, channel, value)


async def setup(bot):
    await bot.add_cog(MiscCog(bot))
