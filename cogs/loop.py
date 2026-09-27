"""Background loops and startup maintenance for the migrated bot."""

import asyncio
import os
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

import save
from utils.audit import add_bot_error_entry, send_audit_log
from utils.banners import create_goodbye_card, create_welcome_card
from utils.formatting import discord_timestamp, format_user_reference, format_user_reference_with_setting

SUPPORT_SERVER_INVITE = "https://discord.com/invite/FSBPvc9zqY"


def get_guild_welcome_channel(guild: discord.Guild) -> discord.TextChannel | None:
    channel_names = {channel.name.lower(): channel for channel in guild.text_channels}
    for name, channel in channel_names.items():
        if "bot" in name or "command" in name:
            return channel
    for name, channel in channel_names.items():
        if "general" in name:
            return channel
    return None


async def get_guild_app_adder(guild: discord.Guild, bot_user: discord.ClientUser) -> discord.Member | discord.User | None:
    try:
        async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=25):
            if getattr(entry, "target", None) is not None and getattr(entry.target, "id", None) == bot_user.id:
                actor = getattr(entry, "user", None) or getattr(entry, "actor", None)
                if actor is not None:
                    return actor
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        pass

    return guild.owner


class LoopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.presence_index = 0

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title="<:next:1518977801057861643> Member Joined",
            color=discord.Color.green(),
        )
        embed.add_field(name="User", value=format_user_reference(member), inline=True)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Account Age", value=discord_timestamp(member.created_at), inline=True)
        embed.timestamp = datetime.now(timezone.utc)
        await send_audit_log(member.guild, "member_join", embed=embed)

        guild_config, _ = save.get_guild_config(str(member.guild.id))
        channel_id = guild_config.get("welcome_channel_id")
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                try:
                    welcome_file = await create_welcome_card(member)
                    settings = save.load_user_settings()
                    await channel.send(f"Welcome {format_user_reference_with_setting(member, settings)}!", file=welcome_file)
                except discord.Forbidden as error:
                    add_bot_error_entry(member.guild.id, channel.id, member, "welcome banner", error)
                except Exception as exc:
                    print(f"Error creating welcome card: {exc}")

        if guild_config.get("join_dm_enabled", False):
            join_dm_message = guild_config.get("join_dm_message")
            if join_dm_message:
                try:
                    placeholders = {
                        "user": member.mention,
                        "member": member.mention,
                        "guild": member.guild.name,
                        "server": member.guild.name,
                    }
                    formatted_message = re.sub(
                        r"\{(user|member|guild|server)\}",
                        lambda match: placeholders[match.group(1)],
                        join_dm_message,
                    )
                    source_button = discord.ui.Button(
                        label=f"From {member.guild.name[:73]}",
                        style=discord.ButtonStyle.secondary,
                        disabled=True,
                    )
                    source_view = discord.ui.View()
                    source_view.add_item(source_button)
                    await member.send(formatted_message[:2000], view=source_view)
                except discord.Forbidden as error:
                    add_bot_error_entry(member.guild.id, None, member, "join DM", error)
                except Exception as exc:
                    print(f"Error sending join DM: {exc}")

        join_role_ids = guild_config.get("join_role_ids", [])
        if join_role_ids:
            for role_id in list(join_role_ids):
                try:
                    role_id_int = int(role_id)
                except (TypeError, ValueError):
                    continue
                role = member.guild.get_role(role_id_int)
                if role is None or role in member.roles:
                    continue
                try:
                    await member.add_roles(role, reason="Join role")
                except discord.Forbidden as error:
                    add_bot_error_entry(member.guild.id, role.id, member, "join role", error)
                except Exception as exc:
                    print(f"Error assigning join role {role.id}: {exc}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            title="<:prev:1518977803092234331> Member Left",
            color=discord.Color.red(),
        )
        embed.add_field(name="User", value=format_user_reference(member), inline=True)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Joined", value=discord_timestamp(member.joined_at) if member.joined_at else "Unknown", inline=True)
        embed.timestamp = datetime.now(timezone.utc)
        await send_audit_log(member.guild, "member_remove", embed=embed)

        guild_config, _ = save.get_guild_config(str(member.guild.id))
        channel_id = guild_config.get("goodbye_channel_id")
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                try:
                    goodbye_file = await create_goodbye_card(member)
                    settings = save.load_user_settings()
                    goodbye_name = format_user_reference_with_setting(member, settings)
                    await channel.send(f"Goodbye {goodbye_name}. We'll miss you!", file=goodbye_file)
                except discord.Forbidden as error:
                    add_bot_error_entry(member.guild.id, channel.id, member, "goodbye banner", error)
                except Exception as exc:
                    print(f"Error creating goodbye card: {exc}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        welcome_channel = get_guild_welcome_channel(guild)
        if welcome_channel is not None:
            adder = await get_guild_app_adder(guild, self.bot.user)
            adder_mention = adder.mention if adder is not None else (guild.owner.mention if guild.owner else "Server owner")
            try:
                await welcome_channel.send(
                    f"<:nUtils:1518376146008539146> **Thanks** for adding me, {adder_mention}! I’m happy to be here.\n"
                    "Please check **/help** to browse commands and **/settings** to configure the bot for your server!"
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def _set_presence_for_all_shards(self, *, activity=None, status=discord.Status.online):
        if not self.bot.is_ready():
            return
        for shard_id in list(self.bot.shards):
            try:
                await self.bot.change_presence(activity=activity, status=status, shard_id=shard_id)
            except Exception:
                pass

    @tasks.loop(seconds=15)
    async def update_presence(self):
        load_dotenv(override=True)
        version = os.getenv('BOT_VERSION')
        version_alternate = os.getenv('BOT_VERSION_ALTERNATE')
        activity_text = os.getenv('ACTIVITY')
        total_guilds = len(self.bot.guilds)

        if self.presence_index == 0:
            activity_name = f"watching over {total_guilds} servers..."
        elif self.presence_index == 1:
            activity_name = f"...and {len(self.bot.users)} users!"
        elif self.presence_index == 2:
            activity_name = activity_text or 'nUtils'
        else:
            activity_name = f"ver{version} ┃ {version_alternate}"

        activity = discord.Activity(type=discord.ActivityType.watching, name=activity_name)
        await self._set_presence_for_all_shards(activity=activity)
        self.presence_index = (self.presence_index + 1) % 4

    @update_presence.before_loop
    async def before_update_presence(self):
        await self.bot.wait_until_ready()
        self.presence_index = 0
        startup_activity = discord.Streaming(
            name='App just started... .. .',
            url='https://www.twitch.tv/imninnn',
        )
        await self._set_presence_for_all_shards(activity=startup_activity)
        await asyncio.sleep(30)

    def start_tasks(self):
        if not self.update_presence.is_running():
            self.presence_index = 0
            self.update_presence.start()
    async def cog_unload(self):
        await self._set_presence_for_all_shards(activity=None)
        if self.update_presence.is_running():
            self.update_presence.cancel()


async def setup(bot):
    cog = LoopCog(bot)
    await bot.add_cog(cog)
    if bot.is_ready():
        cog.start_tasks()
