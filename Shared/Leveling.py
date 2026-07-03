def load_levels():
    return load_json_file(LEVEL_FILE, {})


def save_levels(data):
    save_json_file(LEVEL_FILE, data)

def get_xp_needed(level: int) -> int:
    return 100 + (level * 10)

def get_level_channel_id(guild_id: str):
    levels = load_levels()
    if guild_id in levels:
        return levels[guild_id].get("config", {}).get("channel_id")
    return None


def set_level_channel(guild_id: str, channel_id: int | None):
    levels = load_levels()
    if guild_id not in levels:
        levels[guild_id] = {"config": {}, "users": {}}
    if "config" not in levels[guild_id]:
        levels[guild_id]["config"] = {}
    levels[guild_id]["config"]["channel_id"] = channel_id
    save_levels(levels)
