"""Music feature module."""

import discord
from discord import app_commands
from discord.ext import commands

import helper as main


class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api = main

    @app_commands.command(name='song', description='Play a song or open the current queue UI')
    @app_commands.describe(query='Song name or URL to play')
    @app_commands.allowed_installs(guilds=True, users=False)
    async def song(self, interaction: discord.Interaction, query: str | None = None):
        await main.song.callback(interaction, query)

    @app_commands.command(name='voice-leave', description='Leave the current voice channel')
    @app_commands.allowed_installs(guilds=True, users=False)
    async def voice_leave(self, interaction: discord.Interaction):
        await main.voice_leave.callback(interaction)


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
