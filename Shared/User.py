import discord

from LowerLeveled.jsonutils import load_json_file, save_json_file
from Shared.DataManager import DataManager
from Shared.Guilds import get_guild_data
from Shared.Leveling import load_levels
from main import USER_FILE


def load_user_settings():
    return DataManager.load(USER_FILE, {})


def save_user_settings(data):
    DataManager.save(USER_FILE, data)

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
    settings = load_user_settings()
    return get_user_settings_entry(settings, user_id).get("color", "white")


def get_user_pings_enabled(user_id: str) -> bool:
    settings = load_user_settings()
    return get_user_settings_entry(settings, user_id).get("user_pings", True)


def get_user_has_leveled_up_before(user_id: str) -> bool:
    settings = load_user_settings()
    user_settings = get_user_settings_entry(settings, user_id)

    if "has_leveled_up_before" in user_settings:
        return bool(user_settings["has_leveled_up_before"])

    user_settings["has_leveled_up_before"] = False
    save_user_settings(settings)

    return False


def set_user_has_leveled_up_before(user_id: str, value: bool) -> None:
    settings = load_user_settings()
    get_user_settings_entry(settings, user_id)["has_leveled_up_before"] = value
    save_user_settings(settings)


def format_user_reference(user: discord.abc.User | discord.Member, settings: dict | None = None) -> str:
    if settings is None:
        settings = load_user_settings()

    if get_user_settings_entry(settings, str(user.id)).get("user_pings", True):
        return user.mention

    return getattr(user, "display_name", getattr(user, "name", str(user)))


def get_banner_name(member: discord.abc.User | discord.Member) -> str:
    display_name = member.display_name
    if any(ord(char) > 127 for char in display_name):
        return member.name
    return display_name


def format_banner_username(name: str, limit: int = 17) -> str:
    if len(name) <= limit:
        return name
    return name[:limit] + "..."

def migrate_inventory(user: dict) -> None:
    inv = user.get("inventory")
    if isinstance(inv, list):
        stacked: dict = {}
        for item in inv:
            stacked[item] = stacked.get(item, 0) + 1
        user["inventory"] = stacked


def get_user_data(data, guild_id, user_id):
    guild = get_guild_data(data, guild_id)
    user_id = str(user_id)
    if user_id not in guild["users"]:
        guild["users"][user_id] = {"balance": 0, "inventory": {}}
    migrate_inventory(guild["users"][user_id])
    return guild["users"][user_id]

def get_user_color_value(user_id: str) -> discord.Color:
    settings = load_user_settings()
    user_settings = get_user_settings_entry(settings, user_id)
    color_name = user_settings.get("color", "white")
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
