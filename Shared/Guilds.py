import discord

from LowerLeveled.jsonutils import load_json_file, save_json_file
from Shared.DataManager import DataManager
from main import GUILD_FILE


def load_guild_data():
    return DataManager.load(GUILD_FILE, {})


def save_guild_data(data):
    DataManager.save(GUILD_FILE, data)

def get_guild_config(guild_id: str) -> dict:
    data = load_guild_data()
    default_config = {
        "welcome_channel_id": None,
        "goodbye_channel_id": None,
        "ghost_ping_enabled": False,
        "edit_delete_history_enabled": True,
        "level_up_message_enabled": False,
        "counter_channels": {},
        "honeypot_channel_id": None,
        "honeypot_sanction": {}
    }

    if guild_id not in data:
        data[guild_id] = default_config
    else:
        for key, value in default_config.items():
            if key not in data[guild_id]:
                data[guild_id][key] = value
    save_guild_data(data)
    return data[guild_id], data


def format_channel_reference(guild: discord.Guild, channel_id) -> str:
    if not channel_id:
        return "None"
    try:
        ch_id = int(channel_id)
    except (TypeError, ValueError):
        return str(channel_id)
    channel = guild.get_channel(ch_id)
    return channel.mention if channel else f"<#{ch_id}>"


def parse_channel_reference(guild: discord.Guild, reference: str) -> discord.abc.GuildChannel | None:
    if not reference:
        return None
    ref = reference.strip()
    if ref.startswith("<#") and ref.endswith(">"):
        ref = ref[2:-1]
    try:
        channel_id = int(ref)
    except ValueError:
        return None
    return guild.get_channel(channel_id)

def get_guild_data(data, guild_id):
    if guild_id not in data:
        data[guild_id] = {
            "users": {},
            "shop": {},
            "recipes": {},
            "item_uses": {},
            "item_values": {}
        }
    return data[guild_id]
