from discord.ext.commands import Cog, Context, hybrid_group
from datetime import datetime, timezone

from Shared.Boards import load_board_data, save_board_data
from Shared.Errors import *
import discord
import random

from Shared.Leveling import add_xp
from main import reaction_xp_cooldowns

async def setup(bot):
    await bot.add_cog(Boards(bot))

class Boards(Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        reactor = guild.get_member(payload.user_id)
        if reactor and not reactor.bot:
            cooldown_key = (payload.guild_id, payload.user_id)
            now = datetime.now()
            last_xp = reaction_xp_cooldowns.get(cooldown_key)
            if not last_xp or (now - last_xp).total_seconds() >= 15:
                reaction_xp_cooldowns[cooldown_key] = now
                await add_xp(self.bot, reactor, guild, random.randint(1, 3), announce_channel=guild.get_channel(payload.channel_id))
            try:
                channel = guild.get_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)
                if message.author and not message.author.bot and message.author.id != payload.user_id:
                    await add_xp(self.bot, message.author, guild, random.randint(3, 5), announce_channel=channel)
            except discord.Forbidden as error:
                add_bot_error_entry(payload.guild_id, payload.channel_id, None, "reaction xp source fetch", error)
            except Exception:
                pass

        guild_id = str(payload.guild_id)
        board_data = load_board_data()

        if guild_id not in board_data:
            return

        emoji_str = str(payload.emoji)
        if emoji_str not in board_data[guild_id]:
            return

        config = board_data[guild_id][emoji_str]
        if "tracked_messages" not in config:
            config["tracked_messages"] = {}

        message_id_str = str(payload.message_id)

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.Forbidden as error:
            add_bot_error_entry(payload.guild_id, channel.id, None, "reaction board source fetch", error)
            return
        except discord.NotFound:
            return

        reaction = discord.utils.get(message.reactions, emoji=payload.emoji.name if payload.emoji.is_unicode_emoji() else payload.emoji)
        current_count = reaction.count if reaction else 0

        board_channel = self.bot.get_channel(config["channel_id"])
        if not board_channel:
            return

        embed = discord.Embed(
            description=f"{message.content}" if message.content else None,
            color=discord.Color.gold(),
        )
        embed.set_author(name=f"{message.author.display_name}", icon_url=message.author.display_avatar.url)
        if message.attachments:
            attachment = message.attachments[0]
            if attachment.content_type and attachment.content_type.startswith("image/"):
                embed.set_image(url=attachment.url)
        embed.timestamp = datetime.now(timezone.utc)

        content_text = f"{emoji_str} {current_count} in {message.jump_url}"

        if message_id_str in config["tracked_messages"]:
            board_msg_id = int(config["tracked_messages"][message_id_str])
            try:
                board_message = await board_channel.fetch_message(board_msg_id)
                try:
                    await board_message.edit(content=content_text, embed=embed)
                except discord.Forbidden as error:
                    add_bot_error_entry(payload.guild_id, config["channel_id"], None, "reaction board edit", error)
            except discord.NotFound:
                del config["tracked_messages"][message_id_str]
                save_board_data(board_data)
        elif current_count >= config["required_count"]:
            try:
                new_board_msg = await board_channel.send(content=content_text, embed=embed)
            except discord.Forbidden as error:
                add_bot_error_entry(payload.guild_id, config["channel_id"], None, "reaction board post", error)
                return
            config["tracked_messages"][message_id_str] = str(new_board_msg.id)
            save_board_data(board_data)


    @Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if not payload.guild_id:
            return

        guild_id = str(payload.guild_id)
        board_data = load_board_data()

        if guild_id not in board_data:
            return

        emoji_str = str(payload.emoji)
        if emoji_str not in board_data[guild_id]:
            return

        config = board_data[guild_id][emoji_str]
        if "tracked_messages" not in config:
            return

        message_id_str = str(payload.message_id)
        if message_id_str not in config["tracked_messages"]:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return

        reaction = discord.utils.get(message.reactions, emoji=payload.emoji.name if payload.emoji.is_unicode_emoji() else payload.emoji)
        current_count = reaction.count if reaction else 0

        board_channel = self.bot.get_channel(config["channel_id"])
        if not board_channel:
            return

        board_msg_id = int(config["tracked_messages"][message_id_str])
        try:
            board_message = await board_channel.fetch_message(board_msg_id)
            if current_count >= config["required_count"]:
                content_text = f"{emoji_str} {current_count} in {message.jump_url}"
                embed = discord.Embed(description=f"{message.content}" if message.content else None, color=discord.Color.gold())
                embed.set_author(name=f"{message.author.display_name}", icon_url=message.author.display_avatar.url)
                if message.attachments and message.attachments[0].content_type.startswith("image/"):
                    embed.set_image(url=message.attachments[0].url)
                embed.timestamp = datetime.now(timezone.utc)
                await board_message.edit(content=content_text, embed=embed)
            else:
                await board_message.delete()
                del config["tracked_messages"][message_id_str]
                save_board_data(board_data)
        except discord.Forbidden as error:
            add_bot_error_entry(payload.guild_id, config["channel_id"], None, "reaction board fetch", error)
        except discord.NotFound:
            del config["tracked_messages"][message_id_str]
            save_board_data(board_data)
