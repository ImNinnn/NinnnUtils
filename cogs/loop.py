"""Background loops and startup maintenance for the migrated bot."""

import asyncio
import os
import re

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

import helper as main

SUPPORT_SERVER_INVITE = "https://discord.com/invite/FSBPvc9zqY"


class LoopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.presence_index = 0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Intentionally left empty: the central Bot.on_message handler in bot.py is the
        # single message-routing path. Calling main.on_message here would duplicate every
        # prefix-command and counter check on the same message.
        return

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title="<:next:1518977801057861643> Member Joined",
            color=discord.Color.green(),
        )
        embed.add_field(name="User", value=main.format_user_reference(member), inline=True)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Account Age", value=main.discord_timestamp(member.created_at), inline=True)
        embed.timestamp = main.datetime.now(main.timezone.utc)
        await main.send_audit_log(member.guild, "member_join", embed=embed)

        guild_config, _ = main.get_guild_config(str(member.guild.id))
        channel_id = guild_config.get("welcome_channel_id")
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                try:
                    welcome_file = await main.create_welcome_card(member)
                    settings = main.load_user_settings()
                    await channel.send(f"Welcome {main.format_user_reference_with_setting(member, settings)}!", file=welcome_file)
                except discord.Forbidden as error:
                    main.add_bot_error_entry(member.guild.id, channel.id, member, "welcome banner", error)
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
                    await member.send(formatted_message, view=source_view)
                except discord.Forbidden as error:
                    main.add_bot_error_entry(member.guild.id, None, member, "join DM", error)
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
                    main.add_bot_error_entry(member.guild.id, role.id, member, "join role", error)
                except Exception as exc:
                    print(f"Error assigning join role {role.id}: {exc}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            title="<:prev:1518977803092234331> Member Left",
            color=discord.Color.red(),
        )
        embed.add_field(name="User", value=main.format_user_reference(member), inline=True)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Joined", value=main.discord_timestamp(member.joined_at) if member.joined_at else "Unknown", inline=True)
        embed.timestamp = main.datetime.now(main.timezone.utc)
        await main.send_audit_log(member.guild, "member_remove", embed=embed)

        guild_config, _ = main.get_guild_config(str(member.guild.id))
        channel_id = guild_config.get("goodbye_channel_id")
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                try:
                    goodbye_file = await main.create_goodbye_card(member)
                    settings = main.load_user_settings()
                    goodbye_name = main.format_user_reference_with_setting(member, settings)
                    await channel.send(f"Goodbye {goodbye_name}. We'll miss you!", file=goodbye_file)
                except discord.Forbidden as error:
                    main.add_bot_error_entry(member.guild.id, channel.id, member, "goodbye banner", error)
                except Exception as exc:
                    print(f"Error creating goodbye card: {exc}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        welcome_channel = main.get_guild_welcome_channel(guild)
        if welcome_channel is not None:
            adder = await main.get_guild_app_adder(guild)
            adder_mention = adder.mention if adder is not None else (guild.owner.mention if guild.owner else "Server owner")
            try:
                await welcome_channel.send(
                    f"<:nUtils:1518376146008539146> **Thanks** for adding me, {adder_mention}! I’m happy to be here.\n"
                    "Please check **/help** to browse commands and **/settings** to configure the bot for your server!"
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def check_giveaways(self) -> None:
        try:
            data = main.load_giveaway_data()
            if not data:
                return
            now_ts = int(main.datetime.now(main.timezone.utc).timestamp())
            for giveaway_id, giveaway in list(data.items()):
                try:
                    if giveaway.get('status') == 'active' and int(giveaway.get('end_time', 0)) <= now_ts:
                        self.bot.loop.create_task(main.finalize_giveaway(str(giveaway_id), giveaway))
                except Exception:
                    pass
        except Exception:
            pass

    async def check_reminders(self) -> None:
        try:
            settings = main.load_user_settings()
            if not settings:
                return
            now_ts = int(main.datetime.now(main.timezone.utc).timestamp())
            users = settings.get('users')
            if not isinstance(users, dict):
                return
            reminders_changed = False
            for user_id, user_settings in list(users.items()):
                reminders = user_settings.get('reminders')
                if not isinstance(reminders, list):
                    continue

                remaining_reminders = []
                for reminder in reminders:
                    if not isinstance(reminder, dict):
                        continue
                    when = reminder.get('when')
                    if isinstance(when, int) and when <= now_ts:
                        try:
                            self.bot.loop.create_task(main.deliver_reminder(str(user_id), reminder))
                        except Exception:
                            pass
                        reminders_changed = True
                        repeat = reminder.get('repeat')
                        if isinstance(repeat, int) and repeat > 0:
                            next_when = when + repeat
                            while next_when <= now_ts:
                                next_when += repeat
                            reminder['when'] = int(next_when)
                            remaining_reminders.append(reminder)
                    else:
                        remaining_reminders.append(reminder)

                if len(remaining_reminders) != len(reminders):
                    user_settings['reminders'] = remaining_reminders

            if reminders_changed:
                main.save_user_settings(settings)
        except Exception:
            pass

    @tasks.loop(minutes=1)
    async def giveaway_loop(self):
        await self.check_giveaways()

    @tasks.loop(seconds=10)
    async def reminders_loop(self):
        await self.check_reminders()

    @giveaway_loop.before_loop
    async def before_giveaway_loop(self):
        await self.bot.wait_until_ready()

    @reminders_loop.before_loop
    async def before_reminders_loop(self):
        await self.bot.wait_until_ready()

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
        if not self.giveaway_loop.is_running():
            self.giveaway_loop.start()
        if not self.reminders_loop.is_running():
            self.reminders_loop.start()
    async def cog_unload(self):
        await self._set_presence_for_all_shards(activity=None)
        if self.update_presence.is_running():
            self.update_presence.cancel()
        if self.giveaway_loop.is_running():
            self.giveaway_loop.cancel()
        if self.reminders_loop.is_running():
            self.reminders_loop.cancel()


async def setup(bot):
    cog = LoopCog(bot)
    await bot.add_cog(cog)
    if bot.is_ready():
        cog.start_tasks()
