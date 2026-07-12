import random

from discord.ext.commands import Cog
import discord, traceback

from Shared.Cache import clean_cache
from Shared.Counters import handle_counter_message
from Shared.Errors import *
from discord import app_commands

from Shared.Fun import load_fun_data
from Shared.Leveling import add_xp
from Shared.Moderation import apply_honeypot_sanction
from main import NinnnUtils, locked_channels, admin_log_channels, server_pauses, all_paused_guilds, message_cache
from Giveaways import Giveaways
from RPC import RPC
from Blacklist import Blacklist

async def setup(bot):
    await bot.add_cog(UnEvents(bot))

class UnEvents(Cog):
    def __init__(self, bot: NinnnUtils):
        self.bot = bot

    @Cog.listener()
    async def cog_load(self):
        await self.bot.wait_until_ready()
        cog: RPC = self.bot.get_cog("RPC")
        blk: Blacklist = self.bot.get_cog("Blacklist")
        gws: Giveaways = self.bot.get_cog("Giveaways")
        shard_info = (
            f"{len(self.bot.shards)} shard(s), IDs {list(self.bot.shards.keys())}"
            if self.bot.shards
            else "single process (no sharding)"
        )
        print(f"Logged in as {self.bot.user} (ID: {self.bot.user.id}) - {shard_info}")
        print(f"Serving {len(self.bot.guilds)} guild(s)")
        if not cog.update_presence.is_running():
            cog.update_presence.start()

        voice = self.bot.get_cog("Music")

        if not voice.voice_xp_tracker.is_running():
            voice.voice_xp_tracker.start()
        if not gws.giveaway_loop.is_running():
            gws.giveaway_loop.start()
        if not gws.giveaway_refresh_loop.is_running():
            gws.giveaway_refresh_loop.start()
        self.bot.loop.create_task(blk.blacklist_startup_cleanup())

    @Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        original_error = getattr(error, "original", error)
        bot_missing_permissions_error = getattr(app_commands, "BotMissingPermissions", None)

        if isinstance(error, app_commands.CommandOnCooldown):
            retry_after = error.retry_after
            if retry_after >= 60:
                minutes = int(retry_after // 60)
                seconds = int(retry_after % 60)
                if seconds > 0:
                    message_text = f"<:hourglass:1517574046252924938> This command is on cooldown. Please wait **{minutes}m {seconds}s** before trying again."
                else:
                    message_text = f"<:hourglass:1517574046252924938> This command is on cooldown. Please wait **{minutes}m** before trying again."
            else:
                retry_after = round(retry_after, 1)
                message_text = f"<:hourglass:1517574046252924938> This command is on cooldown. Please wait **{retry_after}s** before trying again."
            if interaction.response.is_done():
                await interaction.followup.send(message_text, ephemeral=True)
            else:
                await interaction.response.send_message(message_text, ephemeral=True)
        elif isinstance(error, app_commands.MissingPermissions):
            perms = ", ".join(error.missing_permissions)
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> You lack the required permissions to run this: `{perms}`", ephemeral=True)
        elif bot_missing_permissions_error is not None and isinstance(error, bot_missing_permissions_error):
            perms = ", ".join(error.missing_permissions)
            message_text = f"<:disapprove:1517452151012589662> I am missing the required permissions to run this: `{perms}`"
            if interaction.response.is_done():
                await interaction.followup.send(message_text, ephemeral=True)
            else:
                await interaction.response.send_message(message_text, ephemeral=True)
        elif isinstance(original_error, discord.Forbidden):
            message_text = "<:disapprove:1517452151012589662> I am missing the permissions required to complete that action."
            if interaction.response.is_done():
                await interaction.followup.send(message_text, ephemeral=True)
            else:
                await interaction.response.send_message(message_text, ephemeral=True)
        else:
            command_name = getattr(getattr(interaction, "command", None), "qualified_name", None) or getattr(getattr(interaction, "command", None), "name", "unknown command")
            add_bot_error(
                getattr(interaction, "guild_id", None),
                getattr(interaction, "channel_id", None),
                getattr(interaction, "user", None),
                command_name,
                original_error,
                interaction=interaction,
            )
            print(f"Ignored exception in command tree [{command_name}]: {type(original_error).__name__}: {original_error}")
            print("".join(traceback.format_exception(type(original_error), original_error, original_error.__traceback__)))
            if not interaction.response.is_done():
                await interaction.response.send_message("<:disapprove:1517452151012589662> An unexpected error occurred while executing this command.", ephemeral=True)

    @Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.guild:
            if await apply_honeypot_sanction(message.author, message.guild, message.channel, message.content):
                try:
                    await message.delete()
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return

        if message.guild and message.channel.id in locked_channels:
            guild_id = message.guild.id

            for log_id in admin_log_channels:
                log_channel = self.bot.get_channel(log_id)
                if log_channel and log_channel.guild.id == guild_id:
                    try:
                        await log_channel.send(f"**[LOCKED]** `{message.author}`: {message.content}")
                    except discord.Forbidden as error:
                        add_bot_error_entry(guild_id, log_id, message.author, "locked channel admin log", error)
                    except Exception:
                        pass

            current_pauses = server_pauses.get(guild_id, set())
            if guild_id in all_paused_guilds or message.channel.id in current_pauses:
                return

            dots = "•" * min(max(len(message.content), 1), 200)
            try:
                await message.delete()
                await message.channel.send(f"<:locked:1517574877257924809> {dots}")
            except discord.Forbidden as error:
                add_bot_error_entry(guild_id, message.channel.id, message.author, "locked channel notice", error)
            except Exception:
                pass
            return

        global message_cache
        clean_cache()

        media_url = message.attachments[0].url if message.attachments else None
        now = datetime.now(timezone.utc)
        message_cache.append({
            'id': message.id,
            'channel': message.channel.id,
            'author': message.author,
            'content': message.content,
            'media': media_url,
            'mentions': message.mentions,
            'time': now,
            'created_at': now
        })

        if message.guild:
            guild_id = str(message.guild.id)
            fun_data = load_fun_data()
            if guild_id in fun_data:
                guild_replies = fun_data[guild_id]
                message_words = message.content.lower().split()
                for trigger in guild_replies:
                    if trigger in message_words:
                        response = random.choice(guild_replies[trigger])
                        try:
                            await message.reply(response)
                        except discord.Forbidden as error:
                            add_bot_error_entry(message.guild.id, message.channel.id, message.author,
                                                f"auto-reply: {trigger}", error)
                        except Exception as error:
                            add_bot_error_entry(message.guild.id, message.channel.id, message.author,
                                                f"auto-reply: {trigger}", error)
                        break

            if await handle_counter_message(message):
                return

            await add_xp(self.bot, message.author, message.guild, random.randint(5, 10), announce_channel=message.channel)

        await self.bot.process_commands(message)
