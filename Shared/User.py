import discord

from LowerLeveled.jsonutils import load_json_file, save_json_file
from Shared.DataManager import DataManager
from Shared.Guilds import get_guild_data
from Shared.Leveling import load_levels
from main import USER_FILE, MAX_USER_REMINDERS, MAX_USER_NOTES, MAX_USER_LIST_ITEMS


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

def can_add_user_reminder(user_id: str) -> bool:
    return len(get_user_reminders(user_id)) < MAX_USER_REMINDERS


def get_user_banner_style(user_id: str) -> str:
    settings = load_user_settings()
    return get_user_settings_entry(settings, user_id).get("banner_style", "normal")


def get_user_notes(user_id: str) -> list[str]:
    settings = load_user_settings()
    notes = get_user_settings_entry(settings, user_id).get("notes")
    if isinstance(notes, list):
        return [str(note) for note in notes[:MAX_USER_NOTES]]
    return []


def save_user_notes(user_id: str, notes: list[str]) -> None:
    settings = load_user_settings()
    user_settings = get_user_settings_entry(settings, user_id)
    user_settings["notes"] = [str(note) for note in notes[:MAX_USER_NOTES]]
    save_user_settings(settings)


def get_user_reminders(user_id: str) -> list[dict]:
    settings = load_user_settings()
    reminders = get_user_settings_entry(settings, user_id).get("reminders")
    if isinstance(reminders, list):
        valid_reminders = []
        for reminder in reminders:
            if isinstance(reminder, dict) and "name" in reminder and "when" in reminder:
                valid_reminders.append(reminder)
        return valid_reminders
    return []


def save_user_reminders(user_id: str, reminders: list[dict]) -> None:
    settings = load_user_settings()
    get_user_settings_entry(settings, user_id)["reminders"] = reminders
    save_user_settings(settings)


def get_user_lists(user_id: str) -> list[list[dict]]:
    settings = load_user_settings()
    lists = get_user_settings_entry(settings, user_id).get("lists")
    if not isinstance(lists, list) or len(lists) < 1:
        return [[]]
    first_list = lists[0]
    if isinstance(first_list, list):
        return [[item for item in first_list if isinstance(item, dict)]]
    return [[]]


def save_user_lists(user_id: str, lists: list[list[dict]]) -> None:
    settings = load_user_settings()
    user_settings = get_user_settings_entry(settings, user_id)
    normalized = []
    first_list = lists[0] if lists and isinstance(lists[0], list) else []
    normalized.append(first_list[:MAX_USER_LIST_ITEMS])
    user_settings["lists"] = normalized
    save_user_settings(settings)
