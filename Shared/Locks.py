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

def get_guild_admin_log_channel_ids(guild: discord.Guild) -> list[int]:
    return [cid for cid in admin_log_channels if guild.get_channel(cid) is not None]


def get_guild_locked_channel_ids(guild: discord.Guild) -> list[int]:
    return [cid for cid in locked_channels if guild.get_channel(cid) is not None]

