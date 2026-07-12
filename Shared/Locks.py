import os

import discord

from LowerLeveled.jsonutils import load_json_file, save_json_file
from main import LOCK_CONFIG_FILE, admin_log_channels, locked_channels


def load_lock_config():
    if not os.path.exists(LOCK_CONFIG_FILE):
        return {}, {}
    data = load_json_file(LOCK_CONFIG_FILE, {})
    try:
        locked = {int(k): v for k, v in data.get("locked_channels", {}).items()}
        admin = {int(k): v for k, v in data.get("admin_log_channels", {}).items()}
        return locked, admin
    except (ValueError, AttributeError):
        return {}, {}


def save_lock_config(locked, admin):
    save_json_file(LOCK_CONFIG_FILE, {"locked_channels": locked, "admin_log_channels": admin})

def get_locked_channel_mentions(guild: discord.Guild) -> list[str]:
    """Get mentions for locked channels"""
    return _get_channel_mentions(guild, locked_channels)