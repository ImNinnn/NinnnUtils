from discord.ext.commands import Cog, Context, hybrid_group, has_permissions, hybrid_command
from discord import app_commands
import discord

from Shared.Locks import save_lock_config
from main import locked_channels, admin_log_channels, all_paused_guilds, server_pauses


async def setup(bot):
    await bot.add_cog(Locks(bot))

class Locks(Cog):
    """STUB"""

    @Cog.listener()
    async def on_guild_channel_delete(self, channel):
        changed = False

        if channel.id in locked_channels:
            locked_channels.pop(channel.id)
            changed = True

        if channel.id in admin_log_channels:
            admin_log_channels.pop(channel.id)
            changed = True

        if changed:
            save_lock_config(locked_channels, admin_log_channels)

    @hybrid_group(name="locks", description="Lock channel management", invoke_without_command=True)
    @app_commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_guild=True)
    @has_permissions(manage_guild=True)
    async def l(self, ctx): pass

    @l.command(name="add", description="Lock this channel - messages will be logged and deleted.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_guild=True)
    @has_permissions(manage_guild=True)
    async def lock_command(self, ctx: Context):
        locked_channels[ctx.channel.id] = True
        save_lock_config(locked_channels, admin_log_channels)
        await ctx.send(f"<:locked:1517574877257924809> Channel locked.")

    @l.command(name="remove", description="Unlock this channel.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_guild=True)
    @has_permissions(manage_guild=True)
    async def unlock_command(self, ctx: Context):
        if ctx.channel.id in locked_channels:
            locked_channels.pop(ctx.channel.id)
            save_lock_config(locked_channels, admin_log_channels)
            await ctx.send("<:unlocked:1517574880034558102> Channel unlocked.")
        else:
            await ctx.send(
                "<:warning:1517452174991556758> This channel is not currently locked.", ephemeral=True)

    @l.command(name="pause", description="Pause message deletion for this channel or all locked channels.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_guild=True)
    @has_permissions(manage_guild=True)
    async def pause_command(self, ctx: Context, channel: discord.TextChannel = None):
        guild_id = ctx.guild.id
        if channel is None:
            all_paused_guilds.add(guild_id)
            await ctx.send(
                "<:pause:1517497575219920986> Message deletion paused for all locked channels in this server.")
            return
        if guild_id not in server_pauses:
            server_pauses[guild_id] = set()
        server_pauses[guild_id].add(channel.id)
        await ctx.send(
            f"<:pause:1517497575219920986> Message deletion paused for {channel.mention}.")

    @l.command(name="resume",
                      description="Resume message deletion for this channel or all locked channels.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_guild=True)
    async def resume_command(self, ctx: Context, channel: discord.TextChannel = None):
        guild_id = ctx.guild.id
        if channel is None:
            all_paused_guilds.discard(guild_id)
            await ctx.send(
                "<:play:1517497576855965716> Message deletion resumed for all locked channels in this server.")
            return
        if guild_id not in server_pauses:
            server_pauses[guild_id] = set()
        server_pauses[guild_id].discard(channel.id)
        await ctx.send(
            f"<:play:1517497576855965716> Message deletion resumed for {channel.mention}.")

