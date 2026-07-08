import discord

from LowerLeveled.jsonutils import load_json_file, save_json_file
from Shared.Errors import add_bot_error_entry
from main import BOARD_FILE


def load_board_data():
    return load_json_file(BOARD_FILE, {})


def save_board_data(data):
    save_json_file(BOARD_FILE, data)

def get_guild_board_entries(guild_id: str) -> list[str]:
    board_data = load_board_data()
    entries = []
    if guild_id in board_data:
        for emoji_key, cfg in board_data[guild_id].items():
            ch_id = cfg.get("channel_id")
            required = cfg.get("required_count")
            channel_repr = f"<#{ch_id}>" if ch_id else "Unknown"
            req_text = f"required {required}" if required is not None else "required ?"
            entries.append(f"{emoji_key} in {channel_repr} ({req_text})")
    return entries

def ensure_board_guild_config(guild_id: str):
    board_data = load_board_data()
    if guild_id not in board_data:
        board_data[guild_id] = {}
    return board_data

async def update_board(payload, emoji_str, remove_mode=False):
    guild_id = str(payload.guild_id)
    board_data = load_board_data()

    if guild_id not in board_data or emoji_str not in board_data[guild_id]:
        return

    config = board_data[guild_id][emoji_str]
    if "tracked_messages" not in config:
        config["tracked_messages"] = {}

    orig_msg_id = str(payload.message_id)

    channel = bot.get_channel(payload.channel_id)
    if not channel:
        return
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return

    reaction = discord.utils.get(message.reactions, emoji=payload.emoji.name if payload.emoji.is_unicode_emoji() else payload.emoji)
    current_count = reaction.count if reaction else 0

    board_channel = bot.get_channel(config["channel_id"])
    if not board_channel:
        return

    embed = discord.Embed(
        description=f"{message.content}" if message.content else None,
        color=discord.Color.gold(),
    )
    embed.set_author(name=f"| {message.author.display_name}", icon_url=message.author.display_avatar.url)
    if message.attachments:
        attachment = message.attachments[0]
        if attachment.content_type and attachment.content_type.startswith("image/"):
            embed.set_image(url=attachment.url)
    embed.timestamp = message.created_at

    content_text = f"{emoji_str} {current_count} in {message.jump_url}"

    if orig_msg_id in config["tracked_messages"]:
        board_msg_id = int(config["tracked_messages"][orig_msg_id])
        try:
            board_message = await board_channel.fetch_message(board_msg_id)
            if current_count >= config["required_count"]:
                try:
                    await board_message.edit(content=content_text, embed=embed)
                except discord.Forbidden as error:
                    add_bot_error_entry(payload.guild_id, config["channel_id"], None, "reaction board edit", error)
            else:
                try:
                    await board_message.delete()
                except discord.Forbidden as error:
                    add_bot_error_entry(payload.guild_id, config["channel_id"], None, "reaction board delete", error)
                del config["tracked_messages"][orig_msg_id]
                save_board_data(board_data)
        except discord.Forbidden as error:
            add_bot_error_entry(payload.guild_id, config["channel_id"], None, "reaction board fetch", error)
        except discord.NotFound:
            del config["tracked_messages"][orig_msg_id]
            save_board_data(board_data)

    elif current_count >= config["required_count"] and not remove_mode:
        try:
            new_board_msg = await board_channel.send(content=content_text, embed=embed)
        except discord.Forbidden as error:
            add_bot_error_entry(payload.guild_id, config["channel_id"], None, "reaction board post", error)
            return
        config["tracked_messages"][orig_msg_id] = str(new_board_msg.id)
        save_board_data(board_data)

