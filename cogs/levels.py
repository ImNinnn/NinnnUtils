"""Level progression commands and XP loop."""

import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

import helper as main


class LevelsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api = main

    def start_tasks(self):
        if not self.voice_xp_tracker.is_running():
            self.voice_xp_tracker.start()

    @tasks.loop(minutes=2.0)
    async def voice_xp_tracker(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            for voice_channel in guild.voice_channels:
                real_members = [
                    member for member in voice_channel.members
                    if not member.bot and not member.voice.self_deaf and not member.voice.deaf
                ]
                if len(real_members) < 1:
                    continue
                for member in real_members:
                    await main.add_xp(member, guild, random.randint(5, 10))

    @voice_xp_tracker.before_loop
    async def before_voice_xp_tracker(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name='level', description='View your current server tier standing level rank card')
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(user='Optional member to inspect')
    async def level(self, interaction: discord.Interaction, user: discord.Member | None = None):
        await main.view_level.callback(interaction, user)

    @app_commands.command(name='level-leaderboard', description='Display the top 10 highest-level users in this guild')
    @app_commands.allowed_installs(guilds=True, users=False)
    async def level_leaderboard(self, interaction: discord.Interaction):
        await main.level_leaderboard.callback(interaction)

    @app_commands.command(name='level-edit', description='Manually adjust or set a target user\'s level and XP indexes')
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def level_edit(self, interaction: discord.Interaction, user: discord.Member, level: int, xp: int = 0):
        await main.lvl_edit.callback(interaction, user, level, xp)

    @app_commands.command(name='rewards_info', description='Show the level rewards configured for this guild')
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(level='Optional specific level to inspect')
    async def rewards_info(self, interaction: discord.Interaction, level: int | None = None):
        await main.info_lvl_rewards.callback(interaction, level)


async def setup(bot):
    await bot.add_cog(LevelsCog(bot))
