"""Counter channels and the reaction starboard."""

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import save
from utils.audit import add_bot_error_entry
from utils.automod import is_honeypot_channel
from utils.counters import get_counter_channel_config, safe_eval_math_expr, set_counter_value, update_counter_state


def build_board_embed(message: discord.Message) -> discord.Embed:
    embed = discord.Embed(
        description=message.content if message.content else None,
        color=discord.Color.gold(),
    )
    embed.set_author(name=f"| {message.author.display_name}", icon_url=message.author.display_avatar.url)
    if message.attachments:
        attachment = message.attachments[0]
        if attachment.content_type and attachment.content_type.startswith("image/"):
            embed.set_image(url=attachment.url)
        else:
            attachment_name = attachment.filename or "attachment"
            embed.add_field(name="Attachment", value=f"[{attachment_name}]({attachment.url})"[:1024], inline=False)
    embed.timestamp = message.created_at
    return embed


def _set_board_tracking(guild_id: str, emoji_str: str, message_id: str, board_message_id: int | None) -> None:
    # Reloaded on every write: the board may have been edited while the bot waited on Discord.
    board_data = save.load_board_data()
    config = board_data.get(guild_id, {}).get(emoji_str)
    if not isinstance(config, dict):
        return
    tracked = config.setdefault("tracked_messages", {})
    if board_message_id is None:
        if tracked.pop(message_id, None) is None:
            return
    else:
        tracked[message_id] = str(board_message_id)
    save.save_board_data(board_data)


class MiscCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # key -> [lock, number of reactions using or waiting for it]
        self._board_locks: dict[tuple[str, str, int], list] = {}
        # channel id -> the bot's "wrong number" hint, removed as soon as someone sends another message
        self._counter_hints: dict[int, discord.Message] = {}
        self._last_counter_message: dict[int, int] = {}

    # ------------------------------------------------------------ counters

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if is_honeypot_channel(message.guild, message.channel):
            return
        if get_counter_channel_config(str(message.guild.id), message.channel.id) is None:
            return
        self._last_counter_message[message.channel.id] = message.id
        await self._clear_counter_hint(message.channel.id)
        await self.handle_counter_message(message)

    async def _clear_counter_hint(self, channel_id: int) -> None:
        hint = self._counter_hints.pop(channel_id, None)
        if hint is None:
            return
        try:
            await hint.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

    async def _send_counter_hint(self, message: discord.Message, text: str) -> None:
        try:
            hint = await message.reply(text, mention_author=False)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return
        # Someone typed while the reply was being sent: the hint is already outdated.
        if self._last_counter_message.get(message.channel.id) != message.id:
            try:
                await hint.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            return
        await self._clear_counter_hint(message.channel.id)
        self._counter_hints[message.channel.id] = hint

    async def handle_counter_message(self, message: discord.Message) -> bool:
        guild_id = str(message.guild.id)
        config = get_counter_channel_config(guild_id, message.channel.id)
        if not config:
            return False

        content = message.content.strip()
        if not content:
            return False
        value = safe_eval_math_expr(content)
        if value is None:
            return False

        # No await between reading and saving the count, so two people racing can't both score.
        expected = config.get("current_value", 0) + 1
        hint = None
        if config.get("last_user_id") == message.author.id:
            emoji = "<:warning:1517452174991556758>"
            hint = f"<:warning:1517452174991556758> You can't count twice in a row, let someone else say **{expected}**!"
        elif value == expected:
            update_counter_state(guild_id, message.channel.id, value, message.author.id)
            emoji = "<:approve:1517452125687513158>"
        else:
            emoji = "<:disapprove:1517452151012589662>"
            if config.get("reset_on_fail"):
                update_counter_state(guild_id, message.channel.id, 0, None)
                hint = f"<:disapprove:1517452151012589662> Wrong number, it was **{expected}**! The counter has been reset, start again from **1**."
            else:
                hint = f"<:disapprove:1517452151012589662> Wrong number, the next number is **{expected}**."

        try:
            await message.add_reaction(emoji)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass
        if hint:
            await self._send_counter_hint(message, hint)
        return True

    @app_commands.command(name='counter-number-set', description='Set the current count in a counter channel')
    @app_commands.describe(channel='The counter channel to update', value='The new current count value')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def counter_number_set(self, interaction: discord.Interaction, channel: discord.TextChannel, value: int):
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        success = set_counter_value(str(interaction.guild.id), channel.id, value)
        if success:
            await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Counter in {channel.mention} is now set to {value}.", ephemeral=False)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:warning:1517452174991556758> That channel does not have an active counter.", ephemeral=True)

    # ------------------------------------------------------------ starboard

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self.update_board(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self.update_board(payload)

    async def update_board(self, payload: discord.RawReactionActionEvent) -> None:
        if not payload.guild_id:
            return
        guild_id = str(payload.guild_id)
        emoji_str = str(payload.emoji)
        config = save.load_board_data().get(guild_id, {}).get(emoji_str)
        if not isinstance(config, dict) or not config.get("channel_id"):
            return
        # Reactions on the board's own posts would copy them onto the board again.
        if payload.channel_id == int(config["channel_id"]):
            return

        # Several people often react at once: handle one reaction per message at a time,
        # otherwise each of them posts its own copy on the board.
        lock_key = (guild_id, emoji_str, payload.message_id)
        entry = self._board_locks.setdefault(lock_key, [asyncio.Lock(), 0])
        entry[1] += 1
        try:
            async with entry[0]:
                await self._update_board_locked(payload, guild_id, emoji_str)
        finally:
            entry[1] -= 1
            if entry[1] == 0:
                self._board_locks.pop(lock_key, None)

    async def _update_board_locked(self, payload: discord.RawReactionActionEvent, guild_id: str, emoji_str: str) -> None:
        config = save.load_board_data().get(guild_id, {}).get(emoji_str)
        if not isinstance(config, dict):
            return
        message_id_str = str(payload.message_id)
        board_message_id = config.get("tracked_messages", {}).get(message_id_str)
        required_count = int(config.get("required_count", 1) or 1)

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.Forbidden as error:
            add_bot_error_entry(payload.guild_id, channel.id, None, "reaction board source fetch", error)
            return
        except (discord.NotFound, discord.HTTPException):
            return

        reaction = discord.utils.get(message.reactions, emoji=payload.emoji.name if payload.emoji.is_unicode_emoji() else payload.emoji)
        current_count = reaction.count if reaction else 0

        board_channel = self.bot.get_channel(int(config["channel_id"]))
        if not board_channel:
            return

        content_text = f"{emoji_str} {current_count} in {message.jump_url}"

        if board_message_id:
            try:
                board_message = await board_channel.fetch_message(int(board_message_id))
            except discord.NotFound:
                _set_board_tracking(guild_id, emoji_str, message_id_str, None)
                return
            except (discord.Forbidden, discord.HTTPException) as error:
                add_bot_error_entry(payload.guild_id, board_channel.id, None, "reaction board fetch", error)
                return
            try:
                if current_count >= required_count:
                    await board_message.edit(content=content_text, embed=build_board_embed(message))
                else:
                    await board_message.delete()
                    _set_board_tracking(guild_id, emoji_str, message_id_str, None)
            except discord.NotFound:
                _set_board_tracking(guild_id, emoji_str, message_id_str, None)
            except (discord.Forbidden, discord.HTTPException) as error:
                add_bot_error_entry(payload.guild_id, board_channel.id, None, "reaction board edit", error)
        elif current_count >= required_count:
            try:
                new_board_msg = await board_channel.send(content=content_text, embed=build_board_embed(message))
            except (discord.Forbidden, discord.HTTPException) as error:
                add_bot_error_entry(payload.guild_id, board_channel.id, None, "reaction board post", error)
                return
            _set_board_tracking(guild_id, emoji_str, message_id_str, new_board_msg.id)


async def setup(bot):
    await bot.add_cog(MiscCog(bot))
