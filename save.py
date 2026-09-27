"""Saving and loading: every JSON data file of the bot, the guild config defaults and the backups.

This module only uses the standard library, so any other module can import it.
"""

import json
import os
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'economy.json')
FUN_FILE = os.path.join(BASE_DIR, 'fun.json')
BOARD_FILE = os.path.join(BASE_DIR, 'board.json')
GUILD_FILE = os.path.join(BASE_DIR, 'guild.json')
LEVEL_FILE = os.path.join(BASE_DIR, 'level.json')
USER_FILE = os.path.join(BASE_DIR, 'user.json')
GIVEAWAY_FILE = os.path.join(BASE_DIR, 'giveaway.json')
RATE_FILE = os.path.join(BASE_DIR, 'rate.json')  # love-meter results
HELP_FILE = os.path.join(BASE_DIR, 'help.json')

# Kept when this module is reloaded by the cog manager (the backup thread keeps running).
_KEEP_ON_RELOAD = ("_BACKUP_SCHEDULER_THREAD",)


def load_json_file(path: str, default=None):
    if default is None:
        default = {}

    if not os.path.exists(path):
        return default

    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Warning: {os.path.basename(path)} is corrupted and could not be loaded. Returning default.")
        return default
    except OSError:
        print(f"Warning: unable to read {os.path.basename(path)}. Returning default.")
        return default


def save_json_file(path: str, data, indent: int = 4):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    temp_path = path + '.tmp'
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    except OSError as e:
        print(f"Warning: unable to save {os.path.basename(path)}: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


class DataManager:
    _cache = {}
    
    @classmethod
    def load(cls, file_path: str, default=None):
        if default is None:
            default = {}
        return load_json_file(file_path, default)
    
    @classmethod
    def save(cls, file_path: str, data):
        save_json_file(file_path, data)


def load_levels():
    return DataManager.load(LEVEL_FILE, {})

def save_levels(data):
    DataManager.save(LEVEL_FILE, data)

def load_data():
    return DataManager.load(DATA_FILE, {})

def save_data(data):
    DataManager.save(DATA_FILE, data)

def load_user_settings():
    return DataManager.load(USER_FILE, {})

def save_user_settings(data):
    DataManager.save(USER_FILE, data)


def load_giveaway_data():
    return load_json_file(GIVEAWAY_FILE, {})


def save_giveaway_data(data):
    save_json_file(GIVEAWAY_FILE, data)


def load_love_data():
    return DataManager.load(RATE_FILE, {})

def save_love_data(data):
    DataManager.save(RATE_FILE, data)

def load_fun_data():
    return DataManager.load(FUN_FILE, {})

def save_fun_data(data):
    DataManager.save(FUN_FILE, data)

def load_board_data():
    return DataManager.load(BOARD_FILE, {})

def save_board_data(data):
    DataManager.save(BOARD_FILE, data)

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
        "economy_enabled": False,
        "levels_enabled": False,
        "level_up_message_enabled": False,
        "join_dm_enabled": False,
        "join_dm_message": None,
        "join_role_ids": [],
        "counter_channels": {},
        "honeypot_channel_id": None,
        "honeypot_sanction": {},
        "ticket_channel_id": None,
        "ticket_manager_role_id": None,
        "ticket_style": "button",
        "ticket_reasons": [],
        "ticket_announce_message_id": None,
        "ticket_active_threads": {},
        "admin_log_channels": {}
    }

    # Only write when defaults were missing: this runs on almost every message.
    changed = False
    if guild_id not in data:
        data[guild_id] = default_config
        changed = True
    else:
        for key, value in default_config.items():
            if key not in data[guild_id]:
                data[guild_id][key] = value
                changed = True
    if changed:
        save_guild_data(data)
    return data[guild_id], data


def is_economy_enabled(guild_id: str) -> bool:
    return get_guild_config(guild_id)[0].get("economy_enabled", True)


def is_levels_enabled(guild_id: str) -> bool:
    return get_guild_config(guild_id)[0].get("levels_enabled", True)


def load_help_definitions() -> dict:
    if os.path.exists(HELP_FILE):
        try:
            with open(HELP_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"mini_tutorial": "", "commands": {}}
    return {"mini_tutorial": "", "commands": {}}


def create_backup(root_dir: str = BASE_DIR, backup_folder_name: str = 'backups') -> Path:
    root = Path(root_dir)
    backup_dir = root / backup_folder_name
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    now = datetime.now()
    name = now.strftime("%y.%m.%d.h%H.%M.%S")
    zip_path = backup_dir / f"{name}.zip"
    # Never overwrite an existing backup (two backups in the same second, or a restore's safety backup).
    counter = 2
    while zip_path.exists():
        zip_path = backup_dir / f"{name}-{counter}.zip"
        counter += 1

    try:
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for p in root.rglob('*.json'):
                if p.is_file():
                    try:
                        arcname = p.relative_to(root).as_posix()
                    except Exception:
                        arcname = p.name
                    zf.write(p, arcname)
        print(f"[backup] Created JSON backup: {zip_path}")
    except Exception as e:
        print(f"[backup] Failed to create backup {zip_path}: {e}")

    return zip_path


_BACKUP_SCHEDULER_THREAD: threading.Thread | None = None


def _backup_worker(interval_seconds: int = 12 * 60 * 60, root_dir: str = BASE_DIR):
    while True:
        time.sleep(interval_seconds)
        try:
            create_backup(root_dir)
        except Exception as e:
            print(f"Backup error: {e}")


def start_backup_scheduler(interval_seconds: int = 12 * 60 * 60, root_dir: str = BASE_DIR):
    global _BACKUP_SCHEDULER_THREAD

    if _BACKUP_SCHEDULER_THREAD is not None and _BACKUP_SCHEDULER_THREAD.is_alive():
        return _BACKUP_SCHEDULER_THREAD

    try:
        create_backup(root_dir)
    except Exception as e:
        print(f"Initial backup failed: {e}")

    t = threading.Thread(target=_backup_worker, args=(interval_seconds, root_dir), daemon=True)
    _BACKUP_SCHEDULER_THREAD = t
    t.start()
    print(f"[backup] auto backup scheduler started every {interval_seconds // 3600} hours")
    return t


def restore_backup(backup_file: Path, root_dir: str = BASE_DIR) -> Path:
    """Restore a backup zip over the data files. Returns the safety backup made just before."""
    backup_before_restore = create_backup(root_dir)
    with zipfile.ZipFile(backup_file, 'r') as zf:
        root = Path(root_dir).resolve()
        for member in zf.namelist():
            # Only restore files that land inside the bot folder.
            if not (root / member).resolve().is_relative_to(root):
                raise ValueError(f"Unsafe path in backup: {member}")
        zf.extractall(path=root_dir)
    return backup_before_restore


def get_backup_dir() -> Path:
    return Path(BASE_DIR) / 'backups'


def get_backup_files() -> list[Path]:
    backup_dir = get_backup_dir()
    if not backup_dir.exists():
        return []
    # Newest first; the name breaks ties between backups made in the same second.
    return sorted([p for p in backup_dir.iterdir() if p.is_file() and p.suffix == '.zip'], key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def format_backup_entry(path: Path) -> str:
    modified = datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    size = path.stat().st_size
    return f"{path.name} · {size} bytes · {modified}"
