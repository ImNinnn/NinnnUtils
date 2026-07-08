import discord

from LowerLeveled.expr import safe_eval_math_expr
from Shared.Guilds import get_guild_config, save_guild_data
from discord import HTTPException, Forbidden, NotFound

"""HTTPException – Adding the reaction failed.
Forbidden – You do not have the proper permissions to react to the message.
NotFound – The emoji you specified was not found.
TypeError – The emoji parameter is invalid."""

def get_guild_counter_entries(guild: discord.Guild) -> list[str]:
    guild_config, _ = get_guild_config(str(guild.id))
    entries = []
    for ch_key, cfg in guild_config.get("counter_channels", {}).items():
        try:
            ch_id = int(ch_key)
            ch = guild.get_channel(ch_id)
            ch_repr = ch.mention if ch else f"<#{ch_id}>"
        except (TypeError, ValueError):
            ch_repr = str(ch_key)
        current_val = cfg.get("current_value", 0)
        entries.append(f"{ch_repr}: {current_val}")
    return entries

def get_counter_channel_config(guild_id: str, channel_id: int) -> dict | None:
    guild_config, _ = get_guild_config(guild_id)
    return guild_config.get("counter_channels", {}).get(str(channel_id))


def set_counter_channel(guild_id: str, channel_id: int, reset_on_fail: bool):
    guild_config, data = get_guild_config(guild_id)
    guild_config["counter_channels"][str(channel_id)] = {
        "current_value": 0,
        "last_user_id": None,
        "reset_on_fail": bool(reset_on_fail)
    }
    save_guild_data(data)


def remove_counter_channel(guild_id: str, channel_id: int) -> bool:
    guild_config, data = get_guild_config(guild_id)
    if str(channel_id) in guild_config.get("counter_channels", {}):
        del guild_config["counter_channels"][str(channel_id)]
        save_guild_data(data)
        return True
    return False


def update_counter_state(guild_id: str, channel_id: int, current_value: int, last_user_id: int | None):
    guild_config, data = get_guild_config(guild_id)
    config = guild_config.get("counter_channels", {}).get(str(channel_id))
    if not config:
        return
    config["current_value"] = current_value
    config["last_user_id"] = last_user_id
    save_guild_data(data)


def set_counter_value(guild_id: str, channel_id: int, value: int):
    guild_config, data = get_guild_config(guild_id)
    config = guild_config.get("counter_channels", {}).get(str(channel_id))
    if not config:
        return False
    config["current_value"] = value
    config["last_user_id"] = None
    save_guild_data(data)
    return True


def try_process_counter_message(message: discord.Message):
    guild_id = str(message.guild.id)
    config = get_counter_channel_config(guild_id, message.channel.id)
    if not config:
        return None

    content = message.content.strip()
    if not content:
        return None

    value = safe_eval_math_expr(content)
    if value is None:
        return None

    if config.get("last_user_id") == message.author.id:
        return "warn"

    expected = config.get("current_value", 0) + 1
    if value == expected:
        return "ok"
    return "bad"


def apply_counter_result(message: discord.Message, result: str):
    guild_id = str(message.guild.id)
    channel_id = message.channel.id
    config = get_counter_channel_config(guild_id, channel_id)
    if not config:
        return None

    if result == "ok":
        current = config.get("current_value", 0) + 1
        update_counter_state(guild_id, channel_id, current, message.author.id)
        return "<:approve:1517452125687513158>"
    if result == "warn":
        return "<:warning:1517452174991556758>"
    if result == "bad":
        if config.get("reset_on_fail"):
            update_counter_state(guild_id, channel_id, 0, None)
        return "<:disapprove:1517452151012589662>"
    return None


def is_counter_channel_message(message: discord.Message) -> bool:
    if message.guild is None:
        return False
    return get_counter_channel_config(str(message.guild.id), message.channel.id) is not None


async def handle_counter_message(message: discord.Message):
    result = try_process_counter_message(message)
    if result is None:
        return False
    emoji = apply_counter_result(message, result)
    if emoji:
        try:
            await message.add_reaction(emoji)
        except NotFound | Forbidden | HTTPException | TypeError:
            pass
        return True
    return False
