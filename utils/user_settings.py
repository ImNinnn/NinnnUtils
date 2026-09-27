"""Per-user settings stored in user.json: profile colour, pings and timezone."""

import random
import re
from datetime import timedelta

import discord

import save

USER_COLOR_NAMES = ("white", "black", "red", "blue", "green", "yellow", "purple", "orange", "brown")
USER_COLOR_OPTIONS = ["random"] + [name for name in USER_COLOR_NAMES if name != "black"]


def get_user_settings_entry(settings: dict, user_id: str) -> dict:
    if "users" not in settings or not isinstance(settings["users"], dict):
        settings["users"] = {}

    user_key = str(user_id)
    user_settings = settings["users"].get(user_key)
    if not isinstance(user_settings, dict):
        user_settings = {}
        settings["users"][user_key] = user_settings

    return user_settings


def get_user_color(user_id: str) -> str:
    settings = save.load_user_settings()
    return get_user_settings_entry(settings, user_id).get("color", "white")


def get_user_pings_enabled(user_id: str) -> bool:
    settings = save.load_user_settings()
    return get_user_settings_entry(settings, user_id).get("user_pings", True)


def resolve_user_color_name(color_name: str | None) -> str:
    cleaned = str(color_name or "white").strip().lower()
    if cleaned == "random":
        palette = [name for name in USER_COLOR_OPTIONS if name != "random"]
        return random.choice(palette) if palette else "white"
    return cleaned if cleaned in USER_COLOR_NAMES else "white"


def get_user_color_value(user_id: str) -> discord.Color:
    settings = save.load_user_settings()
    user_settings = get_user_settings_entry(settings, user_id)
    color_name = resolve_user_color_name(user_settings.get("color", "white"))
    color_map = {
        "white": discord.Color.light_gray(),
        "black": discord.Color.dark_gray(),
        "red": discord.Color.red(),
        "blue": discord.Color.blue(),
        "green": discord.Color.green(),
        "yellow": discord.Color.gold(),
        "purple": discord.Color.purple(),
        "orange": discord.Color.orange(),
        "brown": discord.Color.dark_orange(),
    }
    return color_map.get(color_name, discord.Color.blurple())


def parse_utc_offset(offset_str: str | None) -> timedelta | None:
    if not offset_str:
        return None
    s = str(offset_str).strip()
    if not s:
        return None
    s = s.upper().lstrip("UTC").lstrip("GMT").strip()
    m = re.fullmatch(r"([+-])\s*(\d{1,2})(?::?(\d{2}))?", s)
    if not m:
        return None
    sign = -1 if m.group(1) == "-" else 1
    hours = int(m.group(2))
    minutes = int(m.group(3) or "0")
    if hours > 14 or minutes >= 60:
        return None
    return timedelta(hours=hours * sign, minutes=minutes * sign)
