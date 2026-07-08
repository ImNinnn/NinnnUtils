import asyncio
import os, discord

from discord import app_commands
from discord.ext.commands import Cog, hybrid_command, Context
from dotenv import load_dotenv

from LowerLeveled.timestamp import discord_timestamp
from Shared.Cache import clean_cache
from Shared.Errors import add_bot_error_entry
from Shared.Owner import update_env_setting
from Shared.RPC import close_local_rpc
from Views.v2 import V2InfoContainerView
from main import bot_error_cache, VERSION, VERSION_ALTERNATE, ACTIVITY_TEXT

command = hybrid_command

async def setup(bot):
    await bot.add_cog(Bot(bot))

class Bot(Cog):
    def __init__(self, bot):
        self.bot = bot

    @hybrid_command(name="stats", description="Show bot statistics and status")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def stats(self, ctx: Context):
        load_dotenv(override=True)
        VERSION = os.getenv('BOT_VERSION')
        VERSION_ALTERNATE = os.getenv('BOT_VERSION_ALTERNATE')
        ACTIVITY_TEXT = os.getenv('ACTIVITY')
        total_guilds = len(self.bot.guilds)
        embed = discord.Embed(
            title="<:gear:1517576939097952496> Bot Statistics",
            color=discord.Color.gold(),
            description="Current status and technical details of the bot."
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else self.bot.user.default_avatar.url)
        embed.add_field(name="<:internet:1518376144246804672> Servers", value=str(total_guilds), inline=True)
        embed.add_field(name="<:graph:1517584522877866065> Total Users", value=str(len(self.bot.users)), inline=True)
        embed.add_field(name="<:hourglass:1517574046252924938> Latency", value=f"{round(self.bot.latency * 1000)}ms",
                        inline=True)
        embed.add_field(name="<:python:1518376147413635154> Library", value=f"discord.py {discord.__version__}",
                        inline=True)
        embed.add_field(name="<:gear:1517576939097952496> Version",
                        value=f"ver{VERSION} | alt{VERSION_ALTERNATE} | {ACTIVITY_TEXT}", inline=True)
        guild_shard_id = ctx.guild.shard_id if ctx.guild else 0
        total_shards = len(self.bot.shards) or 1
        shard_info = f"Shard id: {guild_shard_id} | total: {total_shards}"
        embed.add_field(name="<:shard:1518376149741338744> Shard Info", value=shard_info, inline=True)
        embed.add_field(name="<:nUtils:1518376146008539146> Bot owner", value="-ImNinnn- (imninnn.)", inline=True)
        await ctx.send(embed=embed)

    @hybrid_command(name="errors", description="Show recent bot errors in this server")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def errors(self, ctx: Context):
        clean_cache()

        guild_errors = [entry for entry in bot_error_cache if entry.get("guild_id") == ctx.guild.id]
        if not guild_errors:
            await ctx.send("No bot errors have been recorded for this server recently.")
            return

        recent_errors = list(reversed(guild_errors[-7:]))
        description_lines = []

        for entry in recent_errors:
            channel_id = entry.get("channel_id")
            if channel_id:
                channel_text = f"<#{channel_id}>"
            else:
                channel_text = "Unknown channel"

            user_obj = entry.get("user")
            user_text = getattr(user_obj, "display_name", getattr(user_obj, "name", "Unknown user"))
            error_message = entry.get("error_message", "No error message provided")
            if len(error_message) > 180:
                error_message = error_message[:177] + "..."

            description_lines.append(
                f"**{entry.get('command_name', 'unknown command')}** in {channel_text} by {user_text}\n"
                f"-# {entry.get('error_type', 'Error')}: {error_message}\n"
                f"-# At {discord_timestamp(entry['time'])}"
            )

        view = V2InfoContainerView(
            "<:warning:1517452174991556758> Recent Bot Errors",
            f"Showing latest {len(recent_errors)} of {len(guild_errors)} error(s).\n\n" + "\n\n".join(
                description_lines),
            discord.Color.red(),
        )
        await ctx.send(view=view)

    @command(name="ver")
    async def set_bot_version(self, ctx: Context, *, new_value: str = ""):
        if not await self.bot.is_owner(ctx.author):
            return await ctx.send("<:disapprove:1517452151012589662> Do not even try...")

        global VERSION

        if not new_value.strip():
            return await ctx.send(f"Current version: `{VERSION or ''}`")

        cleaned_value = new_value.strip()
        update_env_setting("BOT_VERSION", cleaned_value)
        VERSION = cleaned_value

        cogre = self.bot.get_cog("RPC")
        if cogre.update_presence.is_running():
            cogre.update_presence.restart()

        await ctx.send(f"Updated BOT_VERSION in .env to `{VERSION}`.")

    @command(name="alt")
    async def set_bot_alt_version(self, ctx: Context, *, new_value: str = ""):
        if not await self.bot.is_owner(ctx.author):
            return await ctx.send("<:disapprove:1517452151012589662> Do not even try...")

        global VERSION_ALTERNATE

        if not new_value.strip():
            return await ctx.send(f"Current alternate version: `{VERSION_ALTERNATE or ''}`")

        cleaned_value = new_value.strip()
        update_env_setting("BOT_VERSION_ALTERNATE", cleaned_value)
        VERSION_ALTERNATE = cleaned_value

        cogre = self.bot.get_cog("RPC")
        if cogre.update_presence.is_running():
            cogre.update_presence.restart()

        await ctx.send(f"Updated BOT_VERSION_ALTERNATE in .env to `{VERSION_ALTERNATE}`.")

    @command(name="activity")
    async def set_bot_activity(self, ctx: Context, *, new_value: str = ""):
        if not await self.bot.is_owner(ctx.author):
            return await ctx.send("<:disapprove:1517452151012589662> Do not even try...")

        global ACTIVITY_TEXT

        if not new_value.strip():
            return await ctx.send(f"Current activity: `{ACTIVITY_TEXT or ''}`")

        cleaned_value = new_value.strip()
        update_env_setting("ACTIVITY", cleaned_value)
        ACTIVITY_TEXT = cleaned_value

        cogre = self.bot.get_cog("RPC")
        if cogre.update_presence.is_running():
            cogre.update_presence.restart()

        await ctx.send(f"Updated ACTIVITY in .env to `{ACTIVITY_TEXT}`.")

    @command(name="shutdown")
    async def own_shutdown(self, ctx: Context, *, args: str = ""):
        if not await self.bot.is_owner(ctx.author):
            return await ctx.send("<:disapprove:1517452151012589662> Do not even try...")

        channel = None
        reason = "No reason provided"

        if args:
            parts = args.split(maxsplit=1)
            if parts and parts[0].startswith("#"):
                channel_name = parts[0].lstrip("#")
                channel = discord.utils.get(ctx.guild.text_channels, name=channel_name) if ctx.guild else None
                if len(parts) > 1:
                    reason = parts[1]
            else:
                reason = args

        if channel is None:
            channel = self.bot.get_channel(1514173159052415026)
        if channel is None and isinstance(ctx.channel, discord.TextChannel):
            channel = ctx.channel

        shutdown_text = f"🔌 {reason}"
        shutdown_embed = discord.Embed(
            title="Bot Shutdown Initiated",
            description=shutdown_text,
            color=discord.Color.light_gray()
        )

        published = False
        if channel is not None:
            try:
                sent_msg = await channel.send(embed=shutdown_embed)
                if channel.type == discord.ChannelType.news:
                    try:
                        await sent_msg.publish()
                        published = True
                    except Exception:
                        published = False
            except discord.Forbidden as error:
                add_bot_error_entry(ctx.guild.id if ctx.guild else None, channel.id, ctx.author, "shutdown notice",
                                    error)
                await ctx.send(
                    f"<:disapprove:1517452151012589662> Could not send the shutdown notice to {channel.mention}.")
                return
            except Exception as e:
                await ctx.send(
                    f"<:disapprove:1517452151012589662> Could not send the shutdown notice to {channel.mention}. Error: {e}")
                return

        cogre = self.bot.get_cog("RPC")
        if cogre.update_presence.is_running():
            cogre.update_presence.cancel()
            await asyncio.sleep(1)

        response_text = "Going to sleep..."
        if channel is not None:
            response_text = (
                    f"Shutdown notice sent to {channel.mention}. "
                    + ("Published to followers." if published else "")
            )

        await ctx.send(response_text)

        shutdown_activity = discord.Activity(type=discord.ActivityType.watching, name="App is shutting down!!! !! !")
        sleep_activity = discord.Activity(type=discord.ActivityType.watching, name="App is sleeping... zZzZzZ")
        for shard_id in self.bot.shards:
            await self.bot.change_presence(activity=shutdown_activity, status=discord.Status.dnd, shard_id=shard_id)
        await asyncio.sleep(10)
        for shard_id in self.bot.shards:
            await self.bot.change_presence(activity=sleep_activity, status=discord.Status.idle, shard_id=shard_id)
        close_local_rpc()
        await self.bot.close()
