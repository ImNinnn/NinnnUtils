"""Moderation, audit logging, and moderation-history commands."""

import discord
from discord import app_commands
from discord.ext import commands

import helper as main


class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api = main

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        await main.on_message_delete(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        await main.on_message_edit(before, after)

    @app_commands.command(name='purge_adm', description='Mass delete messages from the channel')
    @app_commands.describe(amount='Number of messages to remove', user='Optional user filter')
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def purge_adm(self, interaction: discord.Interaction, amount: int, user: discord.Member | None = None):
        await main.purge.callback(interaction, amount, user)

    @app_commands.command(name='timeout_adm', description='Timeout a member for a specific duration')
    @app_commands.describe(member='Member to timeout', days='Days', hours='Hours', minutes='Minutes', seconds='Seconds', reason='Reason')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def timeout_adm(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        reason: str = 'No reason provided',
    ):
        await main.timeout.callback(interaction, member, days, hours, minutes, seconds, reason)

    @app_commands.command(name='slowmode_adm', description='Set channel slowmode (up to 6 hours)')
    @app_commands.describe(seconds='Seconds', minutes='Minutes', hours='Hours', channel='Channel to update')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def slowmode_adm(
        self,
        interaction: discord.Interaction,
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
        channel: discord.TextChannel | None = None,
    ):
        await main.slowmode.callback(interaction, seconds, minutes, hours, channel)

    @app_commands.command(name='kick_adm', description='Kick a member from the server')
    @app_commands.describe(member='Member to kick', reason='Kick reason')
    @app_commands.default_permissions(kick_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def kick_adm(self, interaction: discord.Interaction, member: discord.Member | None = None, reason: str = 'No reason provided'):
        await main.kick.callback(interaction, member, reason)

    @app_commands.command(name='ban_adm', description='Ban a member from the server')
    @app_commands.describe(member='Member to ban', reason='Ban reason', delete_days='Messages to delete from the past x days')
    @app_commands.default_permissions(ban_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def ban_adm(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        reason: str = 'No reason provided',
        delete_days: int = 0,
    ):
        await main.ban.callback(interaction, member, reason, delete_days)

    @app_commands.command(name='warn_adm', description='Add or remove a warning for a user')
    @app_commands.describe(user='User to warn', reason='Warning reason', remove='Remove a warning instead of adding one')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def warn_adm(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = 'No reason provided',
        remove: bool = False,
    ):
        await main.warn_adm.callback(interaction, user, reason, remove)

    @app_commands.command(name='warns_adm', description='Show warnings for a user')
    @app_commands.describe(user='User to inspect')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def warns_adm(self, interaction: discord.Interaction, user: discord.Member):
        await main.warns_adm.callback(interaction, user)

    @app_commands.command(name='deleted', description='View recently deleted messages and media')
    @app_commands.describe(user='Optional user filter')
    @app_commands.allowed_installs(guilds=True, users=False)
    async def deleted(self, interaction: discord.Interaction, user: discord.Member | None = None):
        await main.deleted.callback(interaction, user)

    @app_commands.command(name='edited', description='Show recently edited messages in this channel')
    @app_commands.describe(user='Optional user filter')
    @app_commands.allowed_installs(guilds=True, users=False)
    async def edited(self, interaction: discord.Interaction, user: discord.Member | None = None):
        await main.edited_command.callback(interaction, user)

    @app_commands.command(name='where-ping', description='Show where a user has been pinged recently')
    @app_commands.describe(user='The user to look up')
    @app_commands.allowed_installs(guilds=True, users=False)
    async def where_ping(self, interaction: discord.Interaction, user: discord.Member | None = None):
        await main.where_ping.callback(interaction, user)

    @app_commands.command(name='errors', description='Show recent bot errors in this server')
    @app_commands.allowed_installs(guilds=True, users=False)
    async def errors(self, interaction: discord.Interaction):
        await main.errors.callback(interaction)

    @app_commands.command(name='forget', description="Clear your messages from the bot's memory")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def forget(self, interaction: discord.Interaction):
        await main.forget.callback(interaction)

    @app_commands.command(name='forget_adm', description="Clear edited and deleted history of a chosen user")
    @app_commands.describe(user='User whose history should be cleared')
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def forget_adm(self, interaction: discord.Interaction, user: discord.Member):
        await main.adm_forget.callback(interaction, user)

    @app_commands.command(name='voice-move_adm', description='Move a member to another voice channel')
    @app_commands.describe(channel='Voice channel to move the user to')
    @app_commands.default_permissions(move_members=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def voice_move_adm(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        await main.adm_voice_move.callback(interaction, channel)

    @app_commands.command(name='rename_adm', description='Rename a user or reset their nickname')
    @app_commands.describe(user='User to rename', name='New nickname to set (leave empty to reset)')
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def rename_adm(self, interaction: discord.Interaction, user: discord.Member, name: str | None = None):
        await main.rename.callback(interaction, user, name)

    @app_commands.command(name='purge-nuke_adm', description='Fully clear a channel')
    @app_commands.describe(archive='Archive the channel before deleting it')
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def purge_nuke_adm(self, interaction: discord.Interaction, archive: bool = False):
        await main.nuke.callback(interaction, archive)

    @app_commands.command(name='role_adm', description='Give or remove a role from a user')
    @app_commands.describe(action='Whether to add or remove the role', member='Member to update', role='Role to add or remove', reason='Reason for this role change')
    @app_commands.choices(action=[app_commands.Choice(name='Add', value='add'), app_commands.Choice(name='Remove', value='remove')])
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def role_adm(self, interaction: discord.Interaction, action: str, member: discord.Member, role: discord.Role, reason: str = 'No reason provided'):
        await main.role_adm.callback(interaction, action, member, role, reason)

    @app_commands.command(name='temp-role_adm', description='Grant or remove a temporary role from a user')
    @app_commands.describe(action='Whether to grant or remove the temporary role', member='The user to update', role='The temporary role to grant or remove', duration='How long the temporary role should last (for example 30m, 2h, 1d)', reason='Why this temporary role change is being made')
    @app_commands.choices(action=[app_commands.Choice(name='Grant', value='grant'), app_commands.Choice(name='Remove', value='remove')])
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def temp_role_adm(self, interaction: discord.Interaction, action: str, member: discord.Member, role: discord.Role, duration: str | None = None, reason: str = 'No reason provided'):
        await main.temp_role_adm.callback(interaction, action, member, role, duration, reason)

    @app_commands.command(name='role-for_adm', description='Add or remove a role from all members who have a target role')
    @app_commands.describe(action='Whether to add or remove the role', role='The role to add or remove', target_role='The role filter; members with this role will be affected (use @everyone for everyone)')
    @app_commands.choices(action=[app_commands.Choice(name='Add', value='add'), app_commands.Choice(name='Remove', value='remove')])
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def role_for_adm(self, interaction: discord.Interaction, action: str, role: discord.Role, target_role: discord.Role):
        await main.adm_role_for.callback(interaction, action, role, target_role)

    @app_commands.command(name='giveaway_adm', description='Create or cancel a giveaway')
    @app_commands.describe(action='Create or cancel a giveaway', name='The giveaway title', winners='How many winners to select', time='How long the giveaway lasts (e.g. 1h, 30m, 2d)', role='Optional role to award to winners', temp_role='Optional temporary role to award to winners', temp_role_time='Temporary role duration in minutes', item='Optional item reward', money='Optional money reward', xp='Optional XP reward')
    @app_commands.choices(action=[app_commands.Choice(name='Create', value='create'), app_commands.Choice(name='Cancel', value='cancel')])
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def giveaway_adm(self, interaction: discord.Interaction, action: str, name: str | None = None, winners: int = 1, time: str | None = None, role: discord.Role | None = None, temp_role: discord.Role | None = None, temp_role_time: int = 0, item: str | None = None, money: int = 0, xp: int = 0):
        await main.adm_giveaway.callback(interaction, action, name, winners, time, role, temp_role, temp_role_time, item, money, xp)


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
