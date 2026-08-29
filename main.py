import asyncio
import ast
import json
import os
import math
import random
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from collections import Counter
import discord
import yt_dlp
from discord import ComponentType, app_commands, Status
from discord.automod import AutoModRuleAction, AutoModTrigger
from discord.enums import AutoModRuleActionType, AutoModRuleEventType, AutoModRuleTriggerType
from discord.ext import tasks, commands
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence, ImageStat
import io
import unicodedata
from deep_translator import GoogleTranslator
import base64
import threading
import traceback
import zipfile
from pathlib import Path
from discord.ui import Modal, Separator, TextInput, View, Button, LayoutView, Container, Section, TextDisplay, MediaGallery, ChannelSelect, RoleSelect, Thumbnail
import aiohttp

try:
    import psutil
except ImportError:
    psutil = None

BOT_START_MONOTONIC = time.monotonic()


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


# -------------------------------------------------------------------------------------------------------------
#                                               Configuration
# -------------------------------------------------------------------------------------------------------------




load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
VERSION = os.getenv('BOT_VERSION')
VERSION_ALTERNATE = os.getenv('BOT_VERSION_ALTERNATE')
raw_blacklist = os.getenv('SERVER_BLACKLIST', '')
BLACKLISTED_GUILDS = [int(sid.strip()) for sid in raw_blacklist.split(',') if sid.strip().isdigit()]
ACTIVITY_TEXT = os.getenv('ACTIVITY')
SHARD_COUNT = int(os.getenv('SHARD_COUNT', '0'))
PREFIX = os.getenv('PREFIX')
OWN_PASSWORD = os.getenv('OWN_PASSWORD')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'economy.json')
RATE_FILE = os.path.join(BASE_DIR, 'rate.json')
FUN_FILE = os.path.join(BASE_DIR, 'fun.json')
BOARD_FILE = os.path.join(BASE_DIR, 'board.json')
GUILD_FILE = os.path.join(BASE_DIR, 'guild.json')
LOCK_CONFIG_FILE = os.path.join(BASE_DIR, 'lock_config.json')
                                                                       
LEVEL_FILE = os.path.join(BASE_DIR, 'level.json')
USER_FILE = os.path.join(BASE_DIR, 'user.json')
GIVEAWAY_FILE = os.path.join(BASE_DIR, 'giveaway.json')
QUEST_FILE = os.path.join(BASE_DIR, 'quest.json')
                                                                                
BANNERS_FILE = os.path.join(BASE_DIR, 'banners.json')
HELP_FILE = os.path.join(BASE_DIR, 'help.json')
BANNER_DEFS: dict | None = None


def load_help_definitions() -> dict:
    if os.path.exists(HELP_FILE):
        try:
            with open(HELP_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"mini_tutorial": "", "commands": {}}
    return {"mini_tutorial": "", "commands": {}}


def load_banner_definitions() -> dict:
    global BANNER_DEFS
    if BANNER_DEFS is not None:
        return BANNER_DEFS
    if os.path.exists(BANNERS_FILE):
        try:
            with open(BANNERS_FILE, 'r', encoding='utf-8') as f:
                BANNER_DEFS = json.load(f)
        except Exception:
            BANNER_DEFS = {}
    else:
        BANNER_DEFS = {}
    return BANNER_DEFS


def get_banner_style_entry(style_name: str) -> dict | None:
    if not style_name:
        return None
    defs = load_banner_definitions()
                  
    if style_name in defs:
        return defs.get(style_name)
                                         
    key = str(style_name).strip().lower()
    for k, v in defs.items():
        if k and k.lower() == key:
            return v
    return None


def assemble_banner_image(bg_path: str, style_name: str) -> tuple[Image.Image, dict | None]:
    background = Image.open(bg_path).convert("RGBA")
    entry = get_banner_style_entry(style_name)
    if entry and isinstance(entry.get("file"), str):
        style_file = entry.get("file")
        candidates = []
        if os.path.isabs(style_file):
            candidates.append(style_file)
        else:
            candidates.append(os.path.join(BASE_DIR, style_file))
            candidates.append(os.path.join(BASE_DIR, "newbanners", style_file))
            if style_file.endswith("~"):
                sf = style_file.rstrip("~")
                candidates.append(os.path.join(BASE_DIR, sf))
                candidates.append(os.path.join(BASE_DIR, "newbanners", sf))
            name, ext = os.path.splitext(style_file)
            if not ext:
                candidates.append(os.path.join(BASE_DIR, f"{style_file}.png"))
                candidates.append(os.path.join(BASE_DIR, "newbanners", f"{style_file}.png"))

        style_path = None
        for cand in candidates:
            if cand and os.path.exists(cand):
                style_path = cand
                break

        if style_path:
            try:
                overlay = Image.open(style_path).convert("RGBA")
                target_w, target_h = 680, 382
                bg_w, bg_h = background.size
                if overlay.size != (target_w, target_h):
                    overlay_resized = overlay.resize((target_w, target_h))
                else:
                    overlay_resized = overlay

                layer = Image.new("RGBA", background.size, (0, 0, 0, 0))
                paste_x = (bg_w - target_w) // 2
                paste_y = (bg_h - target_h) // 2
                layer.paste(overlay_resized, (paste_x, paste_y), overlay_resized)
                background = Image.alpha_composite(background, layer)
            except Exception:
                pass
    overlays = []
    if entry:
        if isinstance(entry.get("mg"), str):
            overlays.append(entry.get("mg"))
        if isinstance(entry.get("overlay"), str):
            overlays.append(entry.get("overlay"))
        if isinstance(entry.get("overlay"), list):
            overlays.extend([p for p in entry.get("overlay") if isinstance(p, str)])

    for ov in overlays:
        candidates = []
        if os.path.isabs(ov):
            candidates.append(ov)
        else:
            candidates.append(os.path.join(BASE_DIR, ov))
            candidates.append(os.path.join(BASE_DIR, "newbanners", ov))
            if ov.endswith("~"):
                ov2 = ov.rstrip("~")
                candidates.append(os.path.join(BASE_DIR, ov2))
                candidates.append(os.path.join(BASE_DIR, "newbanners", ov2))
            name, ext = os.path.splitext(ov)
            if not ext:
                candidates.append(os.path.join(BASE_DIR, f"{ov}.png"))
                candidates.append(os.path.join(BASE_DIR, "newbanners", f"{ov}.png"))

        ov_path = None
        for cand in candidates:
            if cand and os.path.exists(cand):
                ov_path = cand
                break
        if ov_path:
            try:
                overlay = Image.open(ov_path).convert("RGBA")
                if overlay.size != background.size:
                    overlay = overlay.resize(background.size)
                background = Image.alpha_composite(background, overlay)
            except Exception:
                pass

    return background, entry


def apply_named_overlay(background: Image.Image, overlay_name: str) -> Image.Image:
    if not overlay_name:
        return background
    candidates = []
    if os.path.isabs(overlay_name):
        candidates.append(overlay_name)
    else:
        candidates.append(os.path.join(BASE_DIR, overlay_name))
        candidates.append(os.path.join(BASE_DIR, "newbanners", overlay_name))
        if overlay_name.endswith("~"):
            on = overlay_name.rstrip("~")
            candidates.append(os.path.join(BASE_DIR, on))
            candidates.append(os.path.join(BASE_DIR, "newbanners", on))
        name, ext = os.path.splitext(overlay_name)
        if not ext:
            candidates.append(os.path.join(BASE_DIR, f"{overlay_name}.png"))
            candidates.append(os.path.join(BASE_DIR, "newbanners", f"{overlay_name}.png"))

    ov_path = None
    for cand in candidates:
        if cand and os.path.exists(cand):
            ov_path = cand
            break
    if not ov_path:
        return background
    try:
        overlay = Image.open(ov_path).convert("RGBA")
        if overlay.size != background.size:
            overlay = overlay.resize(background.size)
        background = Image.alpha_composite(background, overlay)
    except Exception:
        pass
    return background


def pick_text_color(entry: dict | None, background: Image.Image) -> tuple[int, int, int]:
                                            
    if entry and entry.get("textcolor"):
        c = str(entry.get("textcolor")).lower()
        if c in {"white", "#fff", "#ffffff"}:
            return (255, 255, 255)
        if c in {"black", "#000", "#000000"}:
            return (0, 0, 0)
        if c.startswith("#") and len(c) == 7:
            try:
                return tuple(int(c[i:i+2], 16) for i in (1, 3, 5))
            except Exception:
                pass

                                                                                        
    try:
        gray = background.convert("L")
        stat = ImageStat.Stat(gray)
        avg = stat.mean[0]
        return (0, 0, 0) if avg > 180 else (255, 255, 255)
    except Exception:
        return (255, 255, 255)


def get_opposite_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    if not isinstance(color, tuple):
        return (0, 0, 0)
    r, g, b = color
    return (255 - r, 255 - g, 255 - b)




# -------------------------------------------------------------------------------------------------------------
#                                               Bot Setup
# -------------------------------------------------------------------------------------------------------------




class MyDiscordApp(commands.AutoShardedBot):
    def __init__(self, intents, shard_count: int = 0):
        super().__init__(
            command_prefix={PREFIX},
            intents=intents,
            shard_count=shard_count or None,
            help_command=None,
        )


    async def setup_hook(self):
        shard_info = (
            f"{self.shard_count} shard(s)" if self.shard_count else "auto sharding"
        )
        print(f"[Sharding] Running with {shard_info}")
        await self.tree.sync()
        print("Slash commands synced!")

    async def on_shard_ready(self, shard_id: int):
        print(f"[Shard {shard_id}] Ready")

    async def on_shard_connect(self, shard_id: int):
        print(f"[Shard {shard_id}] Connected")

    async def on_shard_disconnect(self, shard_id: int):
        print(f"[Shard {shard_id}] Disconnected")

    async def on_shard_resumed(self, shard_id: int):
        print(f"[Shard {shard_id}] Resumed")


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = False
intents.auto_moderation_execution = True
bot = MyDiscordApp(intents=intents, shard_count=SHARD_COUNT)


                                  

                                                                                  
                                                                             
                                                                                   





# -------------------------------------------------------------------------------------------------------------
#                                               Message Cache
# -------------------------------------------------------------------------------------------------------------




message_cache = []
deleted_cache = []
edited_cache = []
bot_error_cache = []
where_ping_cache = []
active_minigame_users = set()
reaction_xp_cooldowns = {}




# -------------------------------------------------------------------------------------------------------------
#                                               Data Management
# -------------------------------------------------------------------------------------------------------------




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

def get_xp_needed(level: int) -> int:
    return 100 + (level * 10)

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


def load_quest_data():
    return DataManager.load(QUEST_FILE, {})


def save_quest_data(data):
    DataManager.save(QUEST_FILE, data)


def _next_daily_reset(now: datetime | None = None) -> datetime:
    if now is None:
        now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return tomorrow


def _next_weekly_reset(assigned_at_iso: str | None) -> datetime:
    if not assigned_at_iso:
        return datetime.now(timezone.utc) + timedelta(days=7)
    try:
        assigned = datetime.fromisoformat(assigned_at_iso)
        return assigned + timedelta(days=7)
    except Exception:
        return datetime.now(timezone.utc) + timedelta(days=7)


DAILY_EASY_TEMPLATES = [
    ("Send messages", "messages", (5, 15)),
    ("Be in voice", "voice_minutes", (10, 10)),
    ("Play & win Minesweeper", "win_mines", (1, 1)),
    ("Play & win Towers", "win_towers", (1, 1)),
    ("Play work (easy/normal) and win", "work_win_easy_normal", (1, 1)),
    ("Play coinflip", "coinflip", (1, 1)),
    ("Craft an item", "craft", (1, 1)),
    ("Buy 3 items", "buy", (3, 3)),
    ("Sell an item", "sell", (1, 1)),
    ("Use an item", "use", (1, 1)),
    ("Gain a level", "gain_levels", (1, 1)),
]

DAILY_HARD_TEMPLATES = [
    ("Send messages (hard)", "messages", (15, 30)),
    ("Be in voice (hard)", "voice_minutes", (20, 20)),
    ("Play & win Towers (hard)", "win_towers", (1, 1)),
    ("Play work (hard) and win", "work_win_hard", (1, 1)),
    ("Play & win coinflip", "coinflip_win", (1, 1)),
    ("Craft 3 items", "craft", (3, 3)),
    ("Buy 6 items", "buy", (6, 6)),
    ("Sell 3 items", "sell", (3, 3)),
    ("Use 3 items", "use", (3, 3)),
    ("Gain 3 levels", "gain_levels", (3, 3)),
]

WEEKLY_TEMPLATES = [
    ("Complete 7 daily quests", "complete_daily_count", (7, 7)),
    ("Send messages (weekly)", "messages", (200, 250)),
    ("Be in voice (weekly)", "voice_minutes", (60, 60)),
]


def _make_quest_entry(name: str, qtype: str, target_range: tuple[int, int], reward_money_range: tuple[int, int], reward_xp_range: tuple[int, int], period: str, assigned_at: datetime = None) -> dict:
    if assigned_at is None:
        assigned_at = datetime.now(timezone.utc)
    low, high = target_range
    target = random.randint(low, high) if low != high else low
    money = random.randint(reward_money_range[0], reward_money_range[1])
    xp = random.randint(reward_xp_range[0], reward_xp_range[1])
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "type": qtype,
        "target": target,
        "progress": 0,
        "reward_money": money,
        "reward_xp": xp,
        "period": period,
        "assigned_at": assigned_at.isoformat(),
        "completed": False,
    }


def ensure_user_quests(guild_id: str, user_id: str) -> dict:
    data = load_quest_data()
    guild = data.setdefault(guild_id, {})
    users = guild.setdefault("users", {})
    user_entry = users.setdefault(user_id, {})

    now = datetime.now(timezone.utc)

                  
    daily = user_entry.get("daily", {})
    assigned_iso = daily.get("assigned_at")
    regenerate_daily = True
    if assigned_iso:
        try:
            assigned = datetime.fromisoformat(assigned_iso)
            if now < _next_daily_reset(assigned):
                regenerate_daily = False
        except Exception:
            regenerate_daily = True

    if regenerate_daily:
                                                 
                                                                                                      
        guild_data = get_guild_data(load_data(), guild_id)

        def _template_applicable(tpl: tuple[str, str, tuple[int, int]], gdata: dict) -> bool:
            _name, _type, _range = tpl
            if _type in {"buy", "shop"}:
                return bool(gdata.get("shop") or gdata.get("item_values"))
            if _type == "sell":
                return bool(gdata.get("item_values"))
            if _type == "craft":
                return bool(gdata.get("recipes"))
            if _type == "use":
                return bool(gdata.get("item_uses"))
                                
            return True

        easy_candidates = [t for t in DAILY_EASY_TEMPLATES if _template_applicable(t, guild_data)]
        hard_candidates = [t for t in DAILY_HARD_TEMPLATES if _template_applicable(t, guild_data)]

                                                                                    
        if not easy_candidates:
            easy_candidates = [t for t in DAILY_EASY_TEMPLATES if t[1] not in {"buy", "sell", "craft", "use", "shop"}]
        if not hard_candidates:
            hard_candidates = [t for t in DAILY_HARD_TEMPLATES if t[1] not in {"buy", "sell", "craft", "use", "shop"}]

                                          
        if not easy_candidates:
            easy_candidates = DAILY_EASY_TEMPLATES
        if not hard_candidates:
            hard_candidates = DAILY_HARD_TEMPLATES

        q1_name, q1_type, q1_range = random.choice(easy_candidates)
        q2_name, q2_type, q2_range = random.choice(hard_candidates)
        q1 = _make_quest_entry(q1_name, q1_type, q1_range, (900, 1100), (40, 60), "daily", assigned_at=now)
        q2 = _make_quest_entry(q2_name, q2_type, q2_range, (1400, 1600), (65, 85), "daily", assigned_at=now)
        user_entry["daily"] = {"assigned_at": now.isoformat(), "quests": [q1, q2], "completed_count": 0}

                  
    weekly = user_entry.get("weekly", {})
    w_assigned_iso = weekly.get("assigned_at")
    regenerate_weekly = True
    if w_assigned_iso:
        try:
            w_assigned = datetime.fromisoformat(w_assigned_iso)
            if now < _next_weekly_reset(w_assigned_iso):
                regenerate_weekly = False
        except Exception:
            regenerate_weekly = True

    if regenerate_weekly:
                                                             
        guild_data = get_guild_data(load_data(), guild_id)
        weekly_candidates = [t for t in WEEKLY_TEMPLATES if _template_applicable(t, guild_data)]
        if not weekly_candidates:
            weekly_candidates = [t for t in WEEKLY_TEMPLATES if t[1] not in {"buy", "sell", "craft", "use", "shop"}]
        if not weekly_candidates:
            weekly_candidates = WEEKLY_TEMPLATES
        w_name, w_type, w_range = random.choice(weekly_candidates)
        wq = _make_quest_entry(w_name, w_type, w_range, (2900, 3100), (290, 310), "weekly", assigned_at=now)
        user_entry["weekly"] = {"assigned_at": now.isoformat(), "quest": wq}

    users[user_id] = user_entry
    data[guild_id] = guild
    save_quest_data(data)
    return user_entry


async def _complete_quest(guild: discord.Guild, member: discord.Member, quest: dict):
                                  
    if not is_economy_enabled(str(guild.id)) or not is_levels_enabled(str(guild.id)):
        return

           
    data = load_data()
    eco_user = get_user_data(data, str(guild.id), member.id)
    eco_user["balance"] = eco_user.get("balance", 0) + int(quest.get("reward_money", 0))
    save_data(data)

        
    await add_xp(member, guild, int(quest.get("reward_xp", 0)), announce_channel=None)

              
    levels = load_levels()
    channel_id = levels.get(str(guild.id), {}).get("config", {}).get("channel_id")
    target_channel = guild.get_channel(int(channel_id)) if channel_id else None
    guild_config = get_guild_config(str(guild.id))[0]

    message_text = f"{member.display_name} completed a quest: **{quest.get('name')}** and earned ${quest.get('reward_money')} and {quest.get('reward_xp')} XP!"

                                                                                                                              
    try:
        style = get_user_banner_style(str(member.id))
        preview = await create_banner_preview(member, kind="quest", style_override=style, quest_text=str(quest.get('name') or ""))
        if preview is not None:
            if target_channel:
                try:
                    await target_channel.send(content=message_text, file=preview)
                    return
                except Exception:
                    pass
                                            
            if guild.system_channel:
                try:
                    await guild.system_channel.send(content=message_text, file=preview)
                    return
                except Exception:
                    pass
    except Exception:
        pass

                                                                                                         
    if target_channel and guild_config.get("level_up_message_enabled", False):
        try:
            await target_channel.send(message_text)
        except Exception:
            pass


async def increment_quest_progress(guild: discord.Guild, member: discord.Member, event: str, amount: int = 1):
    if member.bot:
        return
    if not is_economy_enabled(str(guild.id)) or not is_levels_enabled(str(guild.id)):
        return

    data = load_quest_data()
    guild_entry = data.get(str(guild.id), {})
    users = guild_entry.get("users", {})
    user_entry = users.get(str(member.id))
    if not user_entry:
        user_entry = ensure_user_quests(str(guild.id), str(member.id))

    changed = False
                  
    daily = user_entry.get("daily", {}).get("quests", [])
    for q in daily:
        if not q.get("completed") and q.get("type") == event:
            q["progress"] = min(q.get("target", 0), q.get("progress", 0) + amount)
            changed = True
            if q["progress"] >= q["target"]:
                q["completed"] = True
                user_entry["daily"]["completed_count"] = user_entry["daily"].get("completed_count", 0) + 1
                await _complete_quest(guild, member, q)
                                                                                  
                try:
                    weekly = user_entry.get("weekly", {}).get("quest")
                    if weekly and not weekly.get("completed") and weekly.get("type") == "complete_daily_count":
                        comp = user_entry["daily"].get("completed_count", 0)
                        weekly["progress"] = min(weekly.get("target", 0), comp)
                        changed = True
                        if weekly["progress"] >= weekly.get("target", 0):
                            weekly["completed"] = True
                            await _complete_quest(guild, member, weekly)
                except Exception:
                    pass

                  
    weekly = user_entry.get("weekly", {}).get("quest")
    if weekly and not weekly.get("completed") and weekly.get("type") == event:
        weekly["progress"] = min(weekly.get("target", 0), weekly.get("progress", 0) + amount)
        changed = True
        if weekly["progress"] >= weekly["target"]:
            weekly["completed"] = True
            await _complete_quest(guild, member, weekly)

    if changed:
        users[str(member.id)] = user_entry
        guild_entry["users"] = users
        data[str(guild.id)] = guild_entry
        save_quest_data(data)



def parse_duration_to_seconds(value: str) -> int | None:
    if not value:
        return None

    text = value.strip().lower()
    if not re.fullmatch(r'(?:\d+[dhms]\s*)+', text):
        return None

    total_seconds = 0
    for amount, unit in re.findall(r'(\d+)([dhms])', text):
        amount = int(amount)
        if unit == 'd':
            total_seconds += amount * 86400
        elif unit == 'h':
            total_seconds += amount * 3600
        elif unit == 'm':
            total_seconds += amount * 60
        else:
            total_seconds += amount

    return total_seconds


def build_giveaway_embed(giveaway: dict) -> discord.Embed:
    title = giveaway.get('name', 'Giveaway')
    host_id = giveaway.get('host_id')
    host_value = f"<@{host_id}>" if host_id else "Unknown"
    entries = giveaway.get('entries', [])

    reward_parts = []
    if giveaway.get('role_id'):
        role = bot.get_guild(int(giveaway['guild_id'])).get_role(int(giveaway['role_id'])) if bot.get_guild(int(giveaway['guild_id'])) else None
        reward_parts.append(f"Role: {role.name if role else 'Unknown role'}")
    if giveaway.get('temp_role_id'):
        role = bot.get_guild(int(giveaway['guild_id'])).get_role(int(giveaway['temp_role_id'])) if bot.get_guild(int(giveaway['guild_id'])) else None
        reward_parts.append(f"Temp role: {role.name if role else 'Unknown role'} ({giveaway.get('temp_role_time', 0)}m)")
    if giveaway.get('item'):
        reward_parts.append(f"Item: {giveaway['item']}")
    if giveaway.get('money', 0):
        reward_parts.append(f"Money: ${giveaway['money']}")
    if giveaway.get('xp', 0):
        reward_parts.append(f"XP: {giveaway['xp']}")

    reward_text = "\n".join(reward_parts) if reward_parts else "No rewards"
    
    if giveaway.get('status') == 'ended':
        embed = discord.Embed(title=f"<:present:1522648005650415658> {title}", description="Giveaway ended", color=discord.Color.red())
    else:
        embed = discord.Embed(title=f"<:present:1522648005650415658> {title}", description="━━━━━━━━━━━━━━", color=discord.Color.gold())

    embed.add_field(name="Host", value=host_value, inline=True)
    embed.add_field(name="Winners", value=str(giveaway.get('winners_count', 1)), inline=True)
    embed.add_field(name="Entries", value=str(len(entries)), inline=False)
    embed.add_field(name="Rewards", value=reward_text, inline=False)
    embed.add_field(name="Ends", value=f"<t:{giveaway.get('end_time')}:R>", inline=False)
    return embed


class LeaveGiveawayConfirmView(View):
    def __init__(self, giveaway_id: str, original_message, user_id: str):
        super().__init__(timeout=600)
        self.giveaway_id = giveaway_id
        self.original_message = original_message
        self.user_id = user_id

    @discord.ui.button(label="Leave giveaway", style=discord.ButtonStyle.danger)
    async def confirm_leave(self, interaction: discord.Interaction, button: Button):
        data = load_giveaway_data()
        giveaway = data.get(self.giveaway_id)
        if not giveaway or giveaway.get('status') != 'active':
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("This giveaway is no longer active.", ephemeral=True)
            return

        updated_entries = [entry for entry in giveaway.get('entries', []) if str(entry) != self.user_id]
        giveaway['entries'] = updated_entries
        data[self.giveaway_id] = giveaway
        save_giveaway_data(data)

        updated_view = GiveawayView(self.giveaway_id, giveaway)
        try:
            if self.original_message is not None:
                await self.original_message.edit(view=updated_view)
        except Exception:
            pass

        await interaction.response.defer(ephemeral=True); await interaction.followup.send("You left the giveaway.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_leave(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Okay, you stayed in the giveaway.", ephemeral=True)


class GiveawayView(LayoutView):
    def __init__(self, giveaway_id: str, giveaway: dict):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.giveaway = giveaway
        self.build_components()

    def build_components(self):
        self.clear_items()
        giveaway = self.giveaway
        entries = giveaway.get('entries', [])

        entry_button = Button(
            label="Enter giveaway !",
            style=discord.ButtonStyle.success,
            custom_id=f"giveaway_enter:{self.giveaway_id}",
        )

        async def on_enter(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)

            data = load_giveaway_data()
            giveaway = data.get(self.giveaway_id)
            if not giveaway or giveaway.get('status') != 'active':
                await interaction.followup.send("This giveaway is no longer active.", ephemeral=True)
                return

            user_id = str(interaction.user.id)
            normalized_entries = [str(entry) for entry in giveaway.get('entries', []) if entry]
            if user_id in normalized_entries:
                confirm_view = LeaveGiveawayConfirmView(self.giveaway_id, interaction.message, user_id)
                await interaction.followup.send(
                    "You are already entered in this giveaway. Do you want to leave it?",
                    view=confirm_view,
                    ephemeral=True,
                )
                return

            normalized_entries.append(user_id)
            giveaway['entries'] = normalized_entries
            data[self.giveaway_id] = giveaway
            save_giveaway_data(data)

            updated_view = GiveawayView(self.giveaway_id, giveaway)
            try:
                await interaction.message.edit(view=updated_view)
            except Exception:
                pass

            await interaction.followup.send("You joined the giveaway!", ephemeral=True)

        entry_button.callback = on_enter

        host_id = giveaway.get('host_id')
        host_value = f"<@{host_id}>" if host_id else "Unknown"

        reward_parts = []
        if giveaway.get('role_id'):
            role = bot.get_guild(int(giveaway['guild_id'])).get_role(int(giveaway['role_id'])) if bot.get_guild(int(giveaway['guild_id'])) else None
            reward_parts.append(f"Role: {role.name if role else 'Unknown role'}")
        if giveaway.get('temp_role_id'):
            role = bot.get_guild(int(giveaway['guild_id'])).get_role(int(giveaway['temp_role_id'])) if bot.get_guild(int(giveaway['guild_id'])) else None
            reward_parts.append(f"Temp role: {role.name if role else 'Unknown role'} ({giveaway.get('temp_role_time', 0)}m)")
        if giveaway.get('item'):
            reward_parts.append(f"Item: {giveaway['item']}")
        if giveaway.get('money', 0):
            reward_parts.append(f"Money: ${giveaway['money']}")
        if giveaway.get('xp', 0):
            reward_parts.append(f"XP: {giveaway['xp']}")

        reward_text = "\n".join(reward_parts) if reward_parts else "No rewards"

        container_items = [
            TextDisplay(f"<:present:1522648005650415658> {giveaway['name']}"),
            Separator(),
            TextDisplay(f"**Host:** {host_value}\n**Winners:** {giveaway.get('winners_count', 1)}"),
        ]

        if giveaway.get('status') == 'active':
            container_items.append(
                Section(
                    f"**Entries:** {len(entries)}",
                    accessory=entry_button,
                )
            )
        else:
            container_items.append(TextDisplay(f"**Entries:** {len(entries)}"))

        container_items.extend([
            Separator(),
            TextDisplay(f"**Rewards:**\n{reward_text}"),
            Separator(),
            TextDisplay(f"**Ends:** <t:{giveaway.get('end_time')}:R>"),
        ])

        container = Container(
            *container_items,
            accent_color=discord.Color.gold() if giveaway.get('status') == 'active' else discord.Color.red(),
        )
        self.add_item(container)


async def finalize_giveaway(giveaway_id: str, giveaway: dict):
    guild = bot.get_guild(int(giveaway['guild_id'])) if giveaway.get('guild_id') else None
    entries = [entry for entry in giveaway.get('entries', []) if entry]
    winners = []
    if entries:
        winner_count = max(1, int(giveaway.get('winners_count', 1)))
        winners = random.sample(entries, k=min(winner_count, len(entries)))

    channel = bot.get_channel(int(giveaway['channel_id'])) if giveaway.get('channel_id') else None
    if channel and giveaway.get('message_id'):
        try:
            message = await channel.fetch_message(int(giveaway['message_id']))
            giveaway['status'] = 'ended'
            view = GiveawayView(giveaway_id, giveaway)
            await message.edit(view=view)
        except Exception:
            pass

    winner_references = []
    if guild:
        role = guild.get_role(int(giveaway['role_id'])) if giveaway.get('role_id') else None
        temp_role = guild.get_role(int(giveaway['temp_role_id'])) if giveaway.get('temp_role_id') else None

        for winner_id in winners:
            member = guild.get_member(int(winner_id))
            if member:
                winner_references.append(format_user_reference(member))
            if role and member:
                try:
                    await member.add_roles(role, reason=f"Giveaway winner for {giveaway['name']}")
                except Exception:
                    pass
            if temp_role and member and giveaway.get('temp_role_time', 0) > 0:
                try:
                    await member.add_roles(temp_role, reason=f"Temporary giveaway role for {giveaway['name']}")
                    async def remove_temp_role():
                        await asyncio.sleep(int(giveaway['temp_role_time']) * 60)
                        try:
                            await member.remove_roles(temp_role, reason="Temporary giveaway role expired")
                        except Exception:
                            pass
                    asyncio.create_task(remove_temp_role())
                except Exception:
                    pass

            if giveaway.get('money', 0) or giveaway.get('xp', 0) or giveaway.get('item'):
                if giveaway.get('money', 0) or giveaway.get('item'):
                    economy_data = load_data()
                    guild_data = economy_data.setdefault(str(guild.id), {})
                    users = guild_data.setdefault('users', {})
                    user_data = users.setdefault(str(winner_id), {"balance": 0, "inventory": {}})
                    user_data.setdefault("inventory", {})
                    if giveaway.get('money', 0):
                        user_data['balance'] = user_data.get('balance', 0) + int(giveaway['money'])
                    if giveaway.get('item'):
                        inventory_add(user_data['inventory'], giveaway['item'], 1)
                    save_data(economy_data)
                if giveaway.get('xp', 0) and member:
                    await add_xp(member, guild, int(giveaway['xp']), announce_channel=channel)

            try:
                user = await bot.fetch_user(int(winner_id))
                if user:
                    dm_embed = discord.Embed(
                        title="<:spark:1517583248421552305> Giveaway Win!",
                        description=f"You won the giveaway **{giveaway['name']}** in **{guild.name}**.",
                        color=discord.Color.green(),
                    )
                    if role:
                        dm_embed.add_field(name="<:bell:1517497562184024275> Role", value=role.name, inline=True)
                    if temp_role:
                        dm_embed.add_field(name="<:timer:1517996239583576194> Temp Role", value=f"{temp_role.name} ({giveaway.get('temp_role_time', 0)}m)", inline=True)
                    if giveaway.get('money', 0):
                        dm_embed.add_field(name="<:money:1517580310395486239> Money", value=f"${giveaway['money']}", inline=True)
                    if giveaway.get('xp', 0):
                        dm_embed.add_field(name="<:Vial:1517681553377857628> XP", value=str(giveaway['xp']), inline=True)
                    if giveaway.get('item'):
                        dm_embed.add_field(name="<:box:1517581439552585759> Item", value=giveaway['item'], inline=True)
                    await user.send(embed=dm_embed)
            except Exception:
                pass

    if channel:
        if winners:
            winner_text = ", ".join(winner_references) if winner_references else "unknown winners"
            try:
                await channel.send(f"<:spark:1517583248421552305> Giveaway **{giveaway['name']}** has ended! Winners: {winner_text}")
            except Exception as e:
                try:
                    add_bot_error_entry(guild.id if guild else None, channel.id if hasattr(channel, 'id') else None, None, "giveaway: send winners", e)
                except Exception:
                    pass
        else:
            try:
                await channel.send(f"<:spark:1517583248421552305> Giveaway **{giveaway['name']}** has ended with no entries.")
            except Exception as e:
                try:
                    add_bot_error_entry(guild.id if guild else None, channel.id if hasattr(channel, 'id') else None, None, "giveaway: send no-entries", e)
                except Exception:
                    pass

    data = load_giveaway_data()
    if giveaway_id in data:
        del data[giveaway_id]
        save_giveaway_data(data)


@tasks.loop(minutes=1)
async def giveaway_loop():
                                                                         
                                                                                  
    return


@tasks.loop(seconds=30)
async def giveaway_refresh_loop():
    data = load_giveaway_data()
    if not data:
        return

    for giveaway_id, giveaway in list(data.items()):
        if giveaway.get('status') != 'active':
            continue

        channel = bot.get_channel(int(giveaway['channel_id'])) if giveaway.get('channel_id') else None
        if not channel or not giveaway.get('message_id'):
            continue

        try:
            message = await channel.fetch_message(int(giveaway['message_id']))
            await message.edit(view=GiveawayView(giveaway_id, giveaway))
        except Exception:
            pass


@giveaway_loop.before_loop
async def before_giveaway_loop():
    await bot.wait_until_ready()


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


MAX_USER_NOTES = 3
MAX_USER_REMINDERS = 7
MAX_USER_LIST_ITEMS = 30
CHECKLIST_PAGE_SIZE = 10


def can_add_user_reminder(user_id: str) -> bool:
    return len(get_user_reminders(user_id)) < MAX_USER_REMINDERS


def normalize_banner_style(style: str | None) -> str:
    name = str(style or "normal").strip().lower()
    defs = load_banner_definitions()
    if name == "random":
        keys = list(defs.keys())
        if keys:
            return random.choice(keys)
        return "normal"

                                                           
    if name in defs:
        return name

                                                                 
    aliases = {
        "normal": "normal",
        "alt": "alt",
        "alternate": "alt",
        "1000": "1000",
        "milestone": "1000",
        "milestone1000": "1000",
        "admin": "admin",
        "administrator": "admin",
    }
    mapped = aliases.get(name)
    if mapped and mapped in defs:
        return mapped
                                                             
    if defs:
        return next(iter(defs.keys()))
    return "normal"


def format_banner_style_label(style: str | None) -> str:
    name = str(style or "normal").strip().lower()
    if name == "random":
        return "Random"
    normalized = normalize_banner_style(name)
    entry = get_banner_style_entry(normalized)
    if entry and isinstance(entry.get("label"), str):
        return entry.get("label")
    return normalized.title()


def get_banner_search_matches(definitions: dict, query: str) -> list[str]:
    q = (query or "").strip().lower()
    if not q:
        return list(definitions.keys())

    category_prefix = "category:"
    target = q
    if q.startswith(category_prefix):
        target = q[len(category_prefix):].strip()

    matches = []
    for name in definitions.keys():
        entry = definitions.get(name) or {}
        category = str(entry.get("category") or "").strip()
        label = str(entry.get("label") or "").strip()
        description = str(entry.get("desc") or "").strip()
        tokens = [
            name,
            name.replace("_", " "),
            category,
            category.lower(),
            label,
            description,
        ]
        haystack = " ".join(token for token in tokens if token).lower()

        if q.startswith(category_prefix):
            if target and target in category.lower():
                matches.append(name)
            continue

        if target and (target in haystack or target in name.lower() or target in category.lower()):
            matches.append(name)

    return matches


def get_user_banner_style(user_id: str) -> str:
    settings = load_user_settings()
    style = get_user_settings_entry(settings, user_id).get("banner_style", "normal")
    return normalize_banner_style(style)


def ensure_user_banner_assigned(user_id: str) -> str:
    settings = load_user_settings()
    entry = get_user_settings_entry(settings, user_id)
    style = entry.get("banner_style", None)
    if style is None:
        defs = load_banner_definitions()
        keys = [k for k in defs.keys() if k and k.lower() != "random"]
        chosen = random.choice(keys) if keys else "normal"
        entry["banner_style"] = chosen
        save_user_settings(settings)
        return normalize_banner_style(chosen)
    return normalize_banner_style(style)


def get_banner_asset_path(kind: str, style: str, *, allow_legacy: bool = True) -> str | None:
    base_dir = os.path.dirname(__file__)
    banner_dir = os.path.join(base_dir, "banners")
    style_name = normalize_banner_style(style)
    kind_name = (str(kind) or "").strip().lower()

                                                                                                                   
    candidates = [
        os.path.join(base_dir, "newbanners", f"{kind_name}.png"),
        os.path.join(base_dir, "newbanners", f"{kind_name}_{style_name}.png"),
        os.path.join(banner_dir, f"{kind_name}.png"),
        os.path.join(banner_dir, f"{kind_name}_{style_name}.png"),
        os.path.join(base_dir, f"{kind_name}.png"),
        os.path.join(base_dir, f"{kind_name}_{style_name}.png"),
    ]

    if allow_legacy:
        legacy_names = {
            "welcome_bg": ["welcome_bg.png", "welcome_bg_normal.png"],
            "goodbye_bg": ["goodbye_bg.png", "goodbye_bg_normal.png"],
            "levelup_bg": ["levelup_bg.png", "levelup_bg_normal.png"],
            "quest_bg": ["quest_bg.png", "quest_bg_normal.png"],
        }
        for legacy_name in legacy_names.get(kind, []):
            candidates.append(os.path.join(base_dir, legacy_name))

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
                                                            
    generic = os.path.join(base_dir, "newbanners", "banner_size.png")
    if os.path.exists(generic):
        return generic
    return None


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


def parse_utc_offset(offset_str: str) -> timedelta | None:
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


def parse_reminder_time(value: str, user_id: str | None = None) -> int | None:
    if not value:
        return None

    text = value.strip()
                                                          
    if text.lower().startswith("in "):
        text = text[3:].strip()
    elif text.lower().startswith("at "):
        text = text[3:].strip()

                                                                                           
    if re.fullmatch(r'(?:\d+[dhms]\s*)+', text.lower()):
        seconds = parse_duration_to_seconds(text)
        if seconds is None or seconds <= 0:
            return None
        return int(datetime.now(timezone.utc).timestamp()) + seconds

                                                                                     
    offs = None
    if user_id is not None:
        try:
            settings = load_user_settings()
            entry = get_user_settings_entry(settings, str(user_id))
            off = entry.get("timezone_offset")
            offs = parse_utc_offset(off) if off else None
        except Exception:
            offs = None

    now_utc = datetime.now(timezone.utc)

                                                                           
    m_time = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if m_time:
        hour = int(m_time.group(1))
        minute = int(m_time.group(2))
                              
        if offs is not None:
            now_local = (now_utc + offs)
        else:
            now_local = now_utc
        try:
            candidate_local = datetime(now_local.year, now_local.month, now_local.day, hour, minute)
        except ValueError:
            return None
                                                 
        if offs is not None:
            candidate_utc = candidate_local - offs
        else:
            candidate_utc = candidate_local
        candidate_utc = candidate_utc.replace(tzinfo=timezone.utc)
        if candidate_utc <= now_utc:
            candidate_local = candidate_local + timedelta(days=1)
            if offs is not None:
                candidate_utc = (candidate_local - offs).replace(tzinfo=timezone.utc)
            else:
                candidate_utc = candidate_local.replace(tzinfo=timezone.utc)
        return int(candidate_utc.timestamp())

                                                                                                         
    m_date = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?:\s+(\d{1,2}):(\d{2}))?", text)
    if m_date:
        day = int(m_date.group(1))
        month = int(m_date.group(2))
        year_group = m_date.group(3)
        hour = int(m_date.group(4)) if m_date.group(4) else 0
        minute = int(m_date.group(5)) if m_date.group(5) else 0

                                                                 
        if year_group:
            y = int(year_group)
            if y < 100:
                y += 2000
            try:
                reminder_local = datetime(y, month, day, hour, minute)
            except ValueError:
                return None
            if offs is not None:
                reminder_utc = reminder_local - offs
            else:
                reminder_utc = reminder_local
            reminder_utc = reminder_utc.replace(tzinfo=timezone.utc)
            if reminder_utc <= now_utc:
                return None
            return int(reminder_utc.timestamp())
        else:
                                                                            
            if offs is not None:
                now_local = (now_utc + offs)
            else:
                now_local = now_utc
            year = now_local.year
            try:
                candidate_local = datetime(year, month, day, hour, minute)
            except ValueError:
                return None
            if offs is not None:
                candidate_utc = (candidate_local - offs).replace(tzinfo=timezone.utc)
            else:
                candidate_utc = candidate_local.replace(tzinfo=timezone.utc)
            if candidate_utc <= now_utc:
                try:
                    candidate_local = datetime(year + 1, month, day, hour, minute)
                except ValueError:
                    return None
                if offs is not None:
                    candidate_utc = (candidate_local - offs).replace(tzinfo=timezone.utc)
                else:
                    candidate_utc = candidate_local.replace(tzinfo=timezone.utc)
                if candidate_utc <= now_utc:
                    return None
            return int(candidate_utc.timestamp())

    return None


def find_reminder_index(reminders: list[dict], identifier: str) -> int | None:
    identifier_text = str(identifier).strip()
    if identifier_text.isdigit():
        index = int(identifier_text) - 1
        if 0 <= index < len(reminders):
            return index
    for index, reminder in enumerate(reminders):
        if str(reminder.get("name", "")).strip().lower() == identifier_text.lower():
            return index
    return None


def find_checklist_item_index(item_list: list[dict], identifier: str) -> int | None:
    identifier_text = str(identifier).strip()
    if identifier_text.isdigit():
        index = int(identifier_text) - 1
        if 0 <= index < len(item_list):
            return index
    for index, item in enumerate(item_list):
        if str(item.get("content", "")).strip().lower() == identifier_text.lower():
            return index
    return None


def format_checklist_item(item: dict, index: int) -> str:
    status = item.get("status", "none")
    emoji = {
        "red": "<:disapprove:1517452151012589662>",
        "green": "<:approve:1517452125687513158>",
        "yellow": "<:warning:1517452174991556758>",
    }.get(status, "")
    content = item.get("content", "")
    return f"{index + 1}. {emoji} {content}".strip()


def get_total_checklist_items(lists: list[list[dict]]) -> int:
    return sum(len(item_list) for item_list in lists)


def get_reminder_display(reminder: dict) -> str:
    when = reminder.get("when")
    if isinstance(when, int):
        return f"<t:{when}:R>"
    return str(when)


def format_repeat_interval(seconds: int | None) -> str:
    if not isinstance(seconds, int) or seconds <= 0:
        return "Never"

    total = int(seconds)
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs or not parts:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")

    if not parts:
        return "Never"
    return "Every " + " ".join(parts)


def get_reminder_repeat_text(reminder: dict) -> str:
    repeat = reminder.get("repeat")
    if isinstance(repeat, int) and repeat > 0:
        return format_repeat_interval(repeat)
    return "Never"


def get_reminder_destination(reminder: dict, guild: discord.Guild | None = None) -> str:
    return ""


def get_reminder_message_text(reminder: dict) -> str:
    description = reminder.get("description", "").strip()
    if description:
        return description
    return "No description provided."


PENDING_POSTPONE_REMINDERS: dict[str, dict] = {}


class ReminderPostponeModal(Modal):
    def __init__(self, user_id: str, postpone_id: str, current_time: int):
        super().__init__(title="Postpone Reminder")
        self.user_id = user_id
        self.postpone_id = postpone_id
        self.time_input = TextInput(
            label="New reminder time",
            placeholder="Examples: 1h, 30m, 10:00, 20/02, 20/02 23:00, 20/02/2010 23:00",
            required=True,
                                                              
            default=(lambda ts, uid: (
                (datetime.utcfromtimestamp(ts) + (parse_utc_offset(get_user_settings_entry(load_user_settings(), str(uid)).get('timezone_offset')) if get_user_settings_entry(load_user_settings(), str(uid)).get('timezone_offset') else timedelta(0))).strftime('%d/%m/%Y %H:%M')
            ))(current_time, self.user_id),
        )
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction):
        data = PENDING_POSTPONE_REMINDERS.get(self.postpone_id)
        if not data or str(interaction.user.id) != data["user_id"]:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This postpone link is no longer valid.", ephemeral=True)
            return

        reminder = data["reminder"]
        new_time = parse_reminder_time(self.time_input.value, self.user_id)
        if new_time is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid reminder time. Examples: '1h', '30m', '10:00', '20/02', '20/02 23:00', '20/02/2010 23:00'.", ephemeral=True)
            return

        new_reminder = {
            "name": reminder.get("name", "Reminder"),
            "description": reminder.get("description", ""),
            "when": new_time,
            "send": reminder.get("send", "dm"),
        }
                                                                      
        if reminder.get("repeat"):
            new_reminder["repeat"] = reminder.get("repeat")
        if reminder.get("channel_id"):
            new_reminder["channel_id"] = reminder["channel_id"]

        reminders = get_user_reminders(str(self.user_id))
        if len(reminders) >= MAX_USER_REMINDERS:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                "<:disapprove:1517452151012589662> You can have up to 7 reminders at once.",
                ephemeral=True,
            )
            return

        reminders.append(new_reminder)
        save_user_reminders(str(self.user_id), reminders)
        PENDING_POSTPONE_REMINDERS.pop(self.postpone_id, None)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Reminder postponed to <t:{new_time}:F>.", ephemeral=True)


class ReminderNotificationView(LayoutView):
    def __init__(self, user_id: str, postpone_id: str, reminder: dict, mention_user: bool):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.postpone_id = postpone_id
        self.reminder = reminder
        self.mention_user = mention_user
        self.build_components()

    def build_components(self):
        reminder_label = f"<:timer:1517996239583576194> {self.reminder.get('name', 'Reminder')}"
        self.postpone_button = Button(label="Postpone", style=discord.ButtonStyle.secondary, custom_id=f"reminder_postpone:{self.postpone_id}")
        self.postpone_button.callback = self.open_postpone

        details = [
            Section(reminder_label, accessory=self.postpone_button),
            Separator(),
            TextDisplay(get_reminder_message_text(self.reminder)),
            TextDisplay(f"{get_reminder_display(self.reminder)}"),
            TextDisplay(f"Repeats: {get_reminder_repeat_text(self.reminder)}"),
        ]
        if self.mention_user:
            details.append(TextDisplay(f"<@{self.user_id}>"))

        container = Container(*details, accent_color=get_user_color_value(str(self.user_id)))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != int(self.user_id):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Only the reminder owner can postpone this reminder.", ephemeral=True)
            return False
        return True

    async def open_postpone(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ReminderPostponeModal(self.user_id, self.postpone_id, self.reminder.get("when", int(datetime.now(timezone.utc).timestamp()))))


async def deliver_reminder(user_id: str, reminder: dict):
    user = bot.get_user(int(user_id)) if user_id.isdigit() else None
    if not user:
        try:
            user = await bot.fetch_user(int(user_id))
        except Exception:
            user = None

    postpone_id = uuid.uuid4().hex
    PENDING_POSTPONE_REMINDERS[postpone_id] = {
        "user_id": str(user_id),
        "reminder": reminder,
    }

    if user:
        try:
            await user.send(view=ReminderNotificationView(str(user_id), postpone_id, reminder, mention_user=False))
        except Exception:
            pass


                                                                                      


def is_valid_send_mode(value: str) -> bool:
    return str(value).strip().lower() == "dm"


def normalize_send_mode(value: str) -> str:
    return "dm" if is_valid_send_mode(value) else "dm"


def get_list_title(list_index: int) -> str:
    return f"List {list_index + 1}" if 0 <= list_index < 3 else "List"


def get_list_header(user_id: int, list_index: int) -> str:
    return f"<:list:1517497572770451567> Lists for {bot.get_user(user_id).display_name if bot.get_user(user_id) else str(user_id)}"


def get_notes_header(user_id: int) -> str:
    user = bot.get_user(user_id)
    return f"<:edit:1517497568421085256> Notes for {user.display_name if user else str(user_id)}"


def get_reminders_header(user_id: int) -> str:
    user = bot.get_user(user_id)
    return f"<:timer:1517996239583576194> Reminders for {user.display_name if user else str(user_id)}"


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
    return user.mention


def format_user_reference_with_setting(user: discord.abc.User | discord.Member, settings: dict | None = None) -> str:
    if settings is None:
        settings = load_user_settings()

    if get_user_settings_entry(settings, user.id).get("user_pings", True):
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


def sanitize_ascii_text(value: str | None, fallback: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    safe = text.encode("ascii", "ignore").decode("ascii").strip()
    return safe if safe else fallback


def format_banner_limit_text(value: str | None, limit: int = 18, fallback: str = "DM") -> str:
    text = sanitize_ascii_text(value, fallback)
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


AFK_PREFIX = "[AFK]"
AFK_MESSAGE_WINDOW_SECONDS = 60
AFK_MESSAGE_LIMIT = 3
afk_status: dict[str, dict[str, object]] = {}


def get_afk_status_key(guild_id: int | str, user_id: int | str) -> str:
    return f"{guild_id}:{user_id}"


def build_afk_nickname(display_name: str) -> str:
    base_nickname = display_name.strip()
    if not base_nickname:
        base_nickname = "AFK"

    if len(base_nickname) + len(AFK_PREFIX) + 1 <= 32:
        return f"{AFK_PREFIX} {base_nickname}"

    max_base_length = max(0, 32 - len(AFK_PREFIX) - 1)
    return f"{AFK_PREFIX} {base_nickname[:max_base_length].rstrip()}"


async def set_afk_status(member: discord.Member, reason: str | None = None) -> bool:
    key = get_afk_status_key(member.guild.id, member.id)
    reason_text = (reason or "No reason provided.").strip() or "No reason provided."

    existing_state = afk_status.get(key)
    if existing_state:
        existing_state["reason"] = reason_text
        existing_state["message_times"] = [ts for ts in existing_state.get("message_times", []) if time.time() - ts <= AFK_MESSAGE_WINDOW_SECONDS]
        return False

    original_nickname = getattr(member, "display_name", None)
    afk_status[key] = {
        "reason": reason_text,
        "original_nickname": original_nickname,
        "message_times": [],
    }

                                                          
    try:
        settings = load_user_settings()
        uentry = get_user_settings_entry(settings, str(member.id))
        if "afk" not in uentry or not isinstance(uentry.get("afk"), dict):
            uentry["afk"] = {}
        uentry["afk"][str(member.guild.id)] = {
            "enabled": True,
            "reason": reason_text,
            "original_nickname": original_nickname,
            "since": datetime.now(timezone.utc).isoformat(),
        }
        save_user_settings(settings)
    except Exception:
        pass

    me = getattr(member.guild, "me", None)
    can_manage_nicknames = bool(me and me.guild_permissions.manage_nicknames)

    if not can_manage_nicknames:
        add_bot_error_entry(
            member.guild.id,
            None,
            member,
            "afk nickname update",
            PermissionError("Bot lacks manage_nicknames permission to update AFK nickname")
        )
        return True

    try:
        await member.edit(nick=build_afk_nickname(original_nickname or member.name), reason=f"AFK status enabled: {reason_text}")
    except (discord.Forbidden, discord.HTTPException) as error:
        add_bot_error_entry(member.guild.id, None, member, "afk nickname update", error)

    return True


async def clear_afk_status(member: discord.Member, channel: discord.abc.Messageable | None = None) -> None:
    key = get_afk_status_key(member.guild.id, member.id)
    state = afk_status.pop(key, None)
    if not state:
        return

    original_nickname = state.get("original_nickname")
    me = getattr(member.guild, "me", None)
    if me and me.guild_permissions.manage_nicknames:
        try:
            await member.edit(nick=original_nickname or None, reason="AFK status removed")
        except (discord.Forbidden, discord.HTTPException):
            pass

    if channel is not None:
        try:
            await channel.send(f"<:approve:1517452125687513158> **{member.display_name}** is no longer AFK.")
        except (discord.Forbidden, discord.HTTPException):
            pass

                                               
    try:
        settings = load_user_settings()
        uentry = get_user_settings_entry(settings, str(member.id))
        afk_dict = uentry.get("afk")
        if isinstance(afk_dict, dict) and str(member.guild.id) in afk_dict:
            afk_dict.pop(str(member.guild.id), None)
                                                   
            uentry["afk"] = afk_dict
            save_user_settings(settings)
    except Exception:
        pass


def get_afk_reason(entry: dict | None) -> str:
    if not entry:
        return "No reason provided."
    reason = entry.get("reason")
    return str(reason or "No reason provided.")


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


def load_lock_config():
    guild_data = load_guild_data()
    admin = {}

    for guild_id, guild_config in guild_data.items():
        for ch_id_str, value in guild_config.get("admin_log_channels", {}).items():
            try:
                admin[int(ch_id_str)] = value
            except (ValueError, TypeError):
                pass

    return {}, admin


def save_lock_config(locked, admin):
    guild_data = load_guild_data()

    for guild_id, guild_config in guild_data.items():
        guild_config["admin_log_channels"] = {}

    for channel_id, value in admin.items():
        for guild_id in guild_data:
            guild_data[guild_id]["admin_log_channels"][str(channel_id)] = value

    save_guild_data(guild_data)


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

    if guild_id not in data:
        data[guild_id] = default_config
    else:
        for key, value in default_config.items():
            if key not in data[guild_id]:
                data[guild_id][key] = value
    save_guild_data(data)
    return data[guild_id], data


def is_economy_enabled(guild_id: str) -> bool:
    return get_guild_config(guild_id)[0].get("economy_enabled", True)


def is_levels_enabled(guild_id: str) -> bool:
    return get_guild_config(guild_id)[0].get("levels_enabled", True)


async def ensure_economy_enabled(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return True
    if not is_economy_enabled(str(interaction.guild.id)):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Economy features are disabled in this server.", ephemeral=True)
        return False
    return True


async def ensure_levels_enabled(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return True
    if not is_levels_enabled(str(interaction.guild.id)):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Levels are disabled in this server.", ephemeral=True)
        return False
    return True


def get_guild_warnings(guild_id: str, member_id: int):
    data = load_guild_data()
    guild = data.setdefault(guild_id, {})
    warnings = guild.setdefault("warnings", {})
    user_warnings = warnings.setdefault(str(member_id), [])
    return user_warnings, data


def get_guild_automod_config(guild_id: str) -> tuple[dict, dict]:
    data = load_guild_data()
    guild = data.setdefault(guild_id, {})
    automod = guild.setdefault("automod", {})
    automod.setdefault("blocked_words", [])
    automod.setdefault("warning_sanctions", [])
    automod.setdefault("warning_sanction_state", {})
    automod.setdefault("blocked_rule_id", None)

    legacy_auto_sanctions = guild.pop("auto_sanctions", None)
    if isinstance(legacy_auto_sanctions, dict):
        migrated = []
        for warns_str, sanction in legacy_auto_sanctions.items():
            try:
                warns = int(warns_str)
            except (TypeError, ValueError):
                continue
            if not isinstance(sanction, dict):
                continue
            migrated.append({
                "warns": warns,
                "action": str(sanction.get("action", "timeout")),
                "duration_seconds": int(sanction.get("duration_seconds", sanction.get("duration_seconds", 0) or 0)),
                "duration": str(sanction.get("duration", "")) or str(sanction.get("duration_seconds", "")),
            })
        if migrated:
            automod.setdefault("warning_sanctions", []).extend(migrated)
            save_guild_data(data)

    return automod, data


def parse_bool_value(value: str) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def get_automod_match_mode(entry: dict | None) -> str:
    if not isinstance(entry, dict):
        return "word"

    mode = str(entry.get("match_mode", "")).strip().lower()
    if mode in {"generated_regex", "generated", "regex", "true"}:
        return "generated_regex"
    if mode in {"custom_regex", "custom", "is", "raw_regex"}:
        return "custom_regex"
    if mode in {"word", "simple", "keyword", "false"}:
        return "word"

    if entry.get("use_regex", False):
        return "generated_regex"
    return "word"


def automod_text_matches(content: str, phrase: str, match_mode: str = "word") -> bool:
    if not content or not phrase:
        return False

    mode = str(match_mode or "word").strip().lower()
    if mode == "custom_regex":
        try:
            return re.search(phrase, content, re.IGNORECASE) is not None
        except re.error:
            return False

    if mode == "generated_regex":
        try:
            generated_pattern = generate_automod_regex_pattern(phrase)
            if not generated_pattern:
                return False
            return re.search(generated_pattern, content, re.IGNORECASE) is not None
        except re.error:
            return False

    return phrase.lower() in content.lower()


NUM_REPLACERS = {
    "i": ["1"],
    "l": ["1"],
    "e": ["3"],
    "a": ["4"],
    "s": ["5"],
    "t": ["7"],
    "b": ["8"],
    "g": ["9"],
    "o": ["0"],
}

SYM_REPLACERS = {
    "a": ["@", "∆", "/-\\", "/_\\", "/\\", "Д"],
    "b": ["|}", "|:", "|8", "ß", "ь"],
    "c": ["(", "€"],
    "e": ["£"],
    "f": ["ƒ", "£"],
    "h": ["|-|", "#", "}{"],
    "i": ["!", "|"],
    "j": ["ʝ"],
    "k": ["|<"],
    "l": ["!", "|"],
    "n": ["|\\|"],
    "s": ["$", "§"],
    "x": ["><"],
    "y": ["¥"],
}

LET_REPLACERS = {
    "i": ["l"],
    "l": ["i"],
    "u": ["v"],
    "m": ["nn", "rn"],
    "w": ["vv", "uu"],
}

EMO_REPLACERS = {
    "a": ["🇦", "🅰️"],
    "b": ["🇧", "🅱️"],
    "c": ["🇨", "©️"],
    "d": ["🇩"],
    "e": ["🇪"],
    "f": ["🇫"],
    "g": ["🇬"],
    "h": ["🇭"],
    "i": ["🇮", "ℹ️"],
    "j": ["🇯"],
    "k": ["🇰"],
    "l": ["🇱"],
    "m": ["🇲", "Ⓜ️"],
    "n": ["🇳"],
    "o": ["🇴", "🅾️", "⭕"],
    "p": ["🇵", "🅿️"],
    "q": ["🇶"],
    "r": ["🇷", "®️"],
    "s": ["🇸"],
    "t": ["🇹", "✝️"],
    "u": ["🇺"],
    "v": ["🇻"],
    "w": ["🇼"],
    "x": ["🇽", "❌", "❎", "✖️"],
    "y": ["🇾"],
    "z": ["🇿"],
    "1": ["1️⃣"],
    "2": ["2️⃣"],
    "3": ["3️⃣"],
    "4": ["4️⃣"],
    "5": ["5️⃣"],
    "6": ["6️⃣"],
    "7": ["7️⃣"],
    "8": ["8️⃣"],
    "9": ["9️⃣"],
    "0": ["0️⃣"],
}


def _collect_replacers(character: str) -> list[str]:
    replacers: list[str] = []
    for mapping in (NUM_REPLACERS, SYM_REPLACERS, LET_REPLACERS, EMO_REPLACERS):
        replacers.extend(mapping.get(character, []))

    seen: set[str] = set()
    ordered: list[str] = []
    for replacer in replacers:
        if replacer in seen:
            continue
        seen.add(replacer)
        ordered.append(replacer)
    return ordered


def generate_automod_regex_pattern(text: str) -> str:
    if not text:
        return ""

    parts: list[str] = []
    current_char: str | None = None
    repeat_count = 0
    current_pattern: str | None = None

    for character in text:
        if current_char == character and current_pattern is not None:
            repeat_count += 1
            continue

        if current_pattern is not None and repeat_count > 0:
            parts.append(f"(?:{current_pattern}){{{repeat_count + 1},}}")
            repeat_count = 0
            current_pattern = None

        variants = _collect_replacers(character)
        if not variants:
            pattern = re.escape(character)
        else:
            escaped_variants = [re.escape(value) for value in variants]
            pattern = f"(?:{re.escape(character)}|{'|'.join(escaped_variants)})"
        parts.append(pattern)

        current_char = character
        current_pattern = pattern

    if current_pattern is not None and repeat_count > 0:
        parts.append(f"(?:{current_pattern}){{{repeat_count + 1},}}")

    return "".join(parts)


async def sync_guild_word_block_rule(guild_id: str) -> None:
    guild = bot.get_guild(int(guild_id)) if guild_id.isdigit() else None
    if guild is None:
        return

    automod, data = get_guild_automod_config(guild_id)
    blocked_words = automod.get("blocked_words", [])
    keyword_filter = []
    regex_patterns = []
    for entry in blocked_words:
        phrase = str(entry.get("phrase", "")).strip()
        if not phrase:
            continue
        match_mode = get_automod_match_mode(entry)
        if match_mode == "custom_regex":
            regex_patterns.append(phrase)
        elif match_mode == "generated_regex":
            generated_pattern = generate_automod_regex_pattern(phrase)
            if generated_pattern:
                regex_patterns.append(generated_pattern)
        else:
            keyword_filter.append(phrase)

    try:
        existing_rules = await guild.fetch_automod_rules()
        existing_word_rules = {rule.name: rule for rule in existing_rules if rule.name == "Word Block" or rule.name.startswith("Word Block ")}

        if not keyword_filter and not regex_patterns:
            for rule in existing_word_rules.values():
                await rule.delete(reason="No blocked words configured")
            automod["blocked_rule_id"] = None
            automod["blocked_rule_ids"] = []
            save_guild_data(data)
            return

        action = AutoModRuleAction(
            type=AutoModRuleActionType.block_message,
            custom_message="Blocked word or phrase detected.",
        )

        batches = []
        if keyword_filter or regex_patterns:
            if keyword_filter:
                batches.append(("Word Block", keyword_filter, regex_patterns[:10]))
            else:
                batches.append(("Word Block", [], regex_patterns[:10]))

            for index, batch in enumerate([regex_patterns[i:i + 10] for i in range(10, len(regex_patterns), 10)], start=2):
                batches.append((f"Word Block {index}", [], batch))
        else:
            batches.append(("Word Block", [], []))

        created_rule_ids = []
        for name, word_rules, regex_batch in batches:
            trigger = AutoModTrigger(
                type=AutoModRuleTriggerType.keyword,
                keyword_filter=word_rules or None,
                regex_patterns=regex_batch or None,
            )
            existing_rule = existing_word_rules.get(name)
            if existing_rule is not None:
                await existing_rule.edit(
                    name=name,
                    event_type=AutoModRuleEventType.message_send,
                    trigger=trigger,
                    actions=[action],
                    enabled=True,
                    reason="Updated blocked word settings",
                )
                created_rule_ids.append(existing_rule.id)
            else:
                new_rule = await guild.create_automod_rule(
                    name=name,
                    event_type=AutoModRuleEventType.message_send,
                    trigger=trigger,
                    actions=[action],
                    enabled=True,
                    reason="Configured blocked word settings",
                )
                created_rule_ids.append(new_rule.id)

        for rule_name, rule in existing_word_rules.items():
            if rule_name not in {name for name, _, _ in batches}:
                await rule.delete(reason="Removed stale blocked word rule")

        automod["blocked_rule_id"] = created_rule_ids[0] if created_rule_ids else None
        automod["blocked_rule_ids"] = created_rule_ids
        save_guild_data(data)
    except Exception:
        pass


async def add_guild_warning(guild_id: str, member_id: int, reason: str, moderator_id: int | None = None, moderator_name: str | None = None) -> tuple[list[dict], dict]:
    user_warnings, data = get_guild_warnings(guild_id, member_id)
    warn_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "moderator_id": moderator_id,
        "moderator_name": moderator_name,
    }
    user_warnings.append(warn_entry)
    save_guild_data(data)
    return user_warnings, data


async def send_warning_dm(member: discord.Member, guild: discord.Guild, reason: str, total_warnings: int | None = None, automod_triggered: bool = False, sanction: str | None = None) -> None:
    if member.bot:
        return

    title = "<:warning:1517452174991556758> You have received a warning"
    description = f"**Server:** {guild.name}\n**Reason:** {reason}"
    if automod_triggered:
        description += "\n**Triggered by:** Discord AutoMod"
    if total_warnings is not None:
        description += f"\n**Total warnings:** {total_warnings}"

    embed = discord.Embed(title=title, description=description, color=discord.Color.yellow())
    if sanction:
        embed.add_field(name="Sanction", value=sanction, inline=True)

    try:
        await member.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def send_automod_channel_reply(channel: discord.abc.GuildChannel | None, member: discord.Member | discord.User | None, member_id: int, reason: str, sanction: str | None = None, warning_given: bool = False, total_warnings: int | None = None) -> None:
    if channel is None:
        return

    mention = format_user_reference(member) if member is not None else f"<@{member_id}>"

    try:
        if warning_given:
            embed = discord.Embed(
                title="<:warning:1517452174991556758> You aren't allowed to say that.",
                description=f"**{mention}** is not allowed to say that.",
                color=discord.Color.yellow(),
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Total warnings", value=str(total_warnings if total_warnings is not None else 0), inline=False)
            if sanction:
                embed.add_field(name="Sanction", value=sanction, inline=True)
            await channel.send(embed=embed)
        else:
            await channel.send(f"<:warning:1517452174991556758> {mention}, you aren't allowed to say that.")
    except (discord.Forbidden, discord.HTTPException):
        pass


def member_bypasses_automod(member: discord.Member | discord.User | None) -> bool:
    if not isinstance(member, discord.Member):
        return False
    perms = member.guild_permissions
    return bool(perms.manage_guild or perms.administrator)


async def run_automod_check_for_content(guild: discord.Guild | None, member: discord.Member | discord.User | None, channel: discord.abc.GuildChannel | None, content: str, *, source_label: str = "message") -> bool:
    if not guild or not content:
        return False

    if member_bypasses_automod(member):
        return False

    automod, data = get_guild_automod_config(str(guild.id))
    blocked_words = automod.get("blocked_words", [])

    matched_entry = None
    should_warn = False
    for entry in blocked_words:
        phrase = str(entry.get("phrase", "")).strip()
        if not phrase:
            continue
        match_mode = get_automod_match_mode(entry)
        if automod_text_matches(content, phrase, match_mode):
            matched_entry = entry
            should_warn = bool(entry.get("warn_on_match", False))
            break

    if matched_entry is None:
        return False

    member_id = getattr(member, "id", None)
    sanction_text = None
    warnings = None
    if should_warn and member_id is not None:
        warnings, _ = await add_guild_warning(
            str(guild.id),
            member_id,
            f"{source_label} triggered an AutoMod block",
            moderator_id=None,
            moderator_name="Discord AutoMod",
        )

    if should_warn and isinstance(member, discord.Member) and not member.bot:
        sanction_text = await apply_warning_sanctions(member, guild, len(warnings) if warnings is not None else 0)
        await send_warning_dm(
            member,
            guild,
            f"{source_label} triggered an AutoMod block",
            total_warnings=len(warnings) if warnings is not None else None,
            automod_triggered=True,
            sanction=sanction_text,
        )

    await send_automod_channel_reply(
        channel,
        member,
        member_id if member_id is not None else 0,
        f"{source_label} triggered an AutoMod block",
        sanction=sanction_text,
        warning_given=should_warn,
        total_warnings=len(warnings) if warnings is not None else None,
    )
    return True


async def run_automod_check_for_interaction(interaction: discord.Interaction, content: str, *, source_label: str = "message") -> bool:
    if interaction.guild and await run_automod_check_for_content(interaction.guild, interaction.user, interaction.channel, content, source_label=source_label):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Blocked word or phrase detected.", ephemeral=True)
        return True
    return False


async def send_honeypot_dm(member: discord.Member, guild: discord.Guild, channel: discord.abc.GuildChannel, sanction: str, message_preview: str) -> None:
    if member.bot:
        return

    title = "<:honey:1524116282075512842> Sent a message in a honeypot channel"
    description = f"**Server:** {guild.name}\n**Channel:** {getattr(channel, 'mention', str(channel.id))}\n**Action:** {sanction}"

    embed = discord.Embed(title=title, description=description, color=discord.Color.gold())
    embed.add_field(name="Message preview", value=message_preview, inline=False)

    try:
        await member.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


def is_honeypot_channel(guild: discord.Guild | None, channel: discord.abc.GuildChannel | None) -> bool:
    if not guild or not channel:
        return False
    try:
        guild_config, _ = get_guild_config(str(guild.id))
        configured_channel_id = guild_config.get("honeypot_channel_id")
        if configured_channel_id is None:
            return False
        return int(configured_channel_id) == channel.id
    except (TypeError, ValueError):
        return False


async def apply_warning_sanctions(member: discord.Member, guild: discord.Guild, total_warnings: int) -> str | None:
    automod, data = get_guild_automod_config(str(guild.id))
    sanction_state = automod.setdefault("warning_sanction_state", {})
    member_key = str(member.id)
    last_applied = int(sanction_state.get(member_key, {}).get("last_applied_warns", 0))
    if total_warnings <= last_applied:
        return None

    applicable = [
        rule for rule in automod.get("warning_sanctions", [])
        if isinstance(rule, dict) and int(rule.get("warns", 0)) <= total_warnings
    ]
    if not applicable:
        return None

    rule = max(applicable, key=lambda rule: int(rule.get("warns", 0)))
    threshold = int(rule.get("warns", 0))
    action = str(rule.get("action", "timeout")).lower()
    sanction_text = None
    try:
        if action == "timeout":
            duration_seconds = max(1, int(rule.get("duration_seconds", 86400)))
            timed_out_until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            await member.edit(timed_out_until=timed_out_until, reason=f"Reached {threshold} warnings")
            sanction_text = f"Timeout for {format_duration(duration_seconds)}"
        elif action == "kick":
            await member.kick(reason=f"Reached {threshold} warnings")
            sanction_text = "Kick"
        elif action == "ban":
            await member.ban(reason=f"Reached {threshold} warnings")
            sanction_text = "Ban"
    except (discord.Forbidden, discord.HTTPException):
        pass

    sanction_state[member_key] = {"last_applied_warns": total_warnings}
    save_guild_data(data)
    return sanction_text


async def apply_honeypot_sanction(member: discord.Member | discord.User, guild: discord.Guild, channel: discord.abc.GuildChannel, message_content: str | None = None) -> bool:
    if member.bot or not guild or not isinstance(member, discord.Member):
        return False

    if not is_honeypot_channel(guild, channel):
        return False

    guild_config, _ = get_guild_config(str(guild.id))
    sanction = guild_config.get("honeypot_sanction") or {}
    action = str(sanction.get("action", "timeout")).lower()
    if action not in {"timeout", "kick", "ban"}:
        return False

    content_preview = (message_content or "").strip()
    if not content_preview:
        content_preview = "[no text content]"
    if len(content_preview) > 500:
        content_preview = content_preview[:497] + "..."

    if action == "timeout":
        duration_seconds = max(1, int(sanction.get("duration_seconds", 86400)))
        sanction_text = f"Timeout for {format_duration(duration_seconds)}"
    elif action == "kick":
        sanction_text = "Kick"
    else:
        sanction_text = "Ban"

    await send_honeypot_dm(member, guild, channel, sanction_text, content_preview)

    embed = discord.Embed(
        title="<:honey:1524116282075512842> Honeypot Triggered",
        color=discord.Color.gold()
    )
    embed.add_field(name="User", value=format_user_reference(member), inline=True)
    embed.add_field(name="Channel", value=channel.mention if hasattr(channel, 'mention') else str(channel), inline=True)
    embed.add_field(name="Action", value=action.title(), inline=True)
    embed.add_field(name="Message", value=content_preview or "*[Empty or Media]*", inline=False)
    embed.timestamp = datetime.now(timezone.utc)
    await send_audit_log(guild, "honeypot", embed=embed)

    try:
        if action == "timeout":
            timed_out_until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            await member.edit(timed_out_until=timed_out_until, reason="Sent a message in the honeypot channel")
        elif action == "kick":
            await member.kick(reason="Sent a message in the honeypot channel")
        elif action == "ban":
            await member.ban(reason="Sent a message in the honeypot channel")
    except (discord.Forbidden, discord.HTTPException):
        pass

    return True


                                    
webhook_cache = {}
audit_log_last_seen_ids: dict[int, int] = {}

async def get_or_create_webhook(channel: discord.TextChannel, guild_id: int) -> discord.Webhook | None:
    cache_key = f"{guild_id}:{channel.id}"
    if cache_key in webhook_cache:
        try:
            webhook = webhook_cache[cache_key]
            await webhook.fetch()
            return webhook
        except (discord.NotFound, discord.Forbidden):
            del webhook_cache[cache_key]

    try:
        if not bot.user:
            return None

        webhook_name = f"{bot.user.name} [logs]"
        avatar_bytes = None
        avatar_path = os.path.join(BASE_DIR, "log_pfp.png")
        if os.path.exists(avatar_path):
            try:
                with open(avatar_path, "rb") as f:
                    avatar_bytes = f.read()
            except Exception:
                pass

        webhooks = await channel.webhooks()
        for webhook in webhooks:
            if webhook.name == webhook_name:
                webhook_cache[cache_key] = webhook
                return webhook

        webhook = await channel.create_webhook(
            name=webhook_name,
            avatar=avatar_bytes,
            reason="Audit logging system"
        )
        print(f"Created new webhook: {webhook_name} in {channel.name}")
        webhook_cache[cache_key] = webhook
        return webhook
    except (discord.Forbidden, discord.HTTPException):
        return None


async def send_audit_log(guild: discord.Guild, event_type: str, embed: discord.Embed | None = None, content: str = "") -> None:
    if not guild:
        return

    try:
        guild_config, _ = get_guild_config(str(guild.id))
        admin_log_channels_dict = guild_config.get("admin_log_channels", {})

        admin_channel_ids = set()
        for ch_id_str in admin_log_channels_dict.keys():
            try:
                admin_channel_ids.add(int(ch_id_str))
            except (ValueError, TypeError):
                pass

        for ch_id in admin_log_channels.keys():
            admin_channel_ids.add(ch_id)

        if not admin_channel_ids:
            return

        for ch_id in admin_channel_ids:
            try:
                channel = guild.get_channel(ch_id)
                if not channel or not isinstance(channel, discord.TextChannel):
                    continue

                webhook = await get_or_create_webhook(channel, guild.id)
                if not webhook:
                    continue

                if embed:
                    await webhook.send(embed=embed, content=content if content else None)
                else:
                    await webhook.send(content=content if content else "(No audit data)")
            except Exception:
                pass
    except Exception:
        pass


def _format_audit_log_target(entry: discord.AuditLogEntry) -> str:
    target = entry.target
    if target is None:
        return "Unknown"
    if isinstance(target, discord.Member):
        return format_user_reference(target)
    if isinstance(target, discord.User):
        return format_user_reference(target)
    if isinstance(target, discord.TextChannel):
        return target.mention
    if isinstance(target, discord.Role):
        return target.name
    if hasattr(target, "name"):
        return str(target.name)
    return str(target)


def _format_audit_log_action(entry: discord.AuditLogEntry) -> str:
    action_name = getattr(entry.action, "name", None) or str(entry.action)
    return action_name.replace("_", " ").title()


def _format_audit_log_value(value):
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc)
        timestamp = int(dt.timestamp())
        return f"<t:{timestamp}:F>"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


async def sync_guild_audit_logs(guild: discord.Guild) -> None:
    if not guild:
        return

    try:
        audit_log = await guild.audit_logs(limit=5)
        entries = list(getattr(audit_log, "entries", []) or [])
        if not entries:
            return

        last_seen_id = audit_log_last_seen_ids.get(guild.id)
        if last_seen_id is None:
            audit_log_last_seen_ids[guild.id] = entries[0].id
            return

        for entry in entries:
            if entry.id <= last_seen_id:
                break
            await _dispatch_audit_log_entry(entry)

        if entries:
            audit_log_last_seen_ids[guild.id] = entries[0].id
    except Exception:
        pass


async def _dispatch_audit_log_entry(entry: discord.AuditLogEntry) -> None:
    if entry.guild is None:
        return

    embed = discord.Embed(
        title="<:drawer:1517497564189036574> Discord Audit Log",
        color=discord.Color.blurple()
    )
    embed.add_field(name="Action", value=_format_audit_log_action(entry), inline=True)
    embed.add_field(name="User", value=format_user_reference(entry.user) if entry.user else "Unknown", inline=True)
    embed.add_field(name="Target", value=_format_audit_log_target(entry), inline=True)
    if entry.reason:
        embed.add_field(name="Reason", value=entry.reason, inline=False)
    changes = getattr(entry, "changes", None)
    if changes is not None:
        changes_text = []
        before_diff = getattr(changes, "before", None)
        after_diff = getattr(changes, "after", None)
        if before_diff is not None and after_diff is not None:
            before_attrs = set(getattr(before_diff, "__dict__", {}).keys())
            after_attrs = set(getattr(after_diff, "__dict__", {}).keys())
            for attribute in sorted(before_attrs | after_attrs)[:3]:
                before_value = getattr(before_diff, attribute, None)
                after_value = getattr(after_diff, attribute, None)
                if before_value != after_value:
                    changes_text.append(f"{attribute}: {_format_audit_log_value(before_value)} → {_format_audit_log_value(after_value)}")
        if changes_text:
            embed.add_field(name="Changes", value="\n".join(changes_text), inline=False)
    embed.timestamp = datetime.now(timezone.utc)
    await send_audit_log(entry.guild, "discord_audit_log", embed=embed)


@bot.event
async def on_audit_log_entry_create(entry: discord.AuditLogEntry) -> None:
    await _dispatch_audit_log_entry(entry)


@bot.event
async def on_automod_action(action: discord.AutoModAction) -> None:
    guild = action.guild
    if guild is None:
        return

    automod, data = get_guild_automod_config(str(guild.id))
    blocked_rule_ids = set()
    for rule_id in automod.get("blocked_rule_ids", []) or []:
        try:
            blocked_rule_ids.add(int(rule_id))
        except (TypeError, ValueError):
            pass

    blocked_rule_id = automod.get("blocked_rule_id")
    try:
        if blocked_rule_id is not None:
            blocked_rule_ids.add(int(blocked_rule_id))
    except (TypeError, ValueError):
        pass

    if action.rule_id not in blocked_rule_ids:
        return

    text = action.matched_content or action.matched_keyword or action.content or ""
    if not text:
        return

    blocked_words = automod.get("blocked_words", [])
    should_warn = False
    for entry in blocked_words:
        if not entry.get("warn_on_match", False):
            continue
        phrase = str(entry.get("phrase", "")).strip()
        if not phrase:
            continue
        match_mode = get_automod_match_mode(entry)
        if automod_text_matches(text, phrase, match_mode):
            should_warn = True
            break

    member_id = action.user_id
    warnings, _ = None, None
    sanction_text = None
    if should_warn:
        warnings, _ = await add_guild_warning(str(guild.id), member_id, f"Discord AutoMod blocked a message via rule {action.rule_id}", moderator_id=None, moderator_name="Discord AutoMod")

    member = action.member or guild.get_member(member_id)
    if member is None:
        try:
            member = await guild.fetch_member(member_id)
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            member = None

    if member is not None and not member.bot and should_warn:
        sanction_text = await apply_warning_sanctions(member, guild, len(warnings))
        await send_warning_dm(
            member,
            guild,
            f"Discord AutoMod blocked a message",
            total_warnings=len(warnings),
            automod_triggered=True,
            sanction=sanction_text
        )

    await send_automod_channel_reply(
        action.channel,
        member,
        member_id,
        f"Discord AutoMod blocked a message",
        sanction=sanction_text,
        warning_given=should_warn,
        total_warnings=len(warnings) if warnings is not None else None,
    )


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


def parse_role_reference(guild: discord.Guild, reference: str) -> discord.Role | None:
    if not reference:
        return None
    ref = reference.strip()
    if ref.startswith("<@&") and ref.endswith(">"):
        ref = ref[3:-1]
    try:
        role_id = int(ref)
    except ValueError:
        return None
    return guild.get_role(role_id)


def format_role_reference(guild: discord.Guild, role_id) -> str:
    if not role_id:
        return "None"
    try:
        role_id_int = int(role_id)
    except (TypeError, ValueError):
        return str(role_id)
    role = guild.get_role(role_id_int)
    return role.mention if role else f"<@&{role_id_int}>"


def get_active_ticket_thread_entry(guild_id: str, user_id: int) -> dict | None:
    guild_config, _ = get_guild_config(guild_id)
    entry = guild_config.get("ticket_active_threads", {}).get(str(user_id))
    if isinstance(entry, dict):
        return entry
    if isinstance(entry, (int, str)):
        try:
            return {"thread_id": int(entry)}
        except (TypeError, ValueError):
            return None
    return None


def get_active_ticket_thread_id(guild_id: str, user_id: int) -> int | None:
    entry = get_active_ticket_thread_entry(guild_id, user_id)
    return entry.get("thread_id") if entry else None


def get_active_ticket_thread_control_message_id(guild_id: str, user_id: int) -> int | None:
    entry = get_active_ticket_thread_entry(guild_id, user_id)
    return entry.get("control_message_id") if entry else None


def set_active_ticket_thread_entry(guild_id: str, user_id: int, thread_id: int | None, control_message_id: int | None = None) -> None:
    guild_config, data = get_guild_config(guild_id)
    active_tickets = guild_config.setdefault("ticket_active_threads", {})
    key = str(user_id)
    if thread_id is None:
        active_tickets.pop(key, None)
    else:
        entry = active_tickets.get(key)
        if isinstance(entry, dict):
            entry["thread_id"] = thread_id
            if control_message_id is not None:
                entry["control_message_id"] = control_message_id
        else:
            active_tickets[key] = {"thread_id": thread_id, "control_message_id": control_message_id}
    save_guild_data(data)


def set_active_ticket_thread_id(guild_id: str, user_id: int, thread_id: int | None) -> None:
    set_active_ticket_thread_entry(guild_id, user_id, thread_id, None)


def get_ticket_owner_for_thread(guild_id: str, thread_id: int) -> int | None:
    guild_config, _ = get_guild_config(guild_id)
    for user_id_str, active_thread_entry in guild_config.get("ticket_active_threads", {}).items():
        try:
            if isinstance(active_thread_entry, dict):
                if active_thread_entry.get("thread_id") == thread_id:
                    return int(user_id_str)
            elif active_thread_entry == thread_id:
                return int(user_id_str)
        except (TypeError, ValueError):
            continue
    return None


class TicketConfigModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Set ticket settings")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.style_input = TextInput(label="Ticket style (button/list)", placeholder="button or list", required=True, max_length=10)
        self.reasons_input = TextInput(
            label="Ticket reasons",
            placeholder="(Reason1)(Reason2)(Reason3)... up to 10",
            required=False,
            style=discord.TextStyle.long,
            max_length=500,
        )
        self.add_item(self.style_input)
        self.add_item(self.reasons_input)

    async def on_submit(self, interaction: discord.Interaction):
        style = self.style_input.value.strip().lower()
        reasons_raw = self.reasons_input.value.strip()
        if style not in {"button", "list"}:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Ticket style must be button or list.", ephemeral=True)
            return
        reasons = []
        if reasons_raw:
            reasons = re.findall(r"\(([^)]+)\)", reasons_raw)
            reasons = [reason.strip() for reason in reasons if reason.strip()]
            if len(reasons) > 10:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You may only configure up to 10 ticket reasons.", ephemeral=True)
                return
        await self.callback(interaction, style, reasons, self.settings_message)


class RoleSelectorView(View):
    def __init__(self, user_id: int, guild: discord.Guild, placeholder: str, callback, settings_message: discord.Message):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild = guild
        self.callback = callback
        self.settings_message = settings_message
        self.role_select = RoleSelect(placeholder=placeholder, custom_id="role_selector", min_values=1, max_values=1)
        self.role_select.callback = self.on_role_selected
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="role_select_cancel")
        self.cancel_button.callback = self.on_cancel
        self.add_item(self.role_select)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_role_selected(self, interaction: discord.Interaction):
        if not self.role_select.values:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No role was selected.", ephemeral=True)
            return
        role = self.role_select.values[0]
        self.role_select.disabled = True
        self.cancel_button.disabled = True
        await self.callback(interaction, role, self.settings_message)
        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass

    async def on_cancel(self, interaction: discord.Interaction):
        self.role_select.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(content="Role selection cancelled.", view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


def build_ticket_announce_embed(guild_id: str) -> discord.Embed:
    guild_config, _ = get_guild_config(guild_id)
    embed = discord.Embed(
        title="<:ticket:1533568847725203609> Open a ticket",
        description="Click the button below to create a support ticket." if guild_config.get("ticket_style", "button") == "button" else "Select a reason to open a ticket.",
        color=discord.Color.blurple(),
    )
    if guild_config.get("ticket_style") == "list":
        reasons = guild_config.get("ticket_reasons", []) or []
        if reasons:
            embed.add_field(name="Ticket reasons:", value="\n".join(f"- {reason}" for reason in reasons[:10]), inline=False)
    return embed

def build_ticket_create_view(guild_id: str) -> discord.ui.View:
    guild_config, _ = get_guild_config(guild_id)
    if guild_config.get("ticket_style") == "list":
        return TicketReasonSelectMessageView(guild_id)
    return TicketCreateButtonView(guild_id)


async def refresh_ticket_announce_message(guild_id: str) -> None:
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return
    guild_config, data = get_guild_config(guild_id)
    channel_id = guild_config.get("ticket_channel_id")
    if not channel_id:
        guild_config["ticket_announce_message_id"] = None
        save_guild_data(data)
        return
    channel = guild.get_channel(int(channel_id)) if guild else None
    if not channel or not hasattr(channel, "send"):
        return
    embed = build_ticket_announce_embed(guild_id)
    view = build_ticket_create_view(guild_id)
    message_id = guild_config.get("ticket_announce_message_id")
    try:
        if message_id:
            message = await channel.fetch_message(int(message_id))
            await message.edit(embed=embed, view=view)
            try:
                bot.add_view(view, message_id=message.id)
            except Exception:
                pass
            return
    except (discord.NotFound, discord.HTTPException, ValueError):
        pass
    try:
        message = await channel.send(embed=embed, view=view)
        guild_config["ticket_announce_message_id"] = message.id
        save_guild_data(data)
        try:
            bot.add_view(view, message_id=message.id)
        except Exception:
            pass
    except (discord.Forbidden, discord.HTTPException):
        pass


class TicketCreateButtonView(View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.create_button = Button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="ticket_create_button")
        self.create_button.callback = self.on_create
        self.add_item(self.create_button)

    async def on_create(self, interaction: discord.Interaction):
        await create_ticket_for_user(interaction, self.guild_id)


class TicketReasonSelectMessageView(View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        guild_config, _ = get_guild_config(self.guild_id)
        reasons = guild_config.get("ticket_reasons", []) or []
        options = [discord.SelectOption(label=reason[:100], value=str(index)) for index, reason in enumerate(reasons[:10])]
        self.reason_select = discord.ui.Select(
            placeholder="Choose a ticket reason",
            options=options,
            custom_id="ticket_reason_select",
            min_values=1,
            max_values=1,
        )
        self.reason_select.callback = self.on_reason_selected
        self.add_item(self.reason_select)

    async def on_reason_selected(self, interaction: discord.Interaction):
        if not self.reason_select.values:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No reason was selected.", ephemeral=True)
            return
        reason_index = int(self.reason_select.values[0])
        guild_config, _ = get_guild_config(self.guild_id)
        reasons = guild_config.get("ticket_reasons", []) or []
        if reason_index < 0 or reason_index >= len(reasons):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid reason selected.", ephemeral=True)
            return
        await create_ticket_for_user(interaction, self.guild_id, reasons[reason_index])


class TicketReasonSelectView(View):
    def __init__(self, user_id: int, guild_id: str, options: list[discord.SelectOption]):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.reason_select = discord.ui.Select(placeholder="Choose a reason", options=options, custom_id="ticket_reason_select", min_values=1, max_values=1)
        self.reason_select.callback = self.on_reason_selected
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="ticket_reason_cancel")
        self.cancel_button.callback = self.on_cancel
        self.add_item(self.reason_select)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_reason_selected(self, interaction: discord.Interaction):
        reason_index = int(self.reason_select.values[0])
        guild_config, _ = get_guild_config(self.guild_id)
        reasons = guild_config.get("ticket_reasons", []) or []
        if reason_index < 0 or reason_index >= len(reasons):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid reason selected.", ephemeral=True)
            return
        await create_ticket_for_user(interaction, self.guild_id, reasons[reason_index])

    async def on_cancel(self, interaction: discord.Interaction):
        self.reason_select.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class TicketThreadControlView(View):
    def __init__(self, guild_id: str, owner_id: int, thread_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.thread_id = thread_id
        self.close_button = Button(label="Close", style=discord.ButtonStyle.secondary, custom_id="ticket_close")
        self.resolve_button = Button(label="Resolve", style=discord.ButtonStyle.success, custom_id="ticket_resolve")
        self.delete_button = Button(label="Delete", style=discord.ButtonStyle.danger, custom_id="ticket_delete")
        self.close_button.callback = self.on_close
        self.resolve_button.callback = self.on_resolve
        self.delete_button.callback = self.on_delete
        self.add_item(self.close_button)
        self.add_item(self.resolve_button)
        self.add_item(self.delete_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This button must be used inside a ticket thread.", ephemeral=True)
            return False
        if interaction.user.id != self.owner_id and not interaction.user.guild_permissions.manage_channels:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Only the ticket owner or staff can manage this ticket.", ephemeral=True)
            return False
        return True

    async def on_close(self, interaction: discord.Interaction):
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            return
        owner_id = self.owner_id
        owner = thread.guild.get_member(owner_id)
        if owner:
            try:
                await thread.remove_user(owner)
            except discord.Forbidden:
                pass
        set_active_ticket_thread_id(self.guild_id, owner_id, None)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Ticket closed. The owner can no longer access the thread.", ephemeral=True)
        await thread.edit(archived=True)

    async def on_resolve(self, interaction: discord.Interaction):
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            return
        owner_id = self.owner_id
        owner = thread.guild.get_member(owner_id)
        if owner:
            try:
                await thread.remove_user(owner)
            except discord.Forbidden:
                pass
        set_active_ticket_thread_id(self.guild_id, owner_id, None)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Ticket resolved and closed.", ephemeral=True)
        await thread.edit(archived=True)
        try:
            await thread.send("✅ This ticket has been resolved.")
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def on_delete(self, interaction: discord.Interaction):
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            return
        set_active_ticket_thread_id(self.guild_id, self.owner_id, None)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:trash:1517497581058527404> Ticket deleted.", ephemeral=True)
        await thread.delete()


async def create_ticket_for_user(interaction: discord.Interaction, guild_id: str, reason: str | None = None):
    if not interaction.guild or not interaction.channel:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used within the configured server.", ephemeral=True)
    existing_thread_id = get_active_ticket_thread_id(guild_id, interaction.user.id)
    guild = interaction.guild
    if existing_thread_id:
        existing_thread = guild.get_thread(int(existing_thread_id))
        if existing_thread and not existing_thread.archived:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> You already have an active ticket: {existing_thread.mention}", ephemeral=True)
            return
        set_active_ticket_thread_id(guild_id, interaction.user.id, None)
    guild_config, _ = get_guild_config(guild_id)
    channel_id = guild_config.get("ticket_channel_id")
    if not channel_id:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Ticket channel is not configured.", ephemeral=True)
    channel = guild.get_channel(int(channel_id))
    if not channel or not hasattr(channel, "send"):
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Ticket channel is not available.", ephemeral=True)

    await interaction.response.defer(ephemeral=True, thinking=True)
    thread_name = f"ticket-{interaction.user.name}"[:95]
    try:
        thread = await channel.create_thread(name=thread_name, type=discord.ChannelType.private_thread, invitable=False)
    except Exception:
        await interaction.followup.send("<:disapprove:1517452151012589662> Failed to create the ticket thread.", ephemeral=True)
        return
    try:
        await thread.add_user(interaction.user)
    except Exception:
        pass
    owner_id = interaction.user.id
    manager_mention = ""
    manager_role_id = guild_config.get("ticket_manager_role_id")
    manager_role = guild.get_role(int(manager_role_id)) if manager_role_id else None
    if manager_role:
        manager_mention = manager_role.mention
    ticket_title = f"<:ticket:1533568847725203609> Welcome to your ticket thread {interaction.user.name},\na staff member will be with you shortly! \n"
    if reason:
        ticket_reason = f"reason for ticket: {reason}"
    thread_control_view = TicketThreadControlView(guild_id, owner_id, thread.id)
    first_message = await thread.send(
        f"{interaction.user.mention} opened a ticket. {manager_mention}",
        embed=discord.Embed(title=ticket_title, description=ticket_reason if reason else None, color=discord.Color.green()),
        view=thread_control_view,
    )
    try:
        set_active_ticket_thread_entry(guild_id, owner_id, thread.id, first_message.id)
    except Exception:
        set_active_ticket_thread_id(guild_id, owner_id, thread.id)
    try:
        bot.add_view(thread_control_view, message_id=first_message.id)
    except Exception:
        pass
    await interaction.followup.send(f"<:approve:1517452125687513158> Your ticket has been opened: {thread.mention}", ephemeral=True)

    await refresh_ticket_announce_message(guild_id)


def set_active_ticket_thread_id(guild_id: str, user_id: int, thread_id: int | None) -> None:
    guild_config, data = get_guild_config(guild_id)
    active_tickets = guild_config.setdefault("ticket_active_threads", {})
    if thread_id is None:
        active_tickets.pop(str(user_id), None)
    else:
        active_tickets[str(user_id)] = thread_id
    save_guild_data(data)


def get_ticket_owner_for_thread(guild_id: str, thread_id: int) -> int | None:
    guild_config, _ = get_guild_config(guild_id)
    for user_id_str, active_thread_id in guild_config.get("ticket_active_threads", {}).items():
        try:
            if active_thread_id == thread_id:
                return int(user_id_str)
        except (TypeError, ValueError):
            continue
    return None


async def safe_edit_message(message: discord.Message, view: discord.ui.View):
    try:
        await message.edit(view=view)
    except (discord.NotFound, discord.HTTPException):
        pass


async def safe_send(interaction: discord.Interaction, content: str, **kwargs):
    try:
        await interaction.response.defer(); await interaction.followup.send(content, **kwargs)
    except discord.errors.InteractionResponded:
        try:
            await interaction.followup.send(content, **kwargs)
        except (discord.NotFound, discord.HTTPException):
            pass
    except (discord.NotFound, discord.HTTPException):
        pass


def get_guild_admin_log_channel_ids(guild: discord.Guild) -> list[int]:
    return _get_guild_channel_ids(guild, admin_log_channels)

def _get_guild_channel_ids(guild: discord.Guild, channel_dict: dict) -> list[int]:
    return [cid for cid in channel_dict if guild.get_channel(cid) is not None]

def get_admin_log_channel_mentions(guild: discord.Guild) -> list[str]:
    return _get_channel_mentions(guild, admin_log_channels)

def _get_channel_mentions(guild: discord.Guild, channel_dict: dict) -> list[str]:
    return [guild.get_channel(cid).mention for cid in channel_dict if guild.get_channel(cid) is not None]


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


def ensure_board_guild_config(guild_id: str):
    board_data = load_board_data()
    if guild_id not in board_data:
        board_data[guild_id] = {}
    return board_data


def parse_bool_value(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"yes", "y", "true", "1", "on"}


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

                                    
locked_channels = {}
_, admin_log_channels = load_lock_config()


def safe_eval_math_expr(expr: str) -> int | None:
    try:
        tree = ast.parse(expr.strip(), mode='eval')
    except SyntaxError:
        return None

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                raise ValueError("Boolean values are not allowed")
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Unsupported constant")
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                return left ** right
            raise ValueError("Unsupported operator")
        if isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.USub):
                return -operand
            raise ValueError("Unsupported unary operator")
        if isinstance(node, ast.Tuple):
            raise ValueError("Tuples are not allowed")
        raise ValueError("Unsupported expression")

    try:
        value = _eval(tree)
    except (ValueError, OverflowError, ZeroDivisionError):
        return None

    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    if not isinstance(value, int):
        return None
    return value


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
        return

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
        except Exception:
            pass
        return True
    return False


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


def is_server_owner(interaction: discord.Interaction):
    return interaction.user.id == interaction.guild.owner_id


def guild_owner_bypasses_role_checks(interaction: discord.Interaction) -> bool:
    return interaction.guild is not None and interaction.user.id == interaction.guild.owner_id


def _prune_history_entries(cache: list, *, key, max_items: int) -> list:
    if not cache:
        return []

    grouped: dict[object, list[dict]] = {}
    for entry in cache:
        grouped.setdefault(key(entry), []).append(entry)

    pruned: list[dict] = []
    for group_entries in grouped.values():
        pruned.extend(group_entries[-max_items:])

    pruned.sort(key=lambda entry: entry.get("time") or entry.get("created_at") or entry.get("edited_at") or entry.get("deleted_at") or datetime.now(timezone.utc))
    return pruned


def clean_cache():
    global message_cache, deleted_cache, edited_cache, bot_error_cache, where_ping_cache
    deleted_cache = _prune_history_entries(deleted_cache, key=lambda entry: entry.get("channel"), max_items=10)
    edited_cache = _prune_history_entries(edited_cache, key=lambda entry: entry.get("channel"), max_items=10)
    where_ping_cache = _prune_history_entries(where_ping_cache, key=lambda entry: (entry.get("guild_id"), entry.get("mention_id")), max_items=10)
    bot_error_cache = _prune_history_entries(bot_error_cache, key=lambda entry: entry.get("guild_id"), max_items=25)


def discord_timestamp(dt: datetime, style: str = "f") -> str:
    if isinstance(dt, datetime):
        return f"<t:{int(dt.timestamp())}:{style}>"
    return str(dt)


def trim_cache(cache: list, max_len: int = 10) -> list:
    return cache[-max_len:]


def _format_bot_error_user(user) -> str:
    if user is None:
        return "Unknown"
    try:
        return format_user_reference(user)
    except Exception:
        return getattr(user, "name", str(user))


async def _dispatch_bot_error_log(guild_id: int, channel_id: int | None, user, command_name: str, error: Exception, timestamp: datetime) -> None:
    guild = bot.get_guild(guild_id)
    if guild is None:
        return

    embed = discord.Embed(
        title="<:warning:1517497570000000000> Bot Error",
        color=discord.Color.orange()
    )
    embed.add_field(name="Command", value=str(command_name or "unknown"), inline=True)
    embed.add_field(name="User", value=_format_bot_error_user(user), inline=True)
    if channel_id:
        embed.add_field(name="Channel", value=f"<#{channel_id}>", inline=True)
    embed.add_field(name="Error Type", value=type(error).__name__, inline=True)
    embed.add_field(name="Message", value=str(error) or "No error message provided", inline=False)
    embed.timestamp = timestamp
    await send_audit_log(guild, "bot_error", embed=embed)


def add_bot_error(guild_id: int | None, channel_id: int | None, user, command_name: str, error: Exception, interaction: discord.Interaction = None):
    global bot_error_cache

    if interaction is not None:
        if interaction.guild is None:
            return
        guild_id = interaction.guild.id
        channel_id = interaction.channel_id
        user = interaction.user
        command_name = getattr(getattr(interaction, "command", None), "qualified_name", None)
        if not command_name:
            command_name = getattr(getattr(interaction, "command", None), "name", "unknown command")

    if guild_id is None:
        return

    timestamp = datetime.now(timezone.utc)
    bot_error_cache.append({
        "guild_id": guild_id,
        "channel_id": channel_id,
        "user": user,
        "command_name": command_name,
        "error_type": type(error).__name__,
        "error_message": str(error) or "No error message provided",
        "time": timestamp,
    })

    bot_error_cache = _prune_history_entries(bot_error_cache, key=lambda entry: entry.get("guild_id"), max_items=25)

    try:
        asyncio.create_task(_dispatch_bot_error_log(guild_id, channel_id, user, command_name, error, timestamp))
    except Exception:
        pass


def add_bot_error_entry(guild_id: int | None, channel_id: int | None, user, source: str, error: Exception):
    add_bot_error(guild_id, channel_id, user, source, error)


def normalize_item(name: str) -> str:
    return name.strip().title()


def find_item_key(dictionary: dict, item_name: str) -> str | None:
    target = item_name.strip().lower()
    for key in dictionary:
        if key.lower() == target:
            return key
    return None


def inventory_count(inventory: dict, item_name: str) -> int:
    key = find_item_key(inventory, item_name)
    return inventory[key] if key else 0


def inventory_add(inventory: dict, item_name: str, amount: int = 1) -> None:
    key = find_item_key(inventory, item_name)
    if key:
        inventory[key] += amount
    else:
        inventory[item_name] = amount


def inventory_remove(inventory: dict, item_name: str, amount: int = 1) -> int:
    key = find_item_key(inventory, item_name)
    if not key:
        return 0
    available = inventory[key]
    removed = min(available, amount)
    if removed >= available:
        del inventory[key]
    else:
        inventory[key] -= removed
    return removed


def build_board_embed(message):
    embed = discord.Embed(
        description=message.content if message.content else None,
        color=discord.Color.gold(),
    )
    embed.set_author(name=f"| {message.author.display_name}", icon_url=message.author.display_avatar.url)
    if message.attachments:
        attachment = message.attachments[0]
        if attachment.content_type and attachment.content_type.startswith("image/"):
            embed.set_image(url=attachment.url)
        else:
            attachment_name = attachment.filename or "attachment"
            embed.add_field(name="Attachment", value=f"[{attachment_name}]({attachment.url})", inline=False)
    embed.timestamp = message.created_at
    return embed


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

    embed = build_board_embed(message)

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




# -------------------------------------------------------------------------------------------------------------
#                                               UI Views
# -------------------------------------------------------------------------------------------------------------


def _bind_timeout_view_message(view, message):
    if view is None or message is None:
        return
    if not hasattr(view, "_attach_message"):
        return
    try:
        view._attach_message(message)
    except Exception:
        pass


_original_messageable_send = discord.abc.Messageable.send


async def _patched_messageable_send(self, *args, **kwargs):
    view = kwargs.get("view")
    message = await _original_messageable_send(self, *args, **kwargs)
    _bind_timeout_view_message(view, message)
    return message


discord.abc.Messageable.send = _patched_messageable_send


_original_message_edit = discord.message.Message.edit


async def _patched_message_edit(self, *args, **kwargs):
    view = kwargs.get("view")
    message = await _original_message_edit(self, *args, **kwargs)
    _bind_timeout_view_message(view, message)
    return message


discord.message.Message.edit = _patched_message_edit


_original_interaction_response_send_message = discord.InteractionResponse.send_message


async def _patched_interaction_response_send_message(self, *args, **kwargs):
    view = kwargs.get("view", discord.utils.MISSING)
    response = await _original_interaction_response_send_message(self, *args, **kwargs)
    if view is not discord.utils.MISSING and view is not None:
        try:
            message = await self._parent.original_response()
        except Exception:
            message = None
        _bind_timeout_view_message(view, message)
    return response


discord.InteractionResponse.send_message = _patched_interaction_response_send_message


_original_interaction_response_edit_message = discord.InteractionResponse.edit_message


async def _patched_interaction_response_edit_message(self, *args, **kwargs):
    view = kwargs.get("view", discord.utils.MISSING)
    response = await _original_interaction_response_edit_message(self, *args, **kwargs)
    if view is not discord.utils.MISSING and view is not None:
        try:
            message = await self._parent.original_response()
        except Exception:
            message = None
        _bind_timeout_view_message(view, message)
    return response


discord.InteractionResponse.edit_message = _patched_interaction_response_edit_message


class TimeoutDisabledViewMixin:
    def __init__(self, *args, timeout: float = 600, **kwargs):
        self._timeout_message = None
        if timeout is not None and timeout < 600:
            timeout = 600
        super().__init__(*args, timeout=timeout, **kwargs)

    def _attach_message(self, message):
        if message is None:
            return None
        self._timeout_message = message
        self.message = message
        return message

    def _get_timeout_message(self):
        for attr_name in ("message", "settings_message", "original_message", "target_message", "msg"):
            candidate = getattr(self, attr_name, None)
            if candidate is not None:
                return candidate
        return self._timeout_message

    async def on_timeout(self):
        return None


class TimeoutDisabledLayoutView(TimeoutDisabledViewMixin, LayoutView):
    pass


class TimeoutDisabledView(TimeoutDisabledViewMixin, View):
    pass


class ShopView(TimeoutDisabledLayoutView):
    def __init__(self, shop_items, guild_id, user_id):
        super().__init__(timeout=600)
        self.shop_items = dict(shop_items)
        self.guild_id = guild_id
        self.user_id = user_id
        self.current_page = 0
        self.items_per_page = 5
        self.build_components()

    def build_components(self):
        self.clear_items()

        items = list(self.shop_items.items())
        total_pages = max(1, (len(items) + self.items_per_page - 1) // self.items_per_page)
        start = self.current_page * self.items_per_page
        page_items = items[start:start + self.items_per_page]

        container_parts = [
            TextDisplay("## <:chalice:1517579767573123092> Server Shop"),
            TextDisplay("Choose an item from the menu below and buy it with the button."),
            Separator(),
            TextDisplay(f"Page {self.current_page + 1}/{total_pages}"),
        ]

        for item_name, info in page_items:
            buy_button = Button(
                label=f"Buy ${info['price']}",
                style=discord.ButtonStyle.primary,
                custom_id=f"shop_buy:{item_name}",
            )

            async def buy_callback(interaction: discord.Interaction, button: Button = None, item_name=item_name, info=info):
                data = load_data()
                user_data = get_user_data(data, self.guild_id, str(interaction.user.id))
                price = info['price']

                if user_data["balance"] < price:
                    await interaction.response.send_message("<:disapprove:1517452151012589662> You can't afford this!", ephemeral=True)
                    return

                user_data["balance"] -= price
                inventory_add(user_data["inventory"], item_name)
                save_data(data)

                self.build_components()
                await interaction.response.edit_message(view=self)
                await interaction.followup.send(f"<:approve:1517452125687513158> You bought **{item_name}**!", ephemeral=True)

            buy_button.callback = buy_callback
            container_parts.append(
                Section(
                    f"**{item_name}**\n{str(info.get('desc', 'No description provided')).strip() or 'No description provided'}",
                    accessory=buy_button,
                )
            )

        data = load_data()
        user_data = get_user_data(data, self.guild_id, str(self.user_id))
        balance = user_data.get("balance", 0)

        container_parts.extend([
            Separator(),
            TextDisplay(f"<:money:1517580310395486239> Your balance: **${balance}**"),
        ])

        container = Container(*container_parts, accent_color=discord.Color.gold())
        self.add_item(container)

        prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="shop_prev", disabled=self.current_page == 0)
        next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="shop_next", disabled=self.current_page >= total_pages - 1)

        async def prev_callback(interaction: discord.Interaction):
            if self.current_page > 0:
                self.current_page -= 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        async def next_callback(interaction: discord.Interaction):
            if self.current_page < total_pages - 1:
                self.current_page += 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        prev_button.callback = prev_callback
        next_button.callback = next_callback
        self.add_item(discord.ui.ActionRow(prev_button, next_button))


class DeletedMessagesView(TimeoutDisabledLayoutView):
    def __init__(self, full_description: str, media_messages: list, requester):
        super().__init__(timeout=600)
        self.full_description = full_description
        self.messages = media_messages
        self.requester = requester
        self.index = 0
        self.mode = "messages"
        self.build_components()

    def build_components(self):
        self.clear_items()

        if self.mode == "messages":
            container_items = [
                TextDisplay("<:trash:1517497581058527404> Recent deleted messages"),
                Separator(),
                TextDisplay(self.full_description),
            ]
            if self.messages:
                container_items.append(Separator())
                container_items.append(TextDisplay(f"<:image:1517497571470348539> {len(self.messages)} attachment(s) available. Press Media to browse them."))

            container = Container(*container_items, accent_color=discord.Color.red())
            self.add_item(container)

            if self.messages:
                self.media_button = Button(label="Media", style=discord.ButtonStyle.primary, custom_id="deleted_media_switch")

                async def media_callback(interaction: discord.Interaction):
                    if interaction.user != self.requester:
                        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Only the person who ran the command can switch views!", ephemeral=True)
                        return
                    self.mode = "media"
                    self.build_components()
                    await interaction.response.edit_message(view=self)

                self.media_button.callback = media_callback
                self.add_item(discord.ui.ActionRow(self.media_button))

        else:
            current_msg = self.messages[self.index]
            content_text = current_msg.get('content') or "*[Attachment only]*"
            attachment_url = current_msg.get('attachment_url')
            attachment_name = current_msg.get('attachment_name') or "attachment"
            is_image = bool(current_msg.get('is_image'))

            container_items = [
                TextDisplay("<:image:1517497571470348539> Deleted media viewer"),
                Separator(),
                TextDisplay(f"**{current_msg['author'].display_name}** - deleted at {discord_timestamp(current_msg['created_at'])}"),
                TextDisplay(f"{content_text}"),
            ]

            if attachment_url:
                if is_image:
                    gallery = MediaGallery()
                    gallery.add_item(media=attachment_url, description=f"{current_msg['author'].display_name} - deleted at {discord_timestamp(current_msg['created_at'])}")
                    container_items.extend([Separator(), gallery])
                else:
                    container_items.extend([Separator(), TextDisplay(f"Attachment: [{attachment_name}]({attachment_url})")])
            else:
                container_items.extend([Separator(), TextDisplay("No attachment available for this message.")])

            container_items.append(Separator())
            container_items.append(TextDisplay(f"Attachment {self.index + 1}/{len(self.messages)}"))

            container = Container(*container_items, accent_color=discord.Color.red())
            self.add_item(container)

            self.prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="deleted_media_prev")
            self.messages_button = Button(label="Messages", style=discord.ButtonStyle.primary, custom_id="deleted_messages_switch")
            self.next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="deleted_media_next")

            async def prev_callback(interaction: discord.Interaction):
                if interaction.user != self.requester:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Only the person who ran the command can change media pages!", ephemeral=True)
                    return
                if self.index > 0:
                    self.index -= 1
                    self.build_components()
                    await interaction.response.edit_message(view=self)

            async def messages_callback(interaction: discord.Interaction):
                if interaction.user != self.requester:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Only the person who ran the command can switch views!", ephemeral=True)
                    return
                self.mode = "messages"
                self.build_components()
                await interaction.response.edit_message(view=self)

            async def next_callback(interaction: discord.Interaction):
                if interaction.user != self.requester:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Only the person who ran the command can change media pages!", ephemeral=True)
                    return
                if self.index < len(self.messages) - 1:
                    self.index += 1
                    self.build_components()
                    await interaction.response.edit_message(view=self)

            self.prev_button.callback = prev_callback
            self.messages_button.callback = messages_callback
            self.next_button.callback = next_callback
            self.update_button_states()
            self.add_item(discord.ui.ActionRow(self.prev_button, self.messages_button, self.next_button))

    def update_button_states(self):
        self.prev_button.disabled = (self.index == 0)
        self.next_button.disabled = (self.index == len(self.messages) - 1)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if hasattr(self, 'message'):
                await self.message.edit(view=self)
        except Exception:
            pass


class WherePingView(TimeoutDisabledLayoutView):
    def __init__(self, entries: list[dict], target_user: discord.User | discord.Member):
        super().__init__(timeout=600)
        self.entries = list(entries)
        self.target_user = target_user
        self.build_components()

    def build_components(self):
        self.clear_items()

        lines = []
        for index, entry in enumerate(self.entries[:7], start=1):
            author_name = getattr(entry['author'], 'display_name', getattr(entry['author'], 'name', 'Unknown'))
            channel_text = f"<#{entry['channel_id']}>"
            content_text = entry.get('content') or "*[No text content]*"
            if len(content_text) > 220:
                content_text = content_text[:217] + "..."
            mention_name = entry.get('mention_name') or getattr(entry['mention'], 'display_name', getattr(entry['mention'], 'name', 'Unknown'))
            if entry.get('mention_type') == 'role':
                mention_text = f"@{mention_name}"
            else:
                mention_text = f"**{mention_name}**"
            lines.append(
                f"{index}. **{author_name}** pinged {mention_text} in {channel_text}\n"
                f"-# {content_text}\n"
                f"-# At {discord_timestamp(entry['created_at'])} | [Jump to Message]({entry['jump_url']})"
            )

        body = "\n\n".join(lines) if lines else "No recent ping entries found for this user."
        container = Container(
            TextDisplay(f"<:bell:1517497562184024275> Where {self.target_user.display_name} was pinged"),
            Separator(),
            TextDisplay(body),
            accent_color=discord.Color.gold(),
        )
        self.add_item(container)


class V2InfoContainerView(TimeoutDisabledLayoutView):
    def __init__(self, title: str, description: str, accent_color: discord.Color):
        super().__init__(timeout=600)
        container = Container(
            TextDisplay(title),
            Separator(),
            TextDisplay(description),
            accent_color=accent_color,
        )
        self.add_item(container)




# -------------------------------------------------------------------------------------------------------------
#                                               Events
# -------------------------------------------------------------------------------------------------------------




@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id and before.channel is not None and after.channel is None:
        await reset_song_queue_for_disconnect(member.guild.id)

    if not member.bot and member.guild:
        if before.channel != after.channel:
            embed = discord.Embed(
                title="<:play:1517497576855965716> Voice Channel Update",
                color=discord.Color.blue()
            )
            embed.add_field(name="User", value=format_user_reference(member), inline=True)

            if before.channel and after.channel:
                embed.add_field(name="From", value=before.channel.mention, inline=True)
                embed.add_field(name="To", value=after.channel.mention, inline=True)
                embed.description = "Member moved voice channels"
            elif before.channel:
                embed.add_field(name="Left", value=before.channel.mention, inline=True)
                embed.description = "Member left voice channel"
            elif after.channel:
                embed.add_field(name="Joined", value=after.channel.mention, inline=True)
                embed.description = "Member joined voice channel"

            embed.timestamp = datetime.now(timezone.utc)
            await send_audit_log(member.guild, "voice_update", embed=embed)

    voice_client = member.guild.voice_client
    if not voice_client:
        return
    if before.channel and before.channel.id == voice_client.channel.id:
        human_members = [m for m in voice_client.channel.members if not m.bot]
        if len(human_members) == 0:
            print(f"Voice channel empty in {member.guild.name}. Starting 30s leave timer...")
            await asyncio.sleep(30)
            if voice_client.channel:
                current_humans = [m for m in voice_client.channel.members if not m.bot]
                if len(current_humans) == 0:
                    await reset_song_queue_for_disconnect(member.guild.id)
                    await voice_client.disconnect()
                    print(f"Left empty voice channel in {member.guild.name} after 30 seconds.")


async def restore_ticket_announce_views() -> None:
    guild_data = load_guild_data()
    for guild_id, guild_config in guild_data.items():
        message_id = guild_config.get("ticket_announce_message_id")
        if not message_id:
            continue
        try:
            guild = bot.get_guild(int(guild_id)) if guild_id.isdigit() else None
            if not guild:
                continue
            channel_id = guild_config.get("ticket_channel_id")
            if not channel_id:
                continue
            channel = guild.get_channel(int(channel_id)) if guild else None
            if not channel or not hasattr(channel, "send"):
                continue
            view = build_ticket_create_view(guild_id)
            bot.add_view(view, message_id=int(message_id))
        except Exception:
            continue

async def restore_ticket_thread_views() -> None:
    guild_data = load_guild_data()
    for guild_id, guild_config in guild_data.items():
        active_threads = guild_config.get("ticket_active_threads")
        if not isinstance(active_threads, dict):
            continue
        try:
            guild = bot.get_guild(int(guild_id)) if guild_id.isdigit() else None
            if not guild:
                continue
            for owner_id_str, active_thread_entry in active_threads.items():
                try:
                    if isinstance(active_thread_entry, dict):
                        thread_id = active_thread_entry.get("thread_id")
                        control_message_id = active_thread_entry.get("control_message_id")
                    else:
                        thread_id = active_thread_entry
                        control_message_id = None
                    if not thread_id:
                        continue
                    thread = guild.get_thread(int(thread_id))
                    if thread is None:
                        thread = await guild.fetch_channel(int(thread_id))
                    if not isinstance(thread, discord.Thread):
                        continue
                    if control_message_id:
                        view = TicketThreadControlView(guild_id, int(owner_id_str), thread.id)
                        try:
                            bot.add_view(view, message_id=int(control_message_id))
                        except Exception:
                            pass
                        continue
                    first_message = None
                    async for message in thread.history(oldest_first=True, limit=1):
                        first_message = message
                        break
                    if first_message:
                        view = TicketThreadControlView(guild_id, int(owner_id_str), thread.id)
                        bot.add_view(view, message_id=first_message.id)
                        try:
                            set_active_ticket_thread_entry(guild_id, int(owner_id_str), thread.id, first_message.id)
                        except Exception:
                            pass
                except Exception:
                    continue
        except Exception:
            continue

@bot.event
async def on_ready():
    shard_info = (
        f"{len(bot.shards)} shard(s), IDs {list(bot.shards.keys())}"
        if bot.shards
        else "single process (no sharding)"
    )
    print(f"Logged in as {bot.user} (ID: {bot.user.id}) - {shard_info}")
    print(f"Serving {len(bot.guilds)} guilds... | ...and {len(bot.users)} users!")
    if not update_presence.is_running():
        update_presence.start()
    if not voice_xp_tracker.is_running():
        voice_xp_tracker.start()
    await restore_ticket_announce_views()
    await restore_ticket_thread_views()
    if not giveaway_loop.is_running():
        giveaway_loop.start()
    if not giveaway_refresh_loop.is_running():
        giveaway_refresh_loop.start()
                                                 
    try:
        settings = load_user_settings()
        users = settings.get("users", {}) if isinstance(settings, dict) else {}
        for uid, uentry in users.items():
            afk_dict = uentry.get("afk") if isinstance(uentry, dict) else None
            if not isinstance(afk_dict, dict):
                continue
            for gid, afk_entry in afk_dict.items():
                try:
                    if not afk_entry or not afk_entry.get("enabled"):
                        continue
                    guild_obj = bot.get_guild(int(gid)) if gid and gid.isdigit() else None
                    if not guild_obj:
                        continue
                    member = guild_obj.get_member(int(uid)) if uid and uid.isdigit() else None
                                                                                  
                    key = get_afk_status_key(gid, uid)
                    afk_status[key] = {
                        "reason": afk_entry.get("reason", "No reason provided."),
                        "original_nickname": afk_entry.get("original_nickname"),
                        "message_times": [],
                    }
                                                             
                    if member:
                        me = getattr(member.guild, "me", None)
                        if me and me.guild_permissions.manage_nicknames:
                            try:
                                await member.edit(nick=build_afk_nickname(afk_entry.get("original_nickname") or member.name), reason="AFK status restored on bot startup")
                            except Exception:
                                pass
                except Exception:
                    continue
    except Exception:
        pass

    bot.loop.create_task(blacklist_startup_cleanup())


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.guild and message.mentions:
        for mention in message.mentions:
            if mention.id == message.author.id or mention.bot:
                continue

            afk_key = get_afk_status_key(message.guild.id, mention.id)
            afk_entry = afk_status.get(afk_key)
            if afk_entry:
                try:
                    await message.reply(f"<:warning:1517452174991556758> **{mention.display_name}** is AFK right now. Reason: {get_afk_reason(afk_entry)}")
                except (discord.Forbidden, discord.HTTPException):
                    pass
                break

    if message.guild:
        afk_key = get_afk_status_key(message.guild.id, message.author.id)
        afk_entry = afk_status.get(afk_key)
        if afk_entry:
            now = time.time()
            timestamps = [timestamp for timestamp in afk_entry.get("message_times", []) if now - timestamp <= AFK_MESSAGE_WINDOW_SECONDS]
            timestamps.append(now)
            afk_entry["message_times"] = timestamps
            if len(timestamps) >= AFK_MESSAGE_LIMIT:
                await clear_afk_status(message.author, channel=message.channel)

    if message.guild:
        if is_honeypot_channel(message.guild, message.channel):
            await apply_honeypot_sanction(message.author, message.guild, message.channel, message.content)
            try:
                try:
                    await message.delete(reason="Honeypot message removed")
                except TypeError:
                    await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

    global message_cache, where_ping_cache
    clean_cache()

    attachment_url = None
    attachment_name = None
    is_image = False
    if message.attachments:
        attachment = message.attachments[0]
        attachment_url = attachment.url
        attachment_name = attachment.filename or "attachment"
        is_image = bool(attachment.content_type and attachment.content_type.startswith("image/"))
    now = datetime.now(timezone.utc)
    message_cache.append({
        'id': message.id,
        'channel': message.channel.id,
        'author': message.author,
        'content': message.content or "",
        'media': attachment_url,
        'attachment_url': attachment_url,
        'attachment_name': attachment_name,
        'is_image': is_image,
        'mentions': message.mentions,
        'time': now,
        'created_at': now
    })

    if message.guild:
        if getattr(message, "mentions", None):
            for mention in message.mentions:
                if mention.id == message.author.id or getattr(mention, "bot", False):
                    continue
                where_ping_cache.append({
                    'id': message.id,
                    'guild_id': message.guild.id,
                    'channel_id': message.channel.id,
                    'channel': message.channel.id,
                    'author': message.author,
                    'mention': mention,
                    'mention_id': mention.id,
                    'mention_type': 'user',
                    'mention_name': getattr(mention, 'display_name', getattr(mention, 'name', 'Unknown')),
                    'content': message.content,
                    'jump_url': message.jump_url,
                    'time': now,
                    'created_at': now,
                })
                where_ping_cache = _prune_history_entries(where_ping_cache, key=lambda entry: (entry.get("guild_id"), entry.get("mention_id")), max_items=10)

        if getattr(message, "role_mentions", None):
            for role in message.role_mentions:
                where_ping_cache.append({
                    'id': message.id,
                    'guild_id': message.guild.id,
                    'channel_id': message.channel.id,
                    'channel': message.channel.id,
                    'author': message.author,
                    'mention': role,
                    'mention_id': role.id,
                    'mention_type': 'role',
                    'mention_name': getattr(role, 'name', 'Unknown role'),
                    'content': message.content,
                    'jump_url': message.jump_url,
                    'time': now,
                    'created_at': now,
                })
                where_ping_cache = _prune_history_entries(where_ping_cache, key=lambda entry: (entry.get("guild_id"), entry.get("mention_id")), max_items=10)

    if message.guild:
        guild_id = str(message.guild.id)
        fun_data = load_fun_data()
        if guild_id in fun_data:
            guild_replies = fun_data[guild_id]
            message_words = message.content.lower().split()
            for trigger in guild_replies:
                if trigger in message_words:
                    response = random.choice(guild_replies[trigger])
                    try:
                        await message.reply(response)
                    except discord.Forbidden as error:
                        add_bot_error_entry(message.guild.id, message.channel.id, message.author, f"auto-reply: {trigger}", error)
                    except Exception as error:
                        add_bot_error_entry(message.guild.id, message.channel.id, message.author, f"auto-reply: {trigger}", error)
                    break

        if await handle_counter_message(message):
            return

        await add_xp(message.author, message.guild, random.randint(5, 10), announce_channel=message.channel)
        try:
            await increment_quest_progress(message.guild, message.author, 'messages', 1)
        except Exception:
            pass

    await bot.process_commands(message)


@bot.event
async def on_message_delete(message):
    global message_cache, deleted_cache
    clean_cache()

    for msg in message_cache:
        if msg['id'] == message.id:
            deleted_msg = msg.copy()
            deleted_msg['deleted_at'] = datetime.now(timezone.utc)

            history_enabled = True
            ghost_enabled = False
            if message.guild:
                guild_config, _ = get_guild_config(str(message.guild.id))
                history_enabled = guild_config.get("edit_delete_history_enabled", True)
                ghost_enabled = guild_config.get("ghost_ping_enabled", False)

            if history_enabled:
                deleted_cache.append(deleted_msg)
                deleted_cache = _prune_history_entries(deleted_cache, key=lambda entry: entry.get("channel"), max_items=10)
            
            if message.guild and not message.author.bot:
                content_preview = (message.content or "")[:1500]
                embed = discord.Embed(
                    title="<:trash:1517497581058527404> Message Deleted",
                    color=discord.Color.red()
                )
                embed.add_field(name="User", value=format_user_reference(message.author), inline=True)
                embed.add_field(name="Channel", value=message.channel.mention if hasattr(message.channel, 'mention') else str(message.channel), inline=True)
                embed.add_field(name="Content", value=content_preview or "*[Empty or Media]*", inline=False)

                if message.attachments:
                    attachment_links = []
                    for attachment in message.attachments[:5]:
                        name = attachment.filename or "attachment"
                        attachment_links.append(f"[{name}]({attachment.url})")
                    if attachment_links:
                        embed.add_field(name="Attachment(s)", value="\n".join(attachment_links), inline=False)
                        first_attachment = message.attachments[0]
                        if first_attachment.content_type and first_attachment.content_type.startswith("image/"):
                            embed.set_image(url=first_attachment.url)

                embed.add_field(name="Message ID", value=message.id, inline=True)
                embed.timestamp = datetime.now(timezone.utc)
                await send_audit_log(message.guild, "message_delete", embed=embed)
            if message.guild and not ghost_enabled:
                break

            if msg['mentions'] and not msg['author'].bot:
                pinged_users = [
                    user for user in msg['mentions']
                    if user.id != msg['author'].id and not getattr(user, "bot", False)
                ]
                
                if pinged_users:
                    settings = load_user_settings()
                    mentions_str = " ".join([format_user_reference(user, settings) for user in pinged_users])
                    author_str = format_user_reference(msg['author'], settings)
                    
                    embed = discord.Embed(
                        title="<:ghost:1517497569939558470> Ghost Ping Detected!",
                        description=f"{mentions_str}, you were pinged by {author_str} but the message was deleted.",
                        color=discord.Color.red()
                    )
                    if msg['content']:
                        embed.add_field(name="<:list:1517497572770451567> Deleted Content:", value=msg['content'], inline=False)
                    
                    embed.timestamp = msg['created_at']
                    
                    channel = bot.get_channel(msg['channel'])
                    if channel:
                        try:
                            await channel.send(embed=embed)
                        except discord.Forbidden as error:
                            add_bot_error_entry(message.guild.id if message.guild else None, msg['channel'], msg['author'], "ghost ping notification", error)
            break


@bot.event
async def on_message_edit(before, after):
    if before.author.bot:
        return

    if before.content == after.content:
        return

    global message_cache, edited_cache
    clean_cache()

    history_enabled = True
    if before.guild:
        guild_config, _ = get_guild_config(str(before.guild.id))
        history_enabled = guild_config.get("edit_delete_history_enabled", True)

    for msg in message_cache:
        if msg['id'] == before.id:
            if history_enabled:
                edited_msg = msg.copy()
                
                edited_msg['author_id'] = before.author.id
                edited_msg['old_content'] = before.content if before.content else "*(Empty original content)*"
                edited_msg['new_content'] = after.content if after.content else "*(Empty edited content)*"
                edited_msg['jump_url'] = after.jump_url
                edited_msg['edited_at'] = datetime.now(timezone.utc)
                
                edited_cache.append(edited_msg)
                edited_cache = _prune_history_entries(edited_cache, key=lambda entry: entry.get("channel"), max_items=10)
            
            if before.guild and not before.author.bot:
                old_preview = (before.content or "")[:750]
                new_preview = (after.content or "")[:750]
                embed = discord.Embed(
                    title="<:edit:1517497568421085256> Message Edited",
                    color=discord.Color.orange()
                )
                embed.add_field(name="User", value=format_user_reference(before.author), inline=True)
                embed.add_field(name="Channel", value=before.channel.mention if hasattr(before.channel, 'mention') else str(before.channel), inline=True)
                embed.add_field(name="Before", value=old_preview or "*[Empty]*", inline=False)
                embed.add_field(name="After", value=new_preview or "*[Empty]*", inline=False)
                embed.add_field(name="Message ID", value=before.id, inline=True)
                embed.timestamp = datetime.now(timezone.utc)
                await send_audit_log(before.guild, "message_edit", embed=embed)
            
            msg['content'] = after.content
            break


@bot.event
async def on_member_join(member):
    embed = discord.Embed(
        title="<:next:1518977801057861643> Member Joined",
        color=discord.Color.green()
    )
    embed.add_field(name="User", value=format_user_reference(member), inline=True)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Account Age", value=discord_timestamp(member.created_at), inline=True)
    embed.timestamp = datetime.now(timezone.utc)
    await send_audit_log(member.guild, "member_join", embed=embed)
    
    guild_config, _ = get_guild_config(str(member.guild.id))
    channel_id = guild_config.get("welcome_channel_id")
    if channel_id:
        channel = member.guild.get_channel(channel_id)
        if channel:
            try:
                welcome_file = await create_welcome_card(member)
                settings = load_user_settings()
                await channel.send(f"Welcome {format_user_reference_with_setting(member, settings)}!", file=welcome_file)
            except discord.Forbidden as error:
                add_bot_error_entry(member.guild.id, channel.id, member, "welcome banner", error)
            except Exception as e:
                print(f"Error creating welcome card: {e}")

    if guild_config.get("join_dm_enabled", False):
        join_dm_message = guild_config.get("join_dm_message")
        if join_dm_message:
            try:
                placeholders = {
                    "user": member.mention,
                    "member": member.mention,
                    "guild": member.guild.name,
                    "server": member.guild.name,
                }
                formatted_message = re.sub(
                    r"\{(user|member|guild|server)\}",
                    lambda match: placeholders[match.group(1)],
                    join_dm_message,
                )
                server_label = member.guild.name[:73]
                source_button = discord.ui.Button(
                    label=f"From {server_label}",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                )
                source_view = discord.ui.View()
                source_view.add_item(source_button)
                await member.send(formatted_message, view=source_view)
            except discord.Forbidden as error:
                add_bot_error_entry(member.guild.id, None, member, "join DM", error)
            except Exception as e:
                print(f"Error sending join DM: {e}")

    join_role_ids = guild_config.get("join_role_ids", [])
    if join_role_ids:
        for role_id in list(join_role_ids):
            try:
                role_id_int = int(role_id)
            except (TypeError, ValueError):
                continue
            role = member.guild.get_role(role_id_int)
            if role is None or role in member.roles:
                continue
            try:
                await member.add_roles(role, reason="Join role")
            except discord.Forbidden as error:
                add_bot_error_entry(member.guild.id, role.id, member, "join role", error)
            except Exception as e:
                print(f"Error assigning join role {role.id}: {e}")


@bot.event
async def on_member_remove(member):
    embed = discord.Embed(
        title="<:prev:1518977803092234331> Member Left",
        color=discord.Color.red()
    )
    embed.add_field(name="User", value=format_user_reference(member), inline=True)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Joined", value=discord_timestamp(member.joined_at) if member.joined_at else "Unknown", inline=True)
    embed.timestamp = datetime.now(timezone.utc)
    await send_audit_log(member.guild, "member_remove", embed=embed)
    
    guild_config, _ = get_guild_config(str(member.guild.id))
    channel_id = guild_config.get("goodbye_channel_id")
    if channel_id:
        channel = member.guild.get_channel(channel_id)
        if channel:
            try:
                goodbye_file = await create_goodbye_card(member)
                settings = load_user_settings()
                goodbye_name = format_user_reference_with_setting(member, settings)
                await channel.send(f"Goodbye {goodbye_name}. We'll miss you!", file=goodbye_file)
            except discord.Forbidden as error:
                add_bot_error_entry(member.guild.id, channel.id, member, "goodbye banner", error)
            except Exception as e:
                print(f"Error creating goodbye card: {e}")


@bot.event
async def on_raw_reaction_add(payload):
    if not payload.guild_id:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    reactor = guild.get_member(payload.user_id)
    if reactor and not reactor.bot:
        cooldown_key = (payload.guild_id, payload.user_id)
        now = datetime.now()
        last_xp = reaction_xp_cooldowns.get(cooldown_key)
        if not last_xp or (now - last_xp).total_seconds() >= 15:
            reaction_xp_cooldowns[cooldown_key] = now
            await add_xp(reactor, guild, random.randint(1, 3), announce_channel=guild.get_channel(payload.channel_id))
        try:
            channel = guild.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            if message.author and not message.author.bot and message.author.id != payload.user_id:
                await add_xp(message.author, guild, random.randint(3, 5), announce_channel=channel)
        except discord.Forbidden as error:
            add_bot_error_entry(payload.guild_id, payload.channel_id, None, "reaction xp source fetch", error)
        except Exception:
            pass

    guild_id = str(payload.guild_id)
    board_data = load_board_data()

    if guild_id not in board_data:
        return

    emoji_str = str(payload.emoji)
    if emoji_str not in board_data[guild_id]:
        return

    config = board_data[guild_id][emoji_str]
    if "tracked_messages" not in config:
        config["tracked_messages"] = {}

    message_id_str = str(payload.message_id)

    channel = bot.get_channel(payload.channel_id)
    if not channel:
        return
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.Forbidden as error:
        add_bot_error_entry(payload.guild_id, channel.id, None, "reaction board source fetch", error)
        return
    except discord.NotFound:
        return

    reaction = discord.utils.get(message.reactions, emoji=payload.emoji.name if payload.emoji.is_unicode_emoji() else payload.emoji)
    current_count = reaction.count if reaction else 0

    board_channel = bot.get_channel(config["channel_id"])
    if not board_channel:
        return

    embed = build_board_embed(message)

    content_text = f"{emoji_str} {current_count} in {message.jump_url}"

    if message_id_str in config["tracked_messages"]:
        board_msg_id = int(config["tracked_messages"][message_id_str])
        try:
            board_message = await board_channel.fetch_message(board_msg_id)
            try:
                await board_message.edit(content=content_text, embed=embed)
            except discord.Forbidden as error:
                add_bot_error_entry(payload.guild_id, config["channel_id"], None, "reaction board edit", error)
        except discord.NotFound:
            del config["tracked_messages"][message_id_str]
            save_board_data(board_data)
    elif current_count >= config["required_count"]:
        try:
            new_board_msg = await board_channel.send(content=content_text, embed=embed)
        except discord.Forbidden as error:
            add_bot_error_entry(payload.guild_id, config["channel_id"], None, "reaction board post", error)
            return
        config["tracked_messages"][message_id_str] = str(new_board_msg.id)
        save_board_data(board_data)


@bot.event
async def on_raw_reaction_remove(payload):
    if not payload.guild_id:
        return

    guild_id = str(payload.guild_id)
    board_data = load_board_data()

    if guild_id not in board_data:
        return

    emoji_str = str(payload.emoji)
    if emoji_str not in board_data[guild_id]:
        return

    config = board_data[guild_id][emoji_str]
    if "tracked_messages" not in config:
        return

    message_id_str = str(payload.message_id)
    if message_id_str not in config["tracked_messages"]:
        return

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

    board_msg_id = int(config["tracked_messages"][message_id_str])
    try:
        board_message = await board_channel.fetch_message(board_msg_id)
        if current_count >= config["required_count"]:
            content_text = f"{emoji_str} {current_count} in {message.jump_url}"
            embed = build_board_embed(message)
            await board_message.edit(content=content_text, embed=embed)
        else:
            await board_message.delete()
            del config["tracked_messages"][message_id_str]
            save_board_data(board_data)
    except discord.Forbidden as error:
        add_bot_error_entry(payload.guild_id, config["channel_id"], None, "reaction board fetch", error)
    except discord.NotFound:
        del config["tracked_messages"][message_id_str]
        save_board_data(board_data)




# -------------------------------------------------------------------------------------------------------------
#                                               Error Handling
# -------------------------------------------------------------------------------------------------------------




@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original_error = getattr(error, "original", error)
    bot_missing_permissions_error = getattr(app_commands, "BotMissingPermissions", None)

    if isinstance(error, app_commands.CommandOnCooldown):
        retry_after = error.retry_after
        if retry_after >= 60:
            minutes = int(retry_after // 60)
            seconds = int(retry_after % 60)
            if seconds > 0:
                message_text = f"<:hourglass:1517574046252924938> This command is on cooldown. Please wait **{minutes}m {seconds}s** before trying again."
            else:
                message_text = f"<:hourglass:1517574046252924938> This command is on cooldown. Please wait **{minutes}m** before trying again."
        else:
            retry_after = round(retry_after, 1)
            message_text = f"<:hourglass:1517574046252924938> This command is on cooldown. Please wait **{retry_after}s** before trying again."
        if interaction.response.is_done():
            await interaction.followup.send(message_text, ephemeral=True)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(message_text, ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions):
        perms = ", ".join(error.missing_permissions)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> You lack the required permissions to run this: `{perms}`", ephemeral=True)
    elif bot_missing_permissions_error is not None and isinstance(error, bot_missing_permissions_error):
        perms = ", ".join(error.missing_permissions)
        message_text = f"<:disapprove:1517452151012589662> I am missing the required permissions to run this: `{perms}`"
        if interaction.response.is_done():
            await interaction.followup.send(message_text, ephemeral=True)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(message_text, ephemeral=True)
    elif isinstance(original_error, discord.Forbidden):
        message_text = "<:disapprove:1517452151012589662> I am missing the permissions required to complete that action."
        if interaction.response.is_done():
            await interaction.followup.send(message_text, ephemeral=True)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(message_text, ephemeral=True)
    else:
        command_name = getattr(getattr(interaction, "command", None), "qualified_name", None) or getattr(getattr(interaction, "command", None), "name", "unknown command")
        add_bot_error(
            getattr(interaction, "guild_id", None),
            getattr(interaction, "channel_id", None),
            getattr(interaction, "user", None),
            command_name,
            original_error,
            interaction=interaction,
        )
        print(f"Ignored exception in command tree [{command_name}]: {type(original_error).__name__}: {original_error}")
        print("".join(traceback.format_exception(type(original_error), original_error, original_error.__traceback__)))
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> An unexpected error occurred while executing this command.", ephemeral=True)


                                        
@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):                 
    if isinstance(error, commands.CommandNotFound):
        try:
            is_owner = await bot.is_owner(ctx.author)
        except Exception:
            is_owner = False

        if is_owner:
            await ctx.send("<:disapprove:1517452151012589662> you typed it wrong, or maybe you're just hallucinating and this command doesn't exist, try again with a command that exists.")
        else:
            await ctx.send("<:disapprove:1517452151012589662> this command doesn't exist, even if it did, you couldn't even be able to run it, but hey! you can still use the / commands :)")
        return




# -------------------------------------------------------------------------------------------------------------
#                                               Presence Update Loop
# -------------------------------------------------------------------------------------------------------------




presence_index = 0

@tasks.loop(seconds=15)
async def update_presence():
    global presence_toggle, presence_index

    load_dotenv(override=True)
    raw_blacklist = os.getenv('SERVER_BLACKLIST', '')
    BLACKLISTED_GUILDS = [int(sid.strip()) for sid in raw_blacklist.split(',') if sid.strip().isdigit()]

    for guild in bot.guilds:
        if guild.id in BLACKLISTED_GUILDS:
            print(f"Loop Check: Found blacklisted guild: {guild.name} ({guild.id}). Leaving...")
            try:
                await guild.leave()
            except Exception as e:
                print(f"Failed to leave {guild.name}: {e}")

    load_dotenv(override=True)
    VERSION = os.getenv('BOT_VERSION')
    VERSION_ALTERNATE = os.getenv('BOT_VERSION_ALTERNATE')
    ACTIVITY_TEXT = os.getenv('ACTIVITY')
    total_guilds = len(bot.guilds)

    if presence_index == 0:
        activity_text = f"watching over {total_guilds} servers..."
    elif presence_index == 1:
        activity_text = f"...and {len(bot.users)} users!"
    elif presence_index == 2:
        activity_text = f"{ACTIVITY_TEXT}"
    else:
        activity_text = f"ver{VERSION} ┃ {VERSION_ALTERNATE}"

    activity = discord.Activity(type=discord.ActivityType.watching, name=activity_text)

    for shard_id, shard in bot.shards.items():
        await bot.change_presence(
            activity=activity,
            status=discord.Status.online,
            shard_id=shard_id,
        )

    presence_index = (presence_index + 1) % 4

                                                                                     
    try:
        g_data = load_giveaway_data()
        if g_data:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            for gid, gav in list(g_data.items()):
                try:
                    if gav.get('status') == 'active' and int(gav.get('end_time', 0)) <= now_ts:
                                                                                         
                        asyncio.create_task(finalize_giveaway(gid, gav))
                except Exception:
                                                                     
                    pass
    except Exception:
        pass

                                                                  
    try:
        settings = load_user_settings()
        if settings:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            users = settings.get("users")
            if isinstance(users, dict):
                reminders_changed = False
                for user_id, user_settings in list(users.items()):
                    reminders = user_settings.get("reminders")
                    if not isinstance(reminders, list):
                        continue

                    remaining_reminders = []
                    for reminder in reminders:
                        if not isinstance(reminder, dict):
                            continue
                        when = reminder.get("when")
                        if isinstance(when, int) and when <= now_ts:
                                                   
                            try:
                                asyncio.create_task(deliver_reminder(user_id, reminder))
                            except Exception:
                                pass
                            reminders_changed = True

                                                     
                            repeat = reminder.get("repeat")
                            if isinstance(repeat, int) and repeat > 0:
                                next_when = when + repeat
                                while next_when <= now_ts:
                                    next_when += repeat
                                reminder["when"] = int(next_when)
                                remaining_reminders.append(reminder)
                                                                     
                        else:
                            remaining_reminders.append(reminder)

                    if len(remaining_reminders) != len(reminders):
                        user_settings["reminders"] = remaining_reminders

                if reminders_changed:
                    save_user_settings(settings)
    except Exception:
        pass


@update_presence.before_loop
async def before_update_presence():
    await bot.wait_until_ready()
    startup_activity = discord.Streaming(
        name="App just started... .. .",
        url="https://www.twitch.tv/imninnn"
    )
    for shard_id in bot.shards:
        await bot.change_presence(activity=startup_activity, shard_id=shard_id)
    await asyncio.sleep(30)




# -------------------------------------------------------------------------------------------------------------
#                                               Blacklist Handling
# -------------------------------------------------------------------------------------------------------------




@bot.event
async def on_guild_join(guild):
    load_dotenv(override=True)
    raw_blacklist = os.getenv('SERVER_BLACKLIST', '')
    BLACKLISTED_GUILDS = [int(sid.strip()) for sid in raw_blacklist.split(',') if sid.strip().isdigit()]
    if guild.id in BLACKLISTED_GUILDS:
        print(f"Joined blacklisted guild: {guild.name} ({guild.id}). Leaving immediately...")
        await guild.leave()


async def blacklist_startup_cleanup():
    await bot.wait_until_ready()
    print("Running startup blacklist check...")
    print('-------------------------------------')
    for guild in bot.guilds:
        if guild.id in BLACKLISTED_GUILDS:
            print(f"Found blacklisted guild on startup: {guild.name} ({guild.id}). Leaving...")
            try:
                await guild.leave()
            except Exception as e:
                print(f"Failed to leave {guild.name}: {e}")




# -------------------------------------------------------------------------------------------------------------
#                                               User Level Commands
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="definition", description="Look up the dictionary definition of a word")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(word="The word you want to define")
async def define_word(interaction: discord.Interaction, word: str):
    await interaction.response.defer()
    
    clean_word = word.strip().lower()
    if interaction.guild and await run_automod_check_for_interaction(interaction, clean_word, source_label="/def"):
        return

    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{clean_word}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                
                if response.status == 404:
                    return await interaction.followup.send(
                        f"<:disapprove:1517452151012589662> Could not find a definition for **{word}**. Double check your spelling!", 
                        ephemeral=True
                    )
                
                if response.status != 200:
                    return await interaction.followup.send(
                        "<:warning:1517452174991556758> The dictionary service is currently unavailable. Please try again later.", 
                        ephemeral=True
                    )
                
                data = await response.json()
                
        word_data = data[0]
        word_name = word_data.get("word", clean_word).title()
        phonetic = word_data.get("phonetic", "N/A")
        
        embed = discord.Embed(
            title=f"<:list:1517497572770451567> Dictionary Definition: {word_name}",
            description=f"**Phonetic:** `{phonetic}`",
            color=discord.Color.blurple()
        )
        
        meanings = word_data.get("meanings", [])
        
        for meaning in meanings[:3]:
            part_of_speech = meaning.get("partOfSpeech", "unknown").upper()
            definitions_list = meaning.get("definitions", [])
            
            def_text = ""
            for idx, d_obj in enumerate(definitions_list[:2], start=1):
                definition = d_obj.get("definition", "No definition given.")
                def_text += f"**{idx}.** {definition}\n"
                
                example = d_obj.get("example")
                if example:
                    def_text += f"   *\" {example} \"*\n"
            
            if def_text:
                embed.add_field(name=f"<:spark:1517583248421552305> {part_of_speech}", value=def_text, inline=False)
                
        embed.set_footer(text="Data sourced from Wiktionary API")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        print(f"Error executing /def command: {e}")
        await interaction.followup.send("<:disapprove:1517452151012589662> An internal error occurred while fetching the definition.", ephemeral=True)


@bot.tree.command(name="encode-decode", description="Encode or decode text using various methods (Base64, Base32, Base16, Binary)")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(
    text="The text you want to process",
    encoding_type="Choose the format method",
    action="Choose whether to encode (encrypt) or decode (decrypt)"
)
@app_commands.choices(
    encoding_type=[
        app_commands.Choice(name="Base64", value="base64"),
        app_commands.Choice(name="Base32", value="base32"),
        app_commands.Choice(name="Base16 (Hex)", value="base16"),
        app_commands.Choice(name="Binary", value="binary")
    ],
    action=[
        app_commands.Choice(name="Encode (Text ➔ Format)", value="encode"),
        app_commands.Choice(name="Decode (Format ➔ Text)", value="decode")
    ]
)
async def encode_decode_command(interaction: discord.Interaction, text: str, encoding_type: str, action: str):
    try:
        if action == "encode":
            text_bytes = text.encode("utf-8")
            if encoding_type == "base64":
                result = base64.b64encode(text_bytes).decode("utf-8")
            elif encoding_type == "base32":
                result = base64.b32encode(text_bytes).decode("utf-8")
            elif encoding_type == "base16":
                result = base64.b16encode(text_bytes).decode("utf-8")
            elif encoding_type == "binary":
                result = " ".join(f"{ord(char):08b}" for char in text)
            title_text = f"<:locked:1517574877257924809> {encoding_type} Encoding Complete"
            field_name = "Encoded Result:"
            color_choice = discord.Color.red()
        else:
            if encoding_type == "base64":
                result = base64.b64decode(text.encode("utf-8")).decode("utf-8")
            elif encoding_type == "base32":
                result = base64.b32decode(text.encode("utf-8")).decode("utf-8")
            elif encoding_type == "base16":
                result = base64.b16decode(text.encode("utf-8")).decode("utf-8")
            elif encoding_type == "binary":
                binary_values = text.split()
                result = "".join(chr(int(b, 2)) for b in binary_values)
            title_text = f"<:unlocked:1517574880034558102> {encoding_type} Decoding Complete"
            field_name = "Decoded Plain Text Result:"
            color_choice = discord.Color.green()

        if len(result) > 1000:
            result = result[:950] + "\n\n*(Truncated due to size limits...)*"

        embed = discord.Embed(title=title_text, color=color_choice)
        embed.add_field(name="Input:", value=f"`{text}`", inline=False)
        embed.add_field(name=field_name, value=f"`{result}`", inline=False)
        embed.set_footer(text=f"Processed for {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.defer(); await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:disapprove:1517452151012589662> Operation failed. Please check that your input perfectly matches the formatting for {encoding_type}! Error: {e}",
            ephemeral=True
        )


@bot.tree.command(name="translate", description="Translate text into another language")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(
    text="The message you want to translate",
    to_language="The language code to translate into (e.g., 'en', 'es', 'fr', 'ja')",
    from_language="Optional: Specify the original language code (defaults to auto-detect)"
)
async def translate(interaction: discord.Interaction, text: str, to_language: str = "en", from_language: str = "auto"):
    if interaction.guild and await run_automod_check_for_interaction(interaction, text, source_label="/translate"):
        return

    await interaction.response.defer(ephemeral=False)
    try:
        translator = GoogleTranslator(source=from_language, target=to_language)
        translated_text = translator.translate(text)
        await interaction.followup.send(content=translated_text)
    except Exception as e:
        await interaction.followup.send(f"<:disapprove:1517452151012589662> Translation failed. Please ensure you used valid ISO language codes! Error: {e}", ephemeral=True)


def _convert_image_to_gif(img: Image.Image) -> io.BytesIO:
    img = ImageOps.exif_transpose(img)
    buffer = io.BytesIO()

    if getattr(img, "is_animated", False):
        frames = [frame.copy().convert("RGBA") for frame in ImageSequence.Iterator(img)]
        if not frames:
            raise ValueError("No frames found in the provided image.")

        first_frame = frames[0]
        first_quantized = first_frame.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
        palette = first_quantized.getpalette()
        quantized_frames = []
        for frame in frames:
            quantized = frame.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
            if palette:
                quantized.putpalette(palette)
            quantized_frames.append(quantized)

        quantized_frames[0].save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=quantized_frames[1:],
            loop=0,
            duration=img.info.get("duration", 100),
            disposal=2,
            optimize=False,
        )
    else:
        converted = img.convert("RGBA")
        quantized = converted.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
        quantized.save(buffer, format="GIF", optimize=False)

    buffer.seek(0)
    return buffer


@bot.tree.command(name="gif", description="Convert an image attachment into a GIF file")
@app_commands.default_permissions(attach_files=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(image="The image to convert to GIF")
async def gif(interaction: discord.Interaction, image: discord.Attachment):
    await interaction.response.defer(ephemeral=True)

    if not image:
        await interaction.followup.send("<:disapprove:1517452151012589662> Please attach an image to convert.", ephemeral=True)
        return

    try:
        image_bytes = await image.read()
        with Image.open(io.BytesIO(image_bytes)) as img:
            buffer = _convert_image_to_gif(img)
            await interaction.followup.send(file=discord.File(buffer, filename="converted.gif"))

    except Exception as e:
        await interaction.followup.send(
            f"<:disapprove:1517452151012589662> Failed to convert the image to GIF. Please make sure the file is a valid image. Error: {e}",
            ephemeral=True
        )


YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_PATH = shutil.which("ffmpeg") or os.path.join(BASE_DIR, "ffmpeg")
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

song_queues: dict[str, dict] = {}


def get_song_queue(guild_id: str | int) -> dict:
    key = str(guild_id)
    queue = song_queues.setdefault(key, {
        'tracks': [],
        'current_index': 0,
        'loop': False,
        'pause_started_at': None,
        'track_start_time': None,
        'accumulated_pause': 0.0,
        'message_id': None,
        'channel_id': None,
        'ui_refresh_task': None,
    })
    return queue


def get_song_ui_channel(guild: discord.Guild, interaction: discord.Interaction | None = None, member: discord.Member | None = None) -> discord.abc.Messageable | None:
                                                                                       
    if member is not None and getattr(member, "voice", None) is not None and member.voice.channel is not None:
        voice_channel = member.voice.channel
        perms = voice_channel.permissions_for(guild.me) if guild is not None else None
        if perms is None or perms.send_messages:
            return voice_channel

    if interaction is not None and interaction.channel is not None:
        return interaction.channel

    if guild is None:
        return None

    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            return channel

    return None


async def ensure_song_ui_message(guild_id: str | int, interaction: discord.Interaction | None = None, member: discord.Member | None = None) -> discord.Message | None:
    queue = get_song_queue(guild_id)
    guild = bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
    if guild is None:
        return None

    if queue.get('message_id') and queue.get('channel_id'):
        channel = bot.get_channel(queue['channel_id'])
        if channel is not None:
            try:
                message = await channel.fetch_message(queue['message_id'])
                view = queue.get('view') or SongControlsView(guild_id)
                view.rebuild()
                queue['view'] = view
                await message.edit(view=view)
                return message
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                queue['message_id'] = None
                queue['channel_id'] = None

    send_channel = get_song_ui_channel(guild, interaction=interaction, member=member)
    if send_channel is None:
        return None

    view = queue.get('view') or SongControlsView(guild_id)
    view.rebuild()
    queue['view'] = view
    try:
        message = await send_channel.send(view=view)
        queue['message_id'] = message.id
        queue['channel_id'] = send_channel.id
        if queue.get('ui_refresh_task') is None or queue['ui_refresh_task'].done():
            queue['ui_refresh_task'] = asyncio.create_task(_song_ui_refresh_loop(guild_id))
        return message
    except Exception:
        print("[Song UI] Failed to send player UI")
        traceback.print_exc()
        return None


def get_current_elapsed(queue: dict) -> float:
    if not queue.get('track_start_time'):
        return 0.0
    if queue.get('pause_started_at'):
        return max(0.0, queue['pause_started_at'] - queue['track_start_time'] - queue['accumulated_pause'])
    return max(0.0, time.time() - queue['track_start_time'] - queue['accumulated_pause'])


def build_progress_bar(elapsed: float, duration: float, length: int = 10, is_paused: bool = False, is_looping: bool = False) -> str:
    if is_looping:
        icon = "<:loop:1518977798939742449>"
    elif is_paused:
        icon = "<:pause:1517497575219920986>"
    else:
        icon = "<:play:1517497576855965716>"
    if duration <= 0:
        return f"{icon} {'<:Square_Black:1517679889615032540>' * length}"
    progress = min(max(int((elapsed / duration) * length), 0), length)
    filled = "<:Square_Orange:1517679894526562405>" * progress
    empty = "<:Square_Black:1517679889615032540>" * (length - progress)
    return f"{icon} {filled}{empty}"


def build_song_container(guild_id: str | int) -> list | None:
    queue = get_song_queue(guild_id)
    if not queue.get('tracks') or queue['current_index'] >= len(queue['tracks']):
        return None

    track = queue['tracks'][queue['current_index']]
    duration = float(track.get('duration') or 0) or 0.0
    elapsed = min(get_current_elapsed(queue), duration)
    total = len(queue['tracks'])
    current = queue['current_index'] + 1
    progress_bar = build_progress_bar(elapsed, duration, 10, bool(queue.get('pause_started_at')), bool(queue.get('loop')))
    text_lines: list[TextDisplay | Section] = [
        TextDisplay("<:music:1517575582764765224> Now Playing"),
        Separator(),
    ]

    thumbnail_url = track.get('thumbnail')
    if thumbnail_url:
        text_lines.append(
            Section(
                TextDisplay(f"**{track.get('title', 'Unknown Title')}**\nRequested by **{track.get('requested_by', 'Unknown')}**"),
                accessory=Thumbnail(thumbnail_url),
            )
        )
    else:
        text_lines.append(TextDisplay(f"**{track.get('title', 'Unknown Title')}**"))
        text_lines.append(TextDisplay(f"Requested by **{track.get('requested_by', 'Unknown')}**"))

    text_lines.extend([
        TextDisplay(f"{progress_bar}  {format_duration(elapsed)} / {format_duration(duration)}"),
        TextDisplay(f"<:list:1517497572770451567> Track {current}/{total}"),
        TextDisplay("<:next:1518977801057861643> Up Next <:prev:1518977803092234331>"),
    ])

    next_tracks = queue['tracks'][queue['current_index'] + 1:queue['current_index'] + 6]
    if next_tracks:
        for index, item in enumerate(next_tracks, start=queue['current_index'] + 2):
            text_lines.append(TextDisplay(f"{index}. {item.get('title', 'Unknown Title')} • {item.get('requested_by', 'Unknown')}"))
    else:
        text_lines.append(TextDisplay("Nothing queued right now."))

    return text_lines


def build_song_embed(guild_id: str | int) -> discord.Embed | None:
    queue = get_song_queue(guild_id)
    if not queue.get('tracks') or queue['current_index'] >= len(queue['tracks']):
        return None

    track = queue['tracks'][queue['current_index']]
    duration = float(track.get('duration') or 0) or 0.0
    elapsed = min(get_current_elapsed(queue), duration)
    remaining = max(duration - elapsed, 0)
    progress = build_progress_bar(elapsed, duration, 10, bool(queue.get('pause_started_at')), bool(queue.get('loop')))
    embed = discord.Embed(
        title="<:music:1517575582764765224> Now Playing",
        description=f"**{track.get('title', 'Unknown Title')}**",
        color=discord.Color.orange(),
    )

    thumbnail = track.get('thumbnail')
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    embed.add_field(name="Requested by", value=str(track.get('requested_by', 'Unknown')), inline=True)
    embed.add_field(name="Track", value=f"{queue['current_index'] + 1}/{len(queue['tracks'])}", inline=True)
    embed.add_field(name="Progress", value=f"{progress}\n{format_duration(elapsed)} / {format_duration(duration)}", inline=False)
    embed.add_field(name="Time remaining", value=format_duration(remaining), inline=True)
    embed.add_field(name="Status", value="Paused" if queue.get('pause_started_at') else "Playing", inline=True)

    up_next = []
    for idx in range(queue['current_index'] + 1, min(len(queue['tracks']), queue['current_index'] + 5)):
        item = queue['tracks'][idx]
        up_next.append(f"{idx + 1}. {item.get('title', 'Unknown Title')} - {item.get('requested_by', 'Unknown')}")
    embed.add_field(name="Up Next", value="\n".join(up_next) if up_next else "No songs queued.", inline=False)
    return embed


class SongRemoveModal(Modal):
    def __init__(self, guild_id: str | int):
        super().__init__(title="Remove queued song")
        self.guild_id = str(guild_id)
        self.song_target = TextInput(
            label="Song number or title",
            placeholder="Example: 2 or my favorite song",
            required=True,
            max_length=120
        )
        self.add_item(self.song_target)

    async def on_submit(self, interaction: discord.Interaction):
        queue = get_song_queue(self.guild_id)
        if not queue.get('tracks'):
            await interaction.response.send_message("<:disapprove:1517452151012589662> There are no songs in the queue to remove.", ephemeral=True)
            return

        query = self.song_target.value.strip()
        match_index: int | None = None
        if query.isdigit():
            target = int(query) - 1
            if 0 <= target < len(queue['tracks']):
                match_index = target
        if match_index is None:
            normalized = query.lower()
            for index, track in enumerate(queue['tracks']):
                if normalized in track.get('title', '').lower():
                    match_index = index
                    break

        if match_index is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> I couldn't find that song in the queue.", ephemeral=True)
            return

        removed_track = queue['tracks'].pop(match_index)
        if queue['current_index'] > match_index:
            queue['current_index'] -= 1
        elif queue['current_index'] == match_index:
            queue['current_index'] = min(match_index, max(len(queue['tracks']) - 1, 0))
        if not queue['tracks']:
            queue['current_index'] = 0
            queue['track_start_time'] = None
            queue['pause_started_at'] = None
            queue['accumulated_pause'] = 0.0
            if interaction.guild and interaction.guild.voice_client and interaction.guild.voice_client.is_connected():
                interaction.guild.voice_client.stop()
            await interaction.response.send_message(f"<:trash:1517497581058527404> Removed **{removed_track.get('title', 'Unknown Title')}** from the queue.", ephemeral=True)
            return

        voice_client = interaction.guild.voice_client if interaction.guild else None
        if voice_client and voice_client.is_connected() and not voice_client.is_playing() and not voice_client.is_paused():
            await play_guild_song(self.guild_id, voice_client)

        await interaction.response.send_message(f"<:trash:1517497581058527404> Removed **{removed_track.get('title', 'Unknown Title')}** from the queue.", ephemeral=True)
        await _refresh_song_message(self.guild_id)


class SongControlsView(TimeoutDisabledLayoutView):
    def __init__(self, guild_id: str | int):
        super().__init__()
        self.guild_id = str(guild_id)
        self.previous_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id=f"song_prev_{self.guild_id}")
        self.next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id=f"song_next_{self.guild_id}")
        self.pause_button = Button(label="Pause", style=discord.ButtonStyle.secondary, custom_id=f"song_pause_{self.guild_id}")
        self.loop_button = Button(label="Loop: Off", style=discord.ButtonStyle.secondary, custom_id=f"song_loop_{self.guild_id}")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id=f"song_remove_{self.guild_id}")

        self.previous_button.callback = self.previous_song
        self.next_button.callback = self.next_song
        self.pause_button.callback = self.pause_song
        self.loop_button.callback = self.toggle_loop
        self.remove_button.callback = self.remove_song

        self.rebuild()

    def rebuild(self):
        self.clear_items()

        container_parts = []
        main_items = build_song_container(self.guild_id)
        if main_items is not None:
            container_parts.extend(main_items)
        else:
            container_parts.append(TextDisplay(":disapprove:1517452151012589662> Nothing is queued right now."))

        self.update_button_states()
        self.add_item(Container(*container_parts, accent_color=discord.Color.orange()))
        self.add_item(discord.ui.ActionRow(self.previous_button, self.next_button, self.pause_button, self.loop_button, self.remove_button))

    def update_button_states(self):
        queue = get_song_queue(self.guild_id)
        self.previous_button.disabled = queue.get('current_index', 0) <= 0
        self.next_button.disabled = queue.get('current_index', 0) + 1 >= len(queue.get('tracks', []))
        is_paused = bool(queue.get('pause_started_at'))
        self.pause_button.label = "Resume" if is_paused else "Pause"
        self.pause_button.style = discord.ButtonStyle.success if is_paused else discord.ButtonStyle.secondary
        self.loop_button.label = "Loop: On" if queue.get('loop') else "Loop: Off"
        self.loop_button.style = discord.ButtonStyle.success if queue.get('loop') else discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None and str(interaction.guild.id) == self.guild_id

    async def previous_song(self, interaction: discord.Interaction):
        queue = get_song_queue(self.guild_id)
        if not queue.get('tracks'):
            await interaction.response.send_message("<:disapprove:1517452151012589662> There is no queue to go back through.", ephemeral=True)
            return
        if queue['current_index'] <= 0:
            await interaction.response.send_message("<:disapprove:1517452151012589662> There is no previous song.", ephemeral=True)
            return

        queue['current_index'] -= 1
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            voice_client.stop()
        await interaction.response.send_message(f"<:prev:1518977803092234331> Now playing **{queue['tracks'][queue['current_index']]['title']}**.", ephemeral=True)
        if voice_client and voice_client.is_connected():
            await play_guild_song(self.guild_id, voice_client)
        await _refresh_song_message(self.guild_id)

    async def next_song(self, interaction: discord.Interaction):
        queue = get_song_queue(self.guild_id)
        if not queue.get('tracks'):
            await interaction.response.send_message("<:disapprove:1517452151012589662> The queue is empty.", ephemeral=True)
            return
        if queue['current_index'] + 1 >= len(queue['tracks']):
            queue['current_index'] = len(queue['tracks']) - 1
            if interaction.guild and interaction.guild.voice_client and interaction.guild.voice_client.is_connected():
                interaction.guild.voice_client.stop()
            await interaction.response.send_message("<:disapprove:1517452151012589662> No more songs in the queue.", ephemeral=True)
            await _refresh_song_message(self.guild_id)
            return

        queue['current_index'] += 1
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            voice_client.stop()
        await interaction.response.send_message(f"<:next:1518977801057865224> Skipping to **{queue['tracks'][queue['current_index']]['title']}**.", ephemeral=True)
        if voice_client and voice_client.is_connected():
            await play_guild_song(self.guild_id, voice_client)
        await _refresh_song_message(self.guild_id)

    async def pause_song(self, interaction: discord.Interaction):
        queue = get_song_queue(self.guild_id)
        voice_client = interaction.guild.voice_client if interaction.guild else None
        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("<:disapprove:1517452151012589662> I'm not connected to a voice channel.", ephemeral=True)
            return
        if voice_client.is_paused():
            voice_client.resume()
            if queue.get('pause_started_at'):
                queue['accumulated_pause'] += time.time() - queue['pause_started_at']
                queue['pause_started_at'] = None
            await interaction.response.send_message("<:play:1517497576855965716> Resumed playback.", ephemeral=True)
            await _refresh_song_message(self.guild_id)
            return
        if not voice_client.is_playing():
            await interaction.response.send_message("<:disapprove:1517452151012589662> Nothing is playing right now.", ephemeral=True)
            return
        voice_client.pause()
        queue['pause_started_at'] = time.time()
        await interaction.response.send_message("<:pause:1517497575219920986> Paused the song.", ephemeral=True)
        await _refresh_song_message(self.guild_id)

    async def toggle_loop(self, interaction: discord.Interaction):
        queue = get_song_queue(self.guild_id)
        queue['loop'] = not queue.get('loop', False)
        await interaction.response.send_message(f"<:loop:1518977798939742449> Looping is now {'enabled' if queue['loop'] else 'disabled'}.", ephemeral=True)
        await _refresh_song_message(self.guild_id)

    async def remove_song(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SongRemoveModal(self.guild_id))


async def _refresh_song_message(guild_id: str | int):
    queue = get_song_queue(guild_id)
    guild = bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
    if guild is not None and (guild.voice_client is None or not guild.voice_client.is_connected()):
        await _cleanup_song_message(guild_id)
        return
    if not queue.get('message_id') or not queue.get('channel_id'):
        return
    channel = bot.get_channel(queue['channel_id'])
    if not channel:
        return
    try:
        message = await channel.fetch_message(queue['message_id'])
        view = queue.get('view') or SongControlsView(guild_id)
        view.rebuild()
        queue['view'] = view
        await message.edit(view=view)
    except Exception:
        print("[Song UI] Failed to refresh player UI")
        traceback.print_exc()
        queue['message_id'] = None
        queue['channel_id'] = None


async def _song_ui_refresh_loop(guild_id: str | int):
    while True:
        await asyncio.sleep(5)
        queue = get_song_queue(guild_id)
        if not queue.get('tracks'):
            break
        if not queue.get('message_id') or not queue.get('channel_id'):
            break
        await _refresh_song_message(guild_id)

    queue = get_song_queue(guild_id)
    queue['ui_refresh_task'] = None


async def _cleanup_song_message(guild_id: str | int):
    queue = get_song_queue(guild_id)
    task = queue.get('ui_refresh_task')
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    queue['ui_refresh_task'] = None

    message_id = queue.get('message_id')
    channel_id = queue.get('channel_id')
    queue['message_id'] = None
    queue['channel_id'] = None
    if not message_id or not channel_id:
        return
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            message = await channel.fetch_message(message_id)
            await message.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


async def reset_song_queue_for_disconnect(guild_id: str | int):
    queue = get_song_queue(guild_id)
    queue['tracks'] = []
    queue['current_index'] = 0
    queue['track_start_time'] = None
    queue['pause_started_at'] = None
    queue['accumulated_pause'] = 0.0
    queue['loop'] = False
    queue['ui_refresh_task'] = None
    await _cleanup_song_message(guild_id)


async def _search_track(query: str) -> dict | None:
    if not query or not query.strip():
        return None
    url = query.strip()
    if not re.match(r'https?://', url):
        url = f"ytsearch1:{url}"
    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        return None
    if info.get('_type') == 'playlist':
        entries = info.get('entries') or []
        if not entries:
            return None
        info = entries[0]

    return {
        'title': info.get('title') or 'Unknown Title',
        'url': info.get('webpage_url') or info.get('url') or query,
        'thumbnail': info.get('thumbnail'),
        'duration': int(info.get('duration') or 0),
        'requested_by': 'Unknown',
    }


async def play_guild_song(guild_id: str | int, voice_client: discord.VoiceClient) -> bool:
    queue = get_song_queue(guild_id)
    if not queue.get('tracks'):
        return False
    if queue['current_index'] >= len(queue['tracks']):
        queue['current_index'] = max(0, len(queue['tracks']) - 1)
    track = queue['tracks'][queue['current_index']]

    try:
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(track['url'], download=False)
            if info and info.get('_type') == 'playlist':
                entries = info.get('entries') or []
                if entries:
                    info = entries[0]
            stream_url = info.get('url') if info and isinstance(info, dict) else None
            if not stream_url and info and isinstance(info, dict):
                formats = info.get('formats') or []
                if formats:
                    stream_url = next((f.get('url') for f in sorted(formats, key=lambda x: (x.get('quality') or 0, x.get('tbr') or 0), reverse=True) if f.get('url')), None)
            if not stream_url:
                raise ValueError("No playable stream URL found.")
            track['duration'] = int(info.get('duration') or 0) or track.get('duration', 0)
            track['thumbnail'] = info.get('thumbnail') or track.get('thumbnail')
            track['title'] = info.get('title') or track.get('title') or 'Unknown Title'
        audio_source = discord.FFmpegPCMAudio(stream_url, executable=FFMPEG_PATH, **FFMPEG_OPTIONS)

        def after_play(error):
            if error:
                print(f"[song] playback error: {error}")
            bot.loop.call_soon_threadsafe(asyncio.create_task, playback_ended(guild_id))

        voice_client.play(audio_source, after=after_play)
        queue['track_start_time'] = time.time()
        queue['accumulated_pause'] = 0.0
        queue['pause_started_at'] = None
        await _refresh_song_message(guild_id)
        return True
    except Exception as exc:
        print(f"[song] failed to start playback: {exc}")
        return False


async def playback_ended(guild_id: str | int):
    queue = get_song_queue(guild_id)
    if not queue.get('tracks'):
        await _cleanup_song_message(guild_id)
        return

    if queue.get('loop'):
        guild = bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
        if guild and guild.voice_client and guild.voice_client.is_connected():
            await play_guild_song(guild_id, guild.voice_client)
        return

    if queue['current_index'] + 1 < len(queue['tracks']):
        queue['current_index'] += 1
        guild = bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
        if guild and guild.voice_client and guild.voice_client.is_connected():
            await play_guild_song(guild_id, guild.voice_client)
        return

    queue['current_index'] = len(queue['tracks']) - 1
    queue['track_start_time'] = None
    queue['pause_started_at'] = None
    queue['accumulated_pause'] = 0.0
    await _refresh_song_message(guild_id)


@bot.tree.command(name="song", description="Play a song or open the current queue UI")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@app_commands.describe(query="Song name or YouTube URL to play. Leave blank to show the current player.")
async def song(interaction: discord.Interaction, query: str | None = None):
    await interaction.response.defer()

    if interaction.guild is None:
        await interaction.followup.send("This command can only be used in a server voice channel.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    queue = get_song_queue(guild_id)

    if query:
        if interaction.user.voice is None or interaction.user.voice.channel is None:
            await interaction.followup.send("<:disapprove:1517452151012589662> Join a voice channel first.", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client
        if voice_client is None:
            await channel.connect()
            voice_client = interaction.guild.voice_client
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)

        if not voice_client:
            await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't join the voice channel.", ephemeral=True)
            return

        track = await _search_track(query)
        if not track:
            await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't find that song.", ephemeral=True)
            return
        track['requested_by'] = str(interaction.user)
        queue['tracks'].append(track)
        queue['current_index'] = min(queue['current_index'], max(len(queue['tracks']) - 1, 0))

        if not voice_client.is_playing() and not voice_client.is_paused() and len(queue['tracks']) == 1:
            await play_guild_song(guild_id, voice_client)

        await interaction.followup.send(f"<:music:1517575582764765224> Added **{track['title']}** to the queue.", ephemeral=False)
        await ensure_song_ui_message(guild_id, interaction=interaction, member=interaction.user)
        return

    if not queue.get('tracks'):
        await interaction.followup.send("<:disapprove:1517452151012589662> There is nothing in the queue yet. Try /song <song name or URL>.", ephemeral=True)
        return

    message = await ensure_song_ui_message(guild_id, interaction=interaction, member=interaction.user)
    if message is None:
        await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't find a text channel to post the player into.", ephemeral=True)
        return

    send_channel = bot.get_channel(queue['channel_id']) if queue.get('channel_id') else None
    if send_channel is not None:
        await interaction.followup.send(f"<:music:1517575582764765224> Now playing in {send_channel.mention}.", ephemeral=True)
    else:
        await interaction.followup.send("<:music:1517575582764765224> The player is live in the current voice text channel.", ephemeral=True)


@bot.tree.command(name="voice-leave", description="Leave the current voice channel")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
async def voice_leave(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("<:disapprove:1517452151012589662> This command can only be used in a server voice channel.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_connected():
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("<:disapprove:1517452151012589662> I'm not connected to a voice channel right now.", ephemeral=True)
        return

    await reset_song_queue_for_disconnect(guild_id)
    if voice_client.is_connected():
        voice_client.stop()
        await voice_client.disconnect()

    await interaction.response.defer()
    await interaction.followup.send("<:leave:1518977801485588083> Left the voice channel.")


@bot.tree.command(name="afk", description="Set yourself as AFK with a reason")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@app_commands.describe(reason="Why you're going AFK")
async def afk_command(interaction: discord.Interaction, reason: str = None):
    if interaction.guild is None:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        return

    member = interaction.user
    if not isinstance(member, discord.Member):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        return

    reason_text = (reason or "No reason provided.").strip() or "No reason provided."
    if interaction.guild and await run_automod_check_for_interaction(interaction, reason_text, source_label="/afk"):
        return

    already_afk = await set_afk_status(member, reason_text)
    if already_afk:
        await interaction.response.defer(); await interaction.followup.send(f"<:afk:1525440143245180970> {member.mention} is now AFK. Reason: {reason_text}")
    else:
        current_reason = get_afk_reason(afk_status.get(get_afk_status_key(member.guild.id, member.id)))
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:warning:1517452174991556758> You are already AFK. Reason: {current_reason}", ephemeral=True)


@bot.tree.command(name="roll", description="Roll a 6-sided die")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def roll(interaction: discord.Interaction):
    result = random.randint(1, 6)
    await interaction.response.defer(); await interaction.followup.send(f"🎲 You rolled a **{result}**!")


@bot.tree.command(name="random", description="Pick a random number between two values")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(min_value="The lowest number", max_value="The highest number")
async def random_cmd(interaction: discord.Interaction, min_value: int, max_value: int):
    low, high = min(min_value, max_value), max(min_value, max_value)
    result = random.randint(low, high)
    await interaction.response.defer(); await interaction.followup.send(f"<:list:1517497572770451567> Your random number between **{low}** and **{high}** is: **{result}**")


@bot.tree.command(name="serverinfo", description="Display detailed information about this server")
@app_commands.allowed_installs(guilds=True, users=False)
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    created_at = discord_timestamp(guild.created_at)
    joined_at = discord_timestamp(interaction.user.joined_at) if interaction.user.joined_at else "Unknown"
    total_count = guild.member_count
    bot_count = len([m for m in guild.members if m.bot])
    human_count = total_count - bot_count

    embed = discord.Embed(title=f"Information for {guild.name}", color=discord.Color.blue())
    embed.add_field(name="<:chalice:1517579767573123092> Server Owner", value=f"{format_user_reference(guild.owner)}", inline=True)
    embed.add_field(name="<:timer:1517996239583576194> Created At", value=created_at, inline=True)
    embed.add_field(name="<:plus:1518348756570079262> Joined At (user)", value=joined_at, inline=True)
    vanity = guild.vanity_url_code if guild.vanity_url_code else "-"
    embed.add_field(name="<:minus:1518348754111959150> Vanity Link", value=vanity, inline=True)
    embed.add_field(name="<:internet:1518376144246804672> Preferred Locale", value=f"{guild.preferred_locale}", inline=True)
    embed.add_field(name="<:shield:1518340640801427566> Verification Level", value=str(guild.verification_level).capitalize(), inline=True)
    boost_info = f"{guild.premium_subscription_count} (Level {guild.premium_tier})"
    embed.add_field(name="<:spark:1517583248421552305> Server Boosts", value=boost_info, inline=True)
    embed.add_field(name="<:drawer:1517497564189036574> Channels", value=f"{len(guild.channels)}", inline=True)
    embed.add_field(name="<:multi:1518348755261460661> Roles", value=f"{len(guild.roles)}", inline=True)
    embed.add_field(name="\n<:graph:1517584522877866065> Members", value=" ", inline=False)
    embed.add_field(name="<:approuve:1517452125687513158> Real Accounts", value=str(human_count), inline=True)
    embed.add_field(name="<:disapprove:1517452151012589662> Bots", value=str(bot_count), inline=True)
    embed.add_field(name="<:warning:1517452174991556758> Total", value=str(total_count), inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="channelinfo", description="Show configured channels for this server")
@app_commands.allowed_installs(guilds=True, users=False)
async def channelinfo(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This command must be used in a server.", ephemeral=True)
        return

    guild = interaction.guild
    guild_id = str(guild.id)

    guild_config, _ = get_guild_config(guild_id)
    levels = load_levels()
    board_data = load_board_data()
    locked, admin_log = load_lock_config()

    def fmt_channel(cid):
        if not cid:
            return "Not set"
        try:
            cid_int = int(cid)
        except Exception:
            return str(cid)
        ch = guild.get_channel(cid_int)
        if ch is not None:
            return ch.mention
        return f"<#{cid_int}>"

    welcome = fmt_channel(guild_config.get("welcome_channel_id"))
    goodbye = fmt_channel(guild_config.get("goodbye_channel_id"))

    lvl_channel = "Not set"
    if guild_id in levels:
        lvl_channel_id = levels[guild_id].get("config", {}).get("channel_id")
        if lvl_channel_id:
            lvl_channel = fmt_channel(lvl_channel_id)

    board_entries = []
    if guild_id in board_data:
        for emoji_key, cfg in board_data[guild_id].items():
            ch_id = cfg.get("channel_id")
            required = cfg.get("required_count") or cfg.get("required") or cfg.get("required_count", None)
            channel_repr = fmt_channel(ch_id)

            req_text = f"required {required}" if required is not None else "required ?"
            board_entries.append(f"{emoji_key} in {channel_repr} ({req_text})")
    board_channels = "\n".join(board_entries) if board_entries else "None"

    counter_entries = []
    counters = guild_config.get("counter_channels", {})
    for ch_key, cfg in counters.items():
        try:
            ch = guild.get_channel(int(ch_key))
            ch_repr = ch.mention if ch else f"<#{ch_key}"
        except Exception:
            ch_repr = str(ch_key)
        current_val = cfg.get("current_value", 0)
        counter_entries.append(f"{ch_repr}: {current_val}")
    counter_channels = "\n".join(counter_entries) if counter_entries else "None"

    admin_log_channels_list = []
    if admin_log and isinstance(admin_log, dict):
        for ch_id in admin_log.keys():
            try:
                ch = guild.get_channel(int(ch_id))
                if ch:
                    admin_log_channels_list.append(ch.mention)
            except Exception:
                continue
    admin_log_channel = "\n".join(admin_log_channels_list) if admin_log_channels_list else "Not set"

    honeypot_channel = fmt_channel(guild_config.get("honeypot_channel_id"))

    embed = discord.Embed(title=f"<:drawer:1517497564189036574> Configured Channels for {guild.name}", color=discord.Color.blurple())
    embed.add_field(name="<:plus:1518348756570079262> Welcome Channel", value=welcome, inline=False)
    embed.add_field(name="<:minus:1518348754111959150> Goodbye Channel", value=goodbye, inline=False)
    embed.add_field(name="<:chalice:1517579767573123092> Level-up and Quest Announce Channel", value=lvl_channel, inline=False)
    embed.add_field(name="<:graph:1517584522877866065> Board Channels", value=board_channels, inline=False)
    embed.add_field(name="<:list:1517497572770451567> Counter Channels", value=counter_channels, inline=False)
    embed.add_field(name="<:unlocked:1517574880034558102> Admin Log Channel", value=admin_log_channel, inline=False)
    embed.add_field(name="<:honey:1524116282075512842> Honeypot Channel", value=honeypot_channel, inline=False)
    embed.set_footer(text=f"Run /settings and go to channel settings to change these settings.")

    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.command(name="say")
async def prefix_say(ctx: commands.Context, *, message: str):
    is_bot_owner = await bot.is_owner(ctx.author)
    is_server_owner = bool(ctx.guild and ctx.author == ctx.guild.owner)
    is_admin = bool(
        ctx.guild and isinstance(ctx.author, discord.Member) and (
            ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild
        )
    )

    if not (is_bot_owner or is_server_owner or is_admin):
        return await ctx.send(f"<:disapprove:1517452151012589662> this {PREFIX} command is restricted to the bot owner, server owner, or admins only.")

    if ctx.guild and await run_automod_check_for_content(ctx.guild, ctx.author, ctx.channel, message, source_label="/say"):
        return

    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.HTTPException):
        pass

    await ctx.send(message)


@bot.tree.command(name="say", description="Make the bot say something")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def say(interaction: discord.Interaction, message: str):
    if interaction.guild and await run_automod_check_for_content(interaction.guild, interaction.user, interaction.channel, message, source_label="/say"):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Blocked word or phrase detected.", ephemeral=True)
        return

    await interaction.response.defer(); await interaction.followup.send(message)

class CustomEmbedModal(Modal):
    def __init__(self, color: discord.Color, thumbnail: str, image: str, footer_text: str, footer_icon: str):
        super().__init__(title="Configure Your Custom Embed")
        
        self.embed_color = color
        self.thumbnail_url = thumbnail
        self.image_url = image
        self.footer_text = footer_text
        self.footer_icon = footer_icon

        self.embed_title = TextInput(
            label="Embed Title",
            placeholder="Enter the main title (Optional)...",
            required=False,
            max_length=256
        )
        self.embed_author = TextInput(
            label="Author Name",
            placeholder="Display a small creator name at the very top (Optional)...",
            required=False,
            max_length=256
        )
        self.embed_author_icon = TextInput(
            label="Author Icon URL",
            placeholder="Direct link to a small image for the author icon (Optional)...",
            required=False
        )
        self.embed_description = TextInput(
            label="Embed Description",
            style=discord.TextStyle.paragraph,
            placeholder="Enter the main body text content here...",
            required=True,
            max_length=4000
        )
        self.embed_url = TextInput(
            label="Title Hyperlink URL",
            placeholder="Make the title clickable by adding a web link (Optional)...",
            required=False
        )
        
        self.add_item(self.embed_author)
        self.add_item(self.embed_author_icon)
        self.add_item(self.embed_title)
        self.add_item(self.embed_url)
        self.add_item(self.embed_description)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=self.embed_title.value if self.embed_title.value else None,
            description=self.embed_description.value,
            url=self.embed_url.value if self.embed_url.value else None,
            color=self.embed_color
        )
        
        if self.embed_author.value:
            embed.set_author(
                name=self.embed_author.value,
                icon_url=self.embed_author_icon.value if self.embed_author_icon.value else None
            )
        
        if self.thumbnail_url:
            embed.set_thumbnail(url=self.thumbnail_url)
        if self.image_url:
            embed.set_image(url=self.image_url)
            
        if self.footer_text:
            embed.set_footer(
                text=self.footer_text,
                icon_url=self.footer_icon if self.footer_icon else None
            )
        else:
            embed.set_footer(
                text=f"Created by {interaction.user.name}", 
                icon_url=interaction.user.display_avatar.url
            )

        await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="embed", description="Create a fully-loaded customized embed message using a styling menu")
@app_commands.describe(
    color="Choose a preset theme color for the embed accent line",
    footer="Optional: Custom text at the very bottom row of the embed",
    footer_icon="Optional: Direct image URL for a tiny icon next to the footer text",
    thumbnail="Optional: Direct image URL to place as a small card in the top right",
    image="Optional: Direct image URL to place as a giant full-width display banner"
)
@app_commands.choices(
    color=[
        app_commands.Choice(name="🔴 Red", value="red"),
        app_commands.Choice(name="🔵 Blue", value="blue"),
        app_commands.Choice(name="🟢 Green", value="green"),
        app_commands.Choice(name="🟡 Yellow", value="yellow"),
        app_commands.Choice(name="🟣 Purple", value="purple"),
        app_commands.Choice(name="⚫ Dark Grey", value="dark"),
        app_commands.Choice(name="<:spark:1517583248421552305> Random Color", value="random")
    ]
)
async def embed_builder(
    interaction: discord.Interaction,
    color: str = "blue",
    footer: str = None,
    footer_icon: str = None,
    thumbnail: str = None,
    image: str = None
):
    color_map = {
        "red": discord.Color.red(),
        "blue": discord.Color.blue(),
        "green": discord.Color.green(),
        "yellow": discord.Color.yellow(),
        "purple": discord.Color.purple(),
        "dark": discord.Color.dark_embed(),
        "random": discord.Color.random()
    }
    chosen_color = color_map.get(color, discord.Color.blue())

    modal = CustomEmbedModal(
        color=chosen_color, 
        thumbnail=thumbnail, 
        image=image, 
        footer_text=footer,
        footer_icon=footer_icon
    )
    await interaction.response.send_modal(modal)


@bot.tree.context_menu(name="Rizz Meter")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def rizz_menu(interaction: discord.Interaction, message: discord.Message):
    percentage = random.randint(0, 100)
    original_text = message.content if message.content else "*[Media or Embed]*"
    await interaction.response.defer(); await interaction.followup.send(f"> This message has **{percentage}%** Rizz.\n-# **{message.author.display_name}:** {original_text}")


@bot.tree.context_menu(name="Cringe Meter")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def cringe_menu(interaction: discord.Interaction, message: discord.Message):
    percentage = random.randint(0, 100)
    original_text = message.content if message.content else "*[Media or Embed]*"
    await interaction.response.defer(); await interaction.followup.send(f"> This message is **{percentage}%** Cringe.\n-# **{message.author.display_name}:** {original_text}")


@bot.tree.command(name="quests", description="Show your current quests")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
async def show_quests(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Quests are only available in servers.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    if not is_economy_enabled(guild_id) or not is_levels_enabled(guild_id):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Quests require both economy and levels to be enabled on this server.", ephemeral=True)
        return

    user_id = str(interaction.user.id)
    user_entry = ensure_user_quests(guild_id, user_id)

                                                    
    class QuestView(TimeoutDisabledLayoutView):
        def __init__(self, guild: discord.Guild, user_id: str, user_entry: dict):
            super().__init__(timeout=600)
            self.guild = guild
            self.user_id = user_id
            self.user_entry = user_entry
            self.build_components()

        def build_components(self):
            self.clear_items()
            color_value = get_user_color_value(self.user_id)
            color_name = resolve_user_color_name(get_user_color(self.user_id) or "white")
            fill_emoji = COLOR_EMOJIS.get(color_name, COLOR_EMOJIS.get("white"))
            empty_emoji = COLOR_EMOJIS.get("black")

            lines = []
            lines.append(TextDisplay("## <:shield:1518340640801427566> Quests"))
            lines.append(Separator())

            daily_info = self.user_entry.get("daily", {})
            quests = daily_info.get("quests", [])
            lines.append(TextDisplay("<:hourglass:1517574046252924938> **Daily Quests**"))
            for i, q in enumerate(quests, start=1):
                name = q.get("name")
                rewards = f"${q.get('reward_money')} • {q.get('reward_xp')} XP"
                progress = q.get("progress", 0)
                target = q.get("target", 0)
                pct = 0 if target == 0 else progress / target
                filled = int(pct * 10)
                bar = (fill_emoji * filled) + (empty_emoji * (10 - filled))
                lines.append(TextDisplay(f"{name} — {rewards}"))
                lines.append(TextDisplay(f"{bar} {progress}/{target}"))

            lines.append(Separator())
            weekly_info = self.user_entry.get("weekly", {})
            wq = weekly_info.get("quest")
            lines.append(TextDisplay("<:timer:1517996239583576194> **Weekly Quest**"))
            if wq:
                name = wq.get("name")
                rewards = f"${wq.get('reward_money')} • {wq.get('reward_xp')} XP"
                progress = wq.get("progress", 0)
                target = wq.get("target", 0)
                pct = 0 if target == 0 else progress / target
                filled = int(pct * 10)
                bar = (fill_emoji * filled) + (empty_emoji * (10 - filled))
                lines.append(TextDisplay(f"{name} — {rewards}"))
                lines.append(TextDisplay(f"{bar} {progress}/{target}"))
            else:
                lines.append(TextDisplay("<:disapprove:1517452151012589662> No weekly quest assigned."))

            lines.append(Separator())
            daily_assigned = daily_info.get("assigned_at")
            weekly_assigned = weekly_info.get("assigned_at")
            next_daily = _next_daily_reset(datetime.fromisoformat(daily_assigned) if daily_assigned else None)
            next_weekly = _next_weekly_reset(weekly_assigned)
            try:
                daily_ts = int(next_daily.timestamp())
            except Exception:
                daily_ts = None
            try:
                weekly_ts = int(next_weekly.timestamp())
            except Exception:
                weekly_ts = None

            daily_display = f"<t:{daily_ts}:F>" if daily_ts else "Unknown"
            weekly_display = f"<t:{weekly_ts}:F>" if weekly_ts else "Unknown"
            lines.append(TextDisplay(f"<:gear:1517576939097952496> Next quests: Daily → {daily_display} • Weekly → {weekly_display}"))

            container = Container(*lines, accent_color=color_value)
            self.add_item(container)

    view = QuestView(interaction.guild, user_id, user_entry)
    await interaction.response.defer(); await interaction.followup.send(view=view)


@bot.tree.context_menu(name="Stupid Meter")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def stupid_menu(interaction: discord.Interaction, message: discord.Message):
    percentage = random.randint(0, 100)
    original_text = message.content if message.content else "*[Media or Embed]*"
    await interaction.response.defer(); await interaction.followup.send(f"> This message is **{percentage}%** Stupid.\n-# **{message.author.display_name}:** {original_text}")


@bot.tree.context_menu(name="Lie Meter")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def lie_menu(interaction: discord.Interaction, message: discord.Message):
    percentage = random.randint(0, 100)
    original_text = message.content if message.content else "*[Media or Embed]*"
    await interaction.response.defer(); await interaction.followup.send(f"> This message is **{percentage}%** a Lie.\n-# **{message.author.display_name}:** {original_text}")


@bot.tree.context_menu(name="Quote")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def quote_menu(interaction: discord.Interaction, message: discord.Message):
    try:
        await interaction.response.defer(thinking=True)
    except Exception:
        pass
    quote_file = await create_quote_card(message, viewer_id=interaction.user.id)
    if quote_file is None:
        try:
            await interaction.followup.send("<:disapprove:1517452151012589662> Unable to create quote image right now.", ephemeral=True)
        except Exception:
            pass
        return
    try:
        await interaction.followup.send(file=quote_file)
    except Exception:
        try:
            await interaction.response.defer(); await interaction.followup.send(file=quote_file)
        except Exception:
            pass


@bot.tree.command(name="love", description="Check the compatibility between two things or users")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(item1="The first person or thing", item2="The second person or thing")
async def love(interaction: discord.Interaction, item1: str, item2: str):
    content = f"{item1} {item2}".strip()
    if interaction.guild and await run_automod_check_for_interaction(interaction, content, source_label="/love"):
        return

    love_data = load_love_data()
    guild_id = str(interaction.guild.id) if interaction.guild else "dm"
    if guild_id not in love_data:
        love_data[guild_id] = {}
    pair = sorted([item1.lower().strip(), item2.lower().strip()])
    match_key = f"{pair[0]}&{pair[1]}"
    if match_key in love_data[guild_id]:
        score = love_data[guild_id][match_key]
    else:
        score = random.randint(1, 100)
        love_data[guild_id][match_key] = score
        save_love_data(love_data)
    filled = max(0, int(score / 10))
    bar = "<:Square_Red:1517679897068306522>" * filled + "<:Square_Black:1517679889615032540>" * (10 - filled)
    embed = discord.Embed(title="Love Compatibility <:heart:1517577673763979344>", color=discord.Color.red())
    embed.add_field(name="Match", value=f"{item1} & {item2}", inline=False)
    embed.add_field(name="Compatibility", value=f"**{score}%**\n{bar}", inline=False)
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="rate-cool", description="Rate how cool someone is")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(username="The person or thing to rate")
async def rate_cool(interaction: discord.Interaction, username: str):
    if interaction.guild and await run_automod_check_for_interaction(interaction, username, source_label="/rate-cool"):
        return

    love_data = load_love_data()
    guild_id = str(interaction.guild.id) if interaction.guild else "dm"
    if guild_id not in love_data:
        love_data[guild_id] = {}
    cool_key = f"cool_{username.lower().strip()}"
    if cool_key in love_data[guild_id]:
        score = love_data[guild_id][cool_key]
    else:
        score = random.randint(1, 100)
        love_data[guild_id][cool_key] = score
        save_love_data(love_data)
    filled = max(0, int(score / 10))
    bar = "<:Square_Yellow:1517679899769311302>" * filled + "<:Square_Black:1517679889615032540>" * (10 - filled)
    embed = discord.Embed(title="Coolness Rating <:spark:1517583248421552305>", color=discord.Color.yellow())
    embed.add_field(name="User", value=username, inline=False)
    embed.add_field(name="Coolness", value=f"**{score}%**\n{bar}", inline=False)
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="rate-gay", description="Rate how gay someone is")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(username="The person or thing to rate")
async def rate_gay(interaction: discord.Interaction, username: str):
    if interaction.guild and await run_automod_check_for_interaction(interaction, username, source_label="/rate-gay"):
        return

    love_data = load_love_data()
    guild_id = str(interaction.guild.id) if interaction.guild else "dm"
    if guild_id not in love_data:
        love_data[guild_id] = {}
    gay_key = f"gay_{username.lower().strip()}"
    if gay_key in love_data[guild_id]:
        score = love_data[guild_id][gay_key]
    else:
        score = random.randint(1, 100)
        love_data[guild_id][gay_key] = score
        save_love_data(love_data)
    filled = max(0, int(score / 10))
    bar = "<:Square_Blue:1517679890932043897>" * filled + "<:Square_Black:1517679889615032540>" * (10 - filled)
    embed = discord.Embed(title="Gayness Rating <:rainbow:1518708398772846722>", color=discord.Color.blue())
    embed.add_field(name="User", value=username, inline=False)
    embed.add_field(name="Gayness", value=f"**{score}%**\n{bar}", inline=False)
    await interaction.response.defer(); await interaction.followup.send(embed=embed)

EIGHTBALL_RESPONSES = [
    "It is certain.",
    "It is decidedly so.",
    "Without a doubt.",
    "Yes - definitely.",
    "You may rely on it.",
    "As I see it, yes.",
    "Most likely.",
    "Outlook good.",
    "Yes.",
    "Signs point to yes.",
    "Better not tell you.",
    "Cannot predict.",
    "I dont know.",
    "Don't count on it.",
    "My reply is no.",
    "My sources say no.",
    "Outlook not so good.",
    "Very doubtful."
    "No.",
    "Absolutely not.",
]


@bot.tree.command(name="8ball", description="Ask the magic 8-ball a question")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(question="The question you want the 8-ball to answer")
async def eight_ball(interaction: discord.Interaction, question: str):
    if interaction.guild and await run_automod_check_for_interaction(interaction, question, source_label="/8ball"):
        return

    rate_data = load_love_data()
    guild_id = str(interaction.guild.id) if interaction.guild else "dm"
    if guild_id not in rate_data:
        rate_data[guild_id] = {}

    question_key = f"8ball_{question.lower().strip()}"
    if question_key in rate_data[guild_id]:
        response = rate_data[guild_id][question_key]
    else:
        response = random.choice(EIGHTBALL_RESPONSES)
        rate_data[guild_id][question_key] = response
        save_love_data(rate_data)

    embed = discord.Embed(title="Magic 8-Ball <:8ball:1533654157477679365>", color=discord.Color.dark_gray())
    embed.add_field(name="Question", value=question, inline=False)
    embed.add_field(name="Answer", value=response, inline=False)
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


def format_uptime(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


@bot.tree.command(name="stats", description="Show bot statistics and status")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def stats(interaction: discord.Interaction):
    load_dotenv(override=True)
    VERSION = os.getenv('BOT_VERSION')
    VERSION_ALTERNATE = os.getenv('BOT_VERSION_ALTERNATE')
    ACTIVITY_TEXT = os.getenv('ACTIVITY')
    total_guilds = len(bot.guilds)
    start_time = time.perf_counter()
    await interaction.response.defer()
    ws_latency = round(bot.latency * 1000)
    end_time = time.perf_counter()
    api_latency = round((end_time - start_time) * 1000)

    embed = discord.Embed(
        title="<:gear:1517576939097952496> Bot Statistics",
        color=discord.Color.gold(),
        description="Current status and technical details of the bot."
    )
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else bot.user.default_avatar.url)
    embed.add_field(name="<:gear:1517576939097952496> Version", value=f"ver{VERSION} | {VERSION_ALTERNATE}\n{ACTIVITY_TEXT}", inline=True)
    embed.add_field(name="<:internet:1518376144246804672> Servers", value=str(total_guilds), inline=True)
    embed.add_field(name="<:graph:1517584522877866065> Total Users", value=str(len(bot.users)), inline=True)
    embed.add_field(name="<:timer:1517996239583576194> WebSocket", value=f"{ws_latency}ms", inline=True)
    embed.add_field(name="<:hourglass:1517574046252924938> API Round-Trip", value=f"{api_latency}ms", inline=True)
    embed.add_field(name="<:python:1518376147413635154> Library", value=f"discord.py {discord.__version__}", inline=True)

    guild_shard_id = interaction.guild.shard_id if interaction.guild else 0
    total_shards = len(bot.shards) or 1
    shard_info = f"Shard id: {guild_shard_id} | total: {total_shards}"
    embed.add_field(name="<:shard:1518376149741338744> Shard Info", value=shard_info, inline=True)

    app_info = await bot.application_info()
    if app_info.team:
        owner_value = app_info.team.name
    elif app_info.owner:
        owner_value = f"{app_info.owner.name}#{app_info.owner.discriminator}"
    else:
        owner_value = "Unknown"

    embed.add_field(name="<:nUtils:1518376146008539146> Bot owner", value=owner_value, inline=True)
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="quickstats", description="Show bot statistics and status in a compact format")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def quickstats(interaction: discord.Interaction):
    load_dotenv(override=True)
    await interaction.response.defer(); await interaction.followup.send(f"ver : **{os.getenv('BOT_VERSION')}**  |  alt : **{os.getenv('BOT_VERSION_ALTERNATE')}**  |  **{os.getenv('ACTIVITY')}**  |  servers : **{len(bot.guilds)}**  |  users : **{len(bot.users)}**", allowed_mentions=discord.AllowedMentions.none())


@bot.tree.command(name="help", description="Browse the bot commands in a paginated list")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message(view=HelpCommandsView(str(interaction.user.id)), ephemeral=True)


class HelpSearchModal(Modal):
    def __init__(self, help_view):
        super().__init__(title="Search help")
        self.help_view = help_view
        self.query = TextInput(label="Command, category, or keyword", placeholder="Try: economy, ping, fun", required=True, max_length=100)
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        search_value = (self.query.value or "").strip().lower()
        defs = load_help_definitions()
        commands = defs.get("commands", {}) if isinstance(defs.get("commands", {}), dict) else {}

        matches = []
        for command_name, entry in commands.items():
            if not isinstance(command_name, str) or not isinstance(entry, dict):
                continue
            haystack = " ".join([
                command_name.lower(),
                str(entry.get("description") or "").lower(),
                str(entry.get("environement") or "").lower(),
                str(entry.get("category") or "").lower(),
            ])
            if search_value and search_value in haystack:
                matches.append(command_name)

        self.help_view.search_query = search_value or None
        self.help_view.search_matches = matches
        self.help_view.page = 0
        self.help_view.build_components()

        try:
            await interaction.response.edit_message(view=self.help_view)
        except Exception:
            try:
                await interaction.followup.send(view=self.help_view, ephemeral=True)
            except Exception:
                pass


class HelpCommandsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: str, page: int = 0):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.page = page
        self.per_page = 7
        self.search_query = None
        self.search_matches = []
        self.build_components()

    def build_components(self):
        self.clear_items()
        defs = load_help_definitions()
        commands = defs.get("commands", {}) if isinstance(defs.get("commands", {}), dict) else {}
        command_names = [name for name in commands.keys() if isinstance(name, str) and name.strip()]
        if not command_names:
            command_names = ["/help", "/ping", "/stats", "/avatar", "/banner", "/emoji", "/daily", "/balance", "/shop"]

        tutorial = (defs.get("mini_tutorial") or "").strip() or (
            "Use slash commands to explore the bot.\n"
            "Tip: some commands are guild-only, some work in DMs, and some require permissions."
        )

        if self.search_query:
            matches = self.search_matches
            total_pages = max(1, (len(matches) + self.per_page - 1) // self.per_page)
            self.page = max(0, min(self.page, total_pages - 1))
            visible = matches[self.page * self.per_page:(self.page + 1) * self.per_page]
            heading = f"Search results for: **{self.search_query}**"
            page_label = f"Page {self.page + 1}/{total_pages} · {len(matches)} match(es)"
            no_results = not matches
        else:
            total_pages = 1 if len(command_names) <= 3 else 1 + ((len(command_names) - 3 + self.per_page - 1) // self.per_page)
            self.page = max(0, min(self.page, total_pages - 1))
            page_label = f"Page {self.page + 1}/{total_pages}"
            if self.page == 0:
                visible = command_names[:3]
            else:
                start = 3 + (self.page - 1) * self.per_page
                visible = command_names[start:start + self.per_page]
            heading = "Browse the available commands page by page."
            no_results = False

        parts = [
            TextDisplay("## <:nUtils:1518376146008539146> Help menu"),
            TextDisplay(heading),
            Separator(),
            TextDisplay(page_label),
        ]

        if not self.search_query and self.page == 0:
            parts.append(TextDisplay(tutorial))

        if self.search_query and no_results:
            parts.append(TextDisplay(f"No command matched: **{self.search_query}**"))

        for command_name in visible:
            entry = commands.get(command_name, {}) if isinstance(commands.get(command_name, {}), dict) else {}
            description = (entry.get("description") or "No description set yet.").strip() or "No description set yet."
            environment = (entry.get("environement") or "Not set").strip() or "Not set"
            category = (entry.get("category") or "General").strip() or "General"
            section_text = f"**{command_name}**\n{description}\nCategory: {category}\nEnvironment: {environment}"
            parts.append(TextDisplay(section_text))

        parts.append(Separator())
        self.add_item(Container(*parts, accent_color=discord.Color.blue()))

        if self.search_query:
            search_total_pages = max(1, (len(self.search_matches) + self.per_page - 1) // self.per_page)
            prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="help_prev", disabled=self.page == 0 or not self.search_matches)
            next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="help_next", disabled=self.page >= search_total_pages - 1 or not self.search_matches)
        else:
            prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="help_prev", disabled=self.page == 0)
            next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="help_next", disabled=self.page >= total_pages - 1)

        search_button = Button(label="Search", style=discord.ButtonStyle.primary, custom_id="help_search")

        async def prev_cb(interaction: discord.Interaction):
            if self.page > 0:
                self.page -= 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        async def next_cb(interaction: discord.Interaction):
            if self.search_query:
                max_page = max(1, (len(self.search_matches) + self.per_page - 1) // self.per_page)
                if self.page < max_page - 1:
                    self.page += 1
                    self.build_components()
                    await interaction.response.edit_message(view=self)
            elif self.page < total_pages - 1:
                self.page += 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        async def search_cb(interaction: discord.Interaction):
            try:
                await interaction.response.send_modal(HelpSearchModal(self))
            except Exception:
                try:
                    await interaction.followup.send("Could not open search.", ephemeral=True)
                except Exception:
                    pass

        prev_button.callback = prev_cb
        next_button.callback = next_cb
        search_button.callback = search_cb
        self.add_item(discord.ui.ActionRow(prev_button, next_button, search_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != int(self.user_id):
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("This help menu is only for the original user.", ephemeral=True)
            return False
        return True


@bot.tree.command(name="ping", description="Check the bot's latency")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def ping(interaction: discord.Interaction):
    start_time = time.perf_counter()
    await interaction.response.defer()

    ws_latency = round(bot.latency * 1000)
    end_time = time.perf_counter()
    api_latency = round((end_time - start_time) * 1000)

    await interaction.edit_original_response(
        content=f"🏓 Pong! - **WebSocket:** {ws_latency}ms - **API Round-Trip:** {api_latency}ms",
        allowed_mentions=discord.AllowedMentions.none()
    )


@bot.tree.command(name="slot-classic", description="Spin the slot machine!")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def slot(interaction: discord.Interaction):
    emojis = ['🍒', '🍎', '🍇', '💎', '<:bell:1517497562184024275>', '🍋']
    await interaction.response.defer(); await interaction.followup.send("🎰 **Spinning...**")
    for _ in range(3):
        e1, e2, e3 = (random.choice(emojis) for _ in range(3))
        await interaction.edit_original_response(content=f"🎰 | {e1} | {e2} | {e3} |")
        await asyncio.sleep(0.5)
    final_e1, final_e2, final_e3 = (random.choice(emojis) for _ in range(3))
    if final_e1 == final_e2 == final_e3:
        result_msg = f"🎰 **JACKPOT!** You won!\n\n| {final_e1} | {final_e2} | {final_e3} |"
    else:
        result_msg = f"🎰 Slot Machine:\n\n| {final_e1} | {final_e2} | {final_e3} |\n\nBetter luck next time!"
    await interaction.edit_original_response(content=result_msg)


@bot.tree.command(name="coinflip-classic", description="Flips a coin and shows Heads or Tails")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    await interaction.response.defer(); await interaction.followup.send(f"<:coin:1518351100783231138> The coin landed on: **{result}**!")


@bot.tree.command(name="avatar", description="Get the profile picture of a user")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@app_commands.describe(user="The user to get the avatar from")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user.name}'s Avatar", color=discord.Color.blue())
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="banner", description="Get the profile banner of a user")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@app_commands.describe(user="The user to get the banner from")
@app_commands.choices(kind=[
    app_commands.Choice(name="User banner", value="user"),
    app_commands.Choice(name="Welcome preview", value="welcome"),
    app_commands.Choice(name="Goodbye preview", value="goodbye"),
    app_commands.Choice(name="Levelup preview", value="level"),
    app_commands.Choice(name="Quest preview", value="quest"),
])
@app_commands.describe(kind="Optional: preview type to generate")
async def banner(interaction: discord.Interaction, user: discord.Member = None, kind: str = "user"):
    user = user or interaction.user
                                                                  
    kind = (kind or "user").lower()
    if kind == "user":
        full_user = await bot.fetch_user(user.id)
        if full_user.banner:
            embed = discord.Embed(title=f"{user.name}'s Banner", color=discord.Color.blue())
            embed.set_image(url=full_user.banner.url)
            await interaction.response.defer(); await interaction.followup.send(embed=embed)
            return
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"{user.name} does not have a banner.", ephemeral=True)
            return

                                                                         
    try:
        file = await create_banner_preview(user, kind)
        if file:
            await interaction.response.defer(); await interaction.followup.send(file=file)
            return
    except Exception:
        pass

    await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"Unable to generate {kind} banner preview for {user.display_name}.", ephemeral=True)


@bot.tree.command(name="emoji", description="Get the image for a custom emoji")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(emoji="The custom emoji to get the image from")
async def emoji(interaction: discord.Interaction, emoji: str):
    if not emoji:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide a valid custom emoji.", ephemeral=True)
    try:
        emoji_obj = discord.PartialEmoji.from_str(emoji)
    except Exception:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide a valid custom emoji.", ephemeral=True)
    if not emoji_obj.id:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide a valid custom emoji.", ephemeral=True)
    embed = discord.Embed(title=f"Emoji: {emoji_obj.name}", color=discord.Color.blue())
    embed.set_image(url=emoji_obj.url)
    await interaction.response.defer(); await interaction.followup.send(embed=embed)




# -------------------------------------------------------------------------------------------------------------
#                                               Admin Commands
# -------------------------------------------------------------------------------------------------------------





@bot.tree.command(name="voice-move_adm", description="Move everyone in your current voice channel to another voice channel")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(move_members=True)
@app_commands.describe(
    channel="Target voice channel to move everyone into"
)
async def adm_voice_move(interaction: discord.Interaction, channel: discord.VoiceChannel):
    member = interaction.user
    if not isinstance(member, discord.Member):
        member = interaction.guild.get_member(interaction.user.id)

    if not member or not member.voice or not member.voice.channel:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You must be connected to a voice channel to use this command.", ephemeral=True)
        return

    source_channel = member.voice.channel
    if source_channel.id == channel.id:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> You are already in the target voice channel.", ephemeral=True)
        return

    moved_members = []
    failed_members = []
    for target_member in list(source_channel.members):
        try:
            await target_member.move_to(channel, reason=f"Voice move initiated by {interaction.user}")
            moved_members.append(target_member.display_name)
        except Exception as e:
            failed_members.append(f"{target_member.display_name}: {e}")

    embed = discord.Embed(
        title="Voice Move Complete",
        description=f"Moved {len(moved_members)} user(s) from **{source_channel.name}** to **{channel.name}**.",
        color=discord.Color.blurple()
    )
    if moved_members:
        embed.add_field(name="Moved", value="\n".join(moved_members[:25]), inline=False)
    if failed_members:
        embed.add_field(name="Failed", value="\n".join(failed_members[:25]), inline=False)
    embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="rename_adm", description="Rename a user or reset their nickname")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_nicknames=True)
@app_commands.describe(
    user="The member you want to rename",
    name="The new nickname (leave empty to reset to original name)"
)
async def rename(interaction: discord.Interaction, user: discord.Member, name: str = None):
    if interaction.guild.me.top_role <= user.top_role:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I cannot rename this user. Their role is higher than or equal to mine!", ephemeral=True)
        return
    try:
        old_name = user.display_name
        await user.edit(nick=name)
        if name:
            await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Changed **{old_name}**'s nickname to **{name}**.")
        else:
            await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Reset **{old_name}**'s nickname to their original username.")
    except discord.Forbidden:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have the 'Manage Nicknames' permission or the user is the Server Owner.", ephemeral=True)
    except Exception as e:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)


@bot.tree.command(name="purge-nuke_adm", description="Fully clear a channel")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_channels=True)
async def nuke(interaction: discord.Interaction, archive: bool = False):
    try:
        channel = await interaction.guild.fetch_channel(interaction.channel_id)
    except discord.Forbidden:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I cannot 'see' this channel. Please check my permissions in this specific channel's settings.", ephemeral=True)
        return

    GIF_URL = "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExN2x1ZW82ZGdlZzV1MTFzNGF6ajJzZ3Bmc3I2MDlxaXp0cWpkcTY4YyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/fXhYwggfsp3yHBsdlr/giphy.gif"

    await interaction.response.defer(); await interaction.followup.send("<:explosive:1517578642723573880> Target locked. Nuking...", ephemeral=False)
    new_channel = await channel.clone(reason=f"Nuke by {interaction.user}")
    await new_channel.edit(position=channel.position)

    embed = discord.Embed(
        title="<:nuke:1517497573986926732> Channel Nuked",
        description=f"This is {format_user_reference(interaction.user)}'s fault, THEY DID THIS",
        color=discord.Color.red()
    )
    embed.set_image(url=GIF_URL)
    try:
        await new_channel.send(embed=embed)
    except discord.Forbidden as error:
        add_bot_error_entry(interaction.guild.id, new_channel.id, interaction.user, "nuke result message", error)

    try:
        if archive:
            everyone_role = interaction.guild.default_role
            await channel.edit(
                name=f"{channel.name}-archived",
                overwrites={everyone_role: discord.PermissionOverwrite(view_channel=False)},
                reason="Channel Archived via Nuke"
            )
        else:
            await channel.delete(reason="Nuked")
    except discord.Forbidden:
        try:
            await new_channel.send("<:warning:1517452174991556758> **Warning:** I couldn't delete or hide the old channel. Check if my role is high enough!")
        except discord.Forbidden as error:
            add_bot_error_entry(interaction.guild.id, new_channel.id, interaction.user, "nuke cleanup warning", error)
    except Exception as e:
        print(f"Error during nuke cleanup: {e}")


@bot.tree.command(name="purge_adm", description="Mass delete messages from the channel")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_messages=True)
@app_commands.describe(
    amount="Number of messages to delete",
    user="Optional: Only delete messages from this specific user"
)
async def purge(interaction: discord.Interaction, amount: int, user: discord.Member = None):
    if amount <= 0:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please specify a number greater than 0.", ephemeral=True)
        return
    if amount > 100:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:warning:1517452174991556758> For safety, you can only purge up to 100 messages at a time.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    def is_user(m):
        return m.author == user if user else True

    try:
        deleted = await interaction.channel.purge(
            limit=amount,
            check=is_user,
            before=interaction.created_at,
            reason=f"Purged by {interaction.user} via bot"
        )
        user_str = f" from {format_user_reference(user)}" if user else ""
        await interaction.followup.send(f"<:explosive:1517578642723573880> Successfully deleted **{len(deleted)}** messages{user_str}.", ephemeral=False)
    except Exception as e:
        await interaction.followup.send(f"<:disapprove:1517452151012589662> Failed to purge messages. Error: {e}", ephemeral=True)


def resolve_member_from_input(guild: discord.Guild, member_input: str | discord.Member | discord.User | None) -> discord.Member | None:
    if not guild:
        return None

    if isinstance(member_input, discord.Member):
        return member_input

    if isinstance(member_input, discord.User):
        return guild.get_member(member_input.id)

    if not member_input:
        return None

    value = str(member_input).strip()
    if not value:
        return None

    if value.startswith("<@") and value.endswith(">"):
        value = value[2:-1].lstrip("!")

    if value.isdigit():
        return guild.get_member(int(value))

    return guild.get_member_named(value) or discord.utils.find(
        lambda member: member.name.lower() == value.lower() or member.display_name.lower() == value.lower(),
        guild.members,
    )


@bot.tree.command(name="timeout_adm", description="Timeout a member for a specific duration")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(moderate_members=True)
@app_commands.describe(
    member="The username, mention, or ID of the member to timeout",
    days="Number of days",
    hours="Number of hours",
    minutes="Number of minutes",
    seconds="Number of seconds",
    reason="Why is this user being timed out?"
)
async def timeout(interaction: discord.Interaction, member: discord.Member | None = None, days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0, reason: str = "No reason provided"):
    duration = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    if duration.total_seconds() <= 0:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You must specify a duration greater than 0!", ephemeral=True)
        return
    if duration.total_seconds() > 2419200:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Timeout cannot exceed 28 days.", ephemeral=True)
        return

    target_member = resolve_member_from_input(interaction.guild, member)
    if target_member is None:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't find that user in this server.", ephemeral=True)
        return

    if target_member == interaction.user:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot timeout yourself.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and interaction.user != target_member and target_member.top_role >= interaction.user.top_role:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot timeout someone with an equal or higher role than yours.", ephemeral=True)
        return

    time_str = f"{days}d {hours}h {minutes}m {seconds}s"
    if not target_member.bot:
        try:
            dm_embed = discord.Embed(
                title="<:hourglass:1517574046252924938> You have been timed out",
                description=f"**Server:** {interaction.guild.name}\n**Duration:** {time_str}\n**Reason:** {reason}",
                color=discord.Color.orange()
            )
            await target_member.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    try:
        await target_member.timeout(duration, reason=reason)
        confirm_embed = discord.Embed(
            title="<:approve:1517452125687513158> User Timed Out",
            description=f"**{format_user_reference(target_member)}** has been timed out for {time_str}.",
            color=discord.Color.green()
        )
        confirm_embed.add_field(name="Reason", value=reason)
        await interaction.response.defer(); await interaction.followup.send(embed=confirm_embed)
    except discord.Forbidden:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to timeout this user (Hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)


@bot.tree.command(name="slowmode_adm", description="Set channel slowmode (up to 6 hours)")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_channels=True)
@app_commands.describe(
    seconds="Number of seconds",
    minutes="Number of minutes",
    hours="Number of hours",
    channel="Target channel (optional)"
)
async def slowmode(interaction: discord.Interaction, seconds: int = 0, minutes: int = 0, hours: int = 0, channel: discord.TextChannel | None = None):
    total_seconds = int(seconds or 0) + int(minutes or 0) * 60 + int(hours or 0) * 3600
                                 
    if total_seconds < 0:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid slowmode value.", ephemeral=True)
        return
    if total_seconds > 21600:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Slowmode cannot exceed 6 hours.", ephemeral=True)
        return

    target_channel = channel or (interaction.channel if hasattr(interaction, 'channel') else None)
    if target_channel is None or not isinstance(target_channel, discord.TextChannel):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please run this in a text channel or specify a valid text channel.", ephemeral=True)
        return

    try:
        await target_channel.edit(rate_limit_per_user=total_seconds, reason=f"Set by {interaction.user}")
        if total_seconds == 0:
            desc = f"Disabled slowmode in {target_channel.mention}."
        else:
            desc = f"Set slowmode in {target_channel.mention} to {format_duration(total_seconds)}."
        embed = discord.Embed(title="<:approve:1517452125687513158> Slowmode updated", description=desc, color=discord.Color.green())
        await interaction.response.defer(); await interaction.followup.send(embed=embed)
    except discord.Forbidden:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to edit this channel.", ephemeral=True)
    except Exception as e:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)

@bot.tree.command(name="kick_adm", description="Kick a member from the server")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(kick_members=True)
@app_commands.describe(
    member="The username, mention, or ID of the member to kick",
    reason="Why is this user being kicked?"
)
async def kick(interaction: discord.Interaction, member: discord.Member | None = None, reason: str = "No reason provided"):
    target_member = resolve_member_from_input(interaction.guild, member)
    if target_member is None:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't find that user in this server.", ephemeral=True)
        return

    if target_member == interaction.user:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot kick yourself.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and interaction.user != target_member and target_member.top_role >= interaction.user.top_role:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot kick someone with an equal or higher role than yours.", ephemeral=True)
        return

    if not target_member.bot:
        try:
            dm_embed = discord.Embed(
                title="<:warning:1517452174991556758> You have been kicked",
                description=f"**Server:** {interaction.guild.name}\n**Reason:** {reason}",
                color=discord.Color.orange()
            )
            await target_member.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    try:
        await target_member.kick(reason=reason)
        confirm_embed = discord.Embed(
            title="<:approuve:1517452125687513158> User Kicked",
            description=f"**{format_user_reference(target_member)}** has been kicked from the server.",
            color=discord.Color.green()
        )
        confirm_embed.add_field(name="Reason", value=reason)
        await interaction.response.defer(); await interaction.followup.send(embed=confirm_embed)
    except discord.Forbidden:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to kick this user (Hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)


@bot.tree.command(name="ban_adm", description="Ban a member from the server")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(ban_members=True)
@app_commands.describe(
    member="The username, mention, or ID of the member to ban",
    reason="Why is this user being banned?",
    delete_days="How many days of recent messages to delete (0-7)"
)
async def ban(interaction: discord.Interaction, member: discord.Member | None = None, reason: str = "No reason provided", delete_days: int = 0):
    if delete_days < 0 or delete_days > 7:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Delete days must be between 0 and 7.", ephemeral=True)
        return

    target_member = resolve_member_from_input(interaction.guild, member)
    if target_member is None:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't find that user in this server.", ephemeral=True)
        return

    if target_member == interaction.user:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot ban yourself.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and interaction.user != target_member and target_member.top_role >= interaction.user.top_role:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot ban someone with an equal or higher role than yours.", ephemeral=True)
        return

    if not target_member.bot:
        try:
            dm_embed = discord.Embed(
                title="<:disapprove:1517452151012589662> You have been banned",
                description=f"**Server:** {interaction.guild.name}\n**Reason:** {reason}",
                color=discord.Color.red()
            )
            await target_member.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    try:
        await target_member.ban(reason=reason, delete_message_days=delete_days)
        confirm_embed = discord.Embed(
            title="<:approuve:1517452125687513158> User Banned",
            description=f"**{format_user_reference(target_member)}** has been banned from the server.",
            color=discord.Color.green()
        )
        confirm_embed.add_field(name="Reason", value=reason)
        if delete_days > 0:
            confirm_embed.add_field(name="Deleted Messages", value=f"{delete_days} day(s)", inline=True)
        await interaction.response.defer(); await interaction.followup.send(embed=confirm_embed)
    except discord.Forbidden:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to ban this user (Hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)


@bot.tree.command(name="warn_adm", description="Add or remove a warning for a user")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(moderate_members=True)
@app_commands.describe(
    member="The user to warn or remove a warning from",
    action="Whether to add or remove the warning",
    reason="The warning reason or removal note"
)
@app_commands.choices(action=[app_commands.Choice(name="Add", value="add"), app_commands.Choice(name="Remove", value="remove"), app_commands.Choice(name="Clear", value="clear")])
async def warn_adm(
    interaction: discord.Interaction,
    member: discord.Member,
    action: str,
    reason: str = "No reason provided"
):
    if member == interaction.user:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot warn yourself.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and member.top_role >= interaction.user.top_role:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot manage warnings for someone with an equal or higher role than yours.", ephemeral=True)
        return

    user_warnings, data = get_guild_warnings(str(interaction.guild.id), member.id)

    if action == "add":
        warnings, data = await add_guild_warning(
            str(interaction.guild.id),
            member.id,
            reason,
            moderator_id=interaction.user.id,
            moderator_name=str(interaction.user),
        )

        total = len(warnings)
        sanction_text = await apply_warning_sanctions(member, interaction.guild, total)

        if not member.bot:
            await send_warning_dm(
                member,
                interaction.guild,
                reason,
                total_warnings=total,
                sanction=sanction_text
            )

        confirm_embed = discord.Embed(
            title="<:warning:1517452174991556758> Warning added",
            description=f"**{format_user_reference(member)}** has been warned.",
            color=discord.Color.yellow()
        )
        confirm_embed.add_field(name="Reason", value=reason, inline=False)
        confirm_embed.add_field(name="Total warnings", value=str(total), inline=False)
        if sanction_text:
            confirm_embed.add_field(name="Sanction", value=sanction_text, inline=True)
        await interaction.response.defer(); await interaction.followup.send(embed=confirm_embed)
        return

    if action == "remove":
        if not user_warnings:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> **{format_user_reference(member)}** has no warnings to remove.", ephemeral=True)
            return

        removed = user_warnings.pop()
        save_guild_data(data)

        automod, automod_data = get_guild_automod_config(str(interaction.guild.id))
        sanction_state = automod.setdefault("warning_sanction_state", {})
        sanction_state[str(member.id)] = {"last_applied_warns": len(user_warnings)}
        save_guild_data(automod_data)

        if not member.bot:
            try:
                dm_embed = discord.Embed(
                    title="<:warning:1517452174991556758> A warning has been removed",
                    description=f"**Server:** {interaction.guild.name}\n**Note:** {reason}",
                    color=discord.Color.green()
                )
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        total = len(user_warnings)
        confirm_embed = discord.Embed(
            title="<:warning:1517452174991556758> Warning removed",
            description=f"A warning has been removed from **{format_user_reference(member)}**.",
            color=discord.Color.green()
        )
        confirm_embed.add_field(name="Removed warning reason", value=removed.get("reason", "No reason provided"), inline=False)
        confirm_embed.add_field(name="Note", value=reason, inline=False)
        confirm_embed.add_field(name="Remaining warnings", value=str(total), inline=True)
        await interaction.response.defer(); await interaction.followup.send(embed=confirm_embed)
        return

    if action == "clear":
        if not user_warnings:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> **{format_user_reference(member)}** has no warnings to clear.", ephemeral=True)
            return

        count = len(user_warnings)
        user_warnings.clear()
        save_guild_data(data)

        automod, automod_data = get_guild_automod_config(str(interaction.guild.id))
        sanction_state = automod.setdefault("warning_sanction_state", {})
        sanction_state.pop(str(member.id), None)
        save_guild_data(automod_data)

        if not member.bot:
            try:
                dm_embed = discord.Embed(
                    title="<:warning:1517452174991556758> All warnings cleared",
                    description=f"**Server:** {interaction.guild.name}\n**Note:** {reason}",
                    color=discord.Color.green()
                )
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        confirm_embed = discord.Embed(
            title="<:warning:1517452174991556758> Warnings cleared",
            description=f"All warnings have been cleared from **{format_user_reference(member)}**.",
            color=discord.Color.green()
        )
        confirm_embed.add_field(name="Cleared warnings", value=str(count), inline=True)
        confirm_embed.add_field(name="Note", value=reason, inline=False)
        await interaction.response.defer(); await interaction.followup.send(embed=confirm_embed)
        return

    await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid action. Choose add, remove, or clear.", ephemeral=True)


@bot.tree.command(name="warns_adm", description="Show warnings for a user")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(moderate_members=True)
@app_commands.describe(
    member="The user whose warnings you want to view"
)
async def warns_adm(
    interaction: discord.Interaction,
    member: discord.Member
):
    if member == interaction.user:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot view warnings for yourself with this command.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and member.top_role >= interaction.user.top_role:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot view warnings for someone with an equal or higher role than yours.", ephemeral=True)
        return

    user_warnings, _ = get_guild_warnings(str(interaction.guild.id), member.id)
    if not user_warnings:
        await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> **{format_user_reference(member)}** has no warnings.", ephemeral=False)
        return

    embed = discord.Embed(
        title=f"Warnings for {member.display_name}",
        description=f"Total warnings: **{len(user_warnings)}**",
        color=discord.Color.orange()
    )

    for index, warn_entry in enumerate(user_warnings[-10:], start=max(1, len(user_warnings) - 9)):
        raw_timestamp = warn_entry.get("timestamp")
        timestamp = "Unknown time"
        if raw_timestamp:
            try:
                dt = datetime.fromisoformat(raw_timestamp)
                timestamp = discord.utils.format_dt(dt, style="f")
            except Exception:
                timestamp = raw_timestamp
        reason = warn_entry.get("reason", "No reason provided")
        moderator = warn_entry.get("moderator_name", "Unknown moderator")
        embed.add_field(
            name=f"Warn {index}",
            value=f"**Reason:** {reason}\n**Moderator:** {moderator}\n**Time:** {timestamp}",
            inline=False
        )

    if len(user_warnings) > 10:
        embed.set_footer(text=f"Showing the last 10 of {len(user_warnings)} warnings")

    await interaction.response.defer(); await interaction.followup.send(embed=embed, ephemeral=False)


class WarnsAdminView(discord.ui.View):
    def __init__(self, author_id: int, member: discord.Member, warnings: list[dict], page: int = 0, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.member = member
        self.warnings = warnings
        self.page = page
        self.items_per_page = 10

        self.prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary)
        self.next_button = Button(label="Next", style=discord.ButtonStyle.secondary)
        self.close_button = Button(label="Close", style=discord.ButtonStyle.danger)

        self.prev_button.callback = self.previous_page
        self.next_button.callback = self.next_page
        self.close_button.callback = self.close_view

        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.add_item(self.close_button)
        self.update_buttons()

    def update_buttons(self) -> None:
        total_pages = max(1, (len(self.warnings) + self.items_per_page - 1) // self.items_per_page)
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= total_pages - 1

    def get_page_embed(self) -> discord.Embed:
        total_warnings = len(self.warnings)
        total_pages = max(1, (total_warnings + self.items_per_page - 1) // self.items_per_page)
        page = min(max(self.page, 0), total_pages - 1)
        start = page * self.items_per_page
        end = start + self.items_per_page
        page_warnings = self.warnings[start:end]

        embed = discord.Embed(
            title=f"Warnings for {self.member.display_name}",
            description=f"Total warnings: **{total_warnings}**",
            color=discord.Color.orange()
        )

        for index, warn_entry in enumerate(page_warnings, start=start + 1):
            raw_timestamp = warn_entry.get("timestamp")
            timestamp = "Unknown time"
            if raw_timestamp:
                try:
                    dt = datetime.fromisoformat(raw_timestamp)
                    timestamp = discord.utils.format_dt(dt, style="f")
                except Exception:
                    timestamp = raw_timestamp
            reason = warn_entry.get("reason", "No reason provided")
            moderator = warn_entry.get("moderator_name", "Unknown moderator")
            embed.add_field(
                name=f"Warn {index}",
                value=f"**Reason:** {reason}\n**Moderator:** {moderator}\n**Time:** {timestamp}",
                inline=False
            )

        embed.set_footer(text=f"Page {page + 1}/{total_pages}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589462> Only the command user can navigate these pages.", ephemeral=True)
            return False
        return True

    async def previous_page(self, interaction: discord.Interaction) -> None:
        self.page = max(0, self.page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction) -> None:
        total_pages = max(1, (len(self.warnings) + self.items_per_page - 1) // self.items_per_page)
        self.page = min(total_pages - 1, self.page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    async def close_view(self, interaction: discord.Interaction) -> None:
        self.prev_button.disabled = True
        self.next_button.disabled = True
        self.close_button.disabled = True
        await interaction.response.edit_message(view=self)


@bot.tree.command(name="role_adm", description="Give or remove a role from a user")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    action="Whether to add or remove the role",
    member="The user to update",
    role="The role to add or remove",
    reason="Why this role change is being made"
)
@app_commands.choices(action=[app_commands.Choice(name="Add", value="add"), app_commands.Choice(name="Remove", value="remove")])
async def role_adm(
    interaction: discord.Interaction,
    action: str,
    member: discord.Member,
    role: discord.Role,
    reason: str = "No reason provided",
):
    role_error = validate_role_selection(interaction, role, "role")
    if role_error:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(role_error, ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and interaction.user != member and member.top_role >= interaction.user.top_role:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot modify the roles of someone with an equal or higher role than yours.", ephemeral=True)
        return

    try:
        if action == "add":
            if role in member.roles:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:warning:1517452174991556758> **{format_user_reference(member)}** already has **{role.name}**.", ephemeral=True)
                return
            await member.add_roles(role, reason=f"Role admin by {interaction.user} - {reason}")
            await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Added **{role.name}** to **{format_user_reference(member)}**.", ephemeral=False)
        else:
            if role not in member.roles:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:warning:1517452174991556758> **{format_user_reference(member)}** does not have **{role.name}**.", ephemeral=True)
                return
            await member.remove_roles(role, reason=f"Role admin by {interaction.user} - {reason}")
            await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Removed **{role.name}** from **{format_user_reference(member)}**.", ephemeral=False)
    except discord.Forbidden:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)


@bot.tree.command(name="temp-role_adm", description="Grant or remove a temporary role from a user")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    action="Whether to grant or remove the temporary role",
    member="The user to update",
    role="The temporary role to grant or remove",
    duration="How long the temporary role should last (for example 30m, 2h, 1d)",
    reason="Why this temporary role change is being made"
)
@app_commands.choices(action=[app_commands.Choice(name="Grant", value="grant"), app_commands.Choice(name="Remove", value="remove")])
async def temp_role_adm(
    interaction: discord.Interaction,
    action: str,
    member: discord.Member,
    role: discord.Role,
    duration: str = None,
    reason: str = "No reason provided",
):
    role_error = validate_role_selection(interaction, role, "temporary role")
    if role_error:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(role_error, ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and interaction.user != member and member.top_role >= interaction.user.top_role:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You cannot modify the roles of someone with an equal or higher role than yours.", ephemeral=True)
        return

    if action == "grant":
        if not duration:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide a duration like 30m, 2h, or 1d.", ephemeral=True)
            return

        duration_seconds = parse_duration_to_seconds(duration)
        if duration_seconds is None or duration_seconds <= 0:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide a valid duration like 30m, 2h, or 1d.", ephemeral=True)
            return

        try:
            if role in member.roles:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:warning:1517452174991556758> **{format_user_reference(member)}** already has **{role.name}**.", ephemeral=True)
                return
            await member.add_roles(role, reason=f"Temporary role admin by {interaction.user} - {reason}")
            async def remove_temp_role():
                await asyncio.sleep(duration_seconds)
                try:
                    await member.remove_roles(role, reason=f"Temporary role expired after {duration} (admin command)")
                except (discord.Forbidden, discord.HTTPException):
                    pass

            asyncio.create_task(remove_temp_role())
            await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Granted **{role.name}** to **{format_user_reference(member)}** for {duration}.", ephemeral=False)
        except discord.Forbidden:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).", ephemeral=True)
        except Exception as e:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)
        return

    try:
        if role not in member.roles:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:warning:1517452174991556758> **{format_user_reference(member)}** does not have **{role.name}**.", ephemeral=True)
            return
        await member.remove_roles(role, reason=f"Temporary role admin removal by {interaction.user} - {reason}")
        await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Removed **{role.name}** from **{format_user_reference(member)}**.", ephemeral=False)
    except discord.Forbidden:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)


@bot.tree.command(name="role-for_adm", description="Add or remove a role from all members who have a target role")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    action="Whether to add or remove the role",
    role="The role to add or remove",
    target_role="The role filter; members with this role will be affected (use @everyone for everyone)"
)
@app_commands.choices(action=[app_commands.Choice(name="Add", value="add"), app_commands.Choice(name="Remove", value="remove")])
async def adm_role_for(
    interaction: discord.Interaction,
    action: str,
    role: discord.Role,
    target_role: discord.Role,
):
    role_error = validate_role_selection(interaction, role, "role")
    if role_error:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(role_error, ephemeral=True)
        return

    if role is None or target_role is None:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Both role options are required.", ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    updated = 0
    skipped = 0
    failed = 0
    processed = 0
    stop_progress_updates = asyncio.Event()
    affected_members = []

    if target_role == interaction.guild.default_role:
        if len(interaction.guild.members) < interaction.guild.member_count:
            try:
                await interaction.guild.chunk(cache=True)
            except Exception:
                pass
        affected_members = list(interaction.guild.members)
    else:
        affected_members = list(target_role.members)
        if not affected_members and len(interaction.guild.members) < interaction.guild.member_count:
            try:
                await interaction.guild.chunk(cache=True)
            except Exception:
                pass
            affected_members = [member for member in interaction.guild.members if target_role in member.roles]

    def build_progress_embed() -> discord.Embed:
        progress_percent = (processed / len(affected_members) * 100) if affected_members else 100.0
        action_text = "adding" if action == "add" else "removing"
        embed = discord.Embed(
            title="<:gear:1517576939097952496> Role Update In Progress",
            description=f"{action_text.capitalize()} role **{role.name}** from members with **{target_role.name}**...",
            color=discord.Color.blurple()
        )
        embed.add_field(name="<:list:1517497572770451567> Processed", value=f"{processed}/{len(affected_members)} ({progress_percent:.1f}%)", inline=True)
        embed.add_field(name="<:approuve:1517452125687513158> Updated", value=str(updated), inline=True)
        embed.add_field(name="<:warning:1517452174991556758> Skipped", value=str(skipped), inline=True)
        embed.add_field(name="<:disapprove:1517452151012589662> Failed", value=str(failed), inline=True)
        return embed

    async def update_progress_message(message: discord.Message):
        while not stop_progress_updates.is_set():
            await asyncio.sleep(10)
            if stop_progress_updates.is_set():
                break
            try:
                await message.edit(embed=build_progress_embed())
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                break

    progress_message = await interaction.followup.send(embed=build_progress_embed(), ephemeral=False)
    progress_task = asyncio.create_task(update_progress_message(progress_message))

    if not affected_members:
        stop_progress_updates.set()
        if progress_task and not progress_task.done():
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass
            except Exception as error:
                print(f"Progress task cleanup failed: {error}")
        await progress_message.edit(content=f"<:warning:1517452174991556758> No members with the role **{target_role.name}** were found.", embed=build_progress_embed())
        return

    try:
        for member in affected_members:
            try:
                if action == "add":
                    if role not in member.roles:
                        await member.add_roles(role, reason=f"Role mass update by {interaction.user}")
                        updated += 1
                    else:
                        skipped += 1
                else:
                    if role in member.roles:
                        await member.remove_roles(role, reason=f"Role mass update by {interaction.user}")
                        updated += 1
                    else:
                        skipped += 1
            except discord.Forbidden:
                failed += 1
            except Exception as error:
                failed += 1
                print(f"Error updating role for {member}: {error}")
            finally:
                processed += 1
    finally:
        stop_progress_updates.set()
        if progress_task and not progress_task.done():
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass
            except Exception as error:
                print(f"Progress task cleanup failed: {error}")

    action_text = "added to" if action == "add" else "removed from"
    embed = discord.Embed(
        title="<:gear:1517576939097952496> Role Update Complete",
        description=f"The role **{role.name}** was {action_text} **{target_role.name}** members.",
        color=discord.Color.green() if action == "add" else discord.Color.orange()
    )
    embed.add_field(name="<:graph:1517584522877866065> Affected Members", value=str(len(affected_members)), inline=True)
    embed.add_field(name="<:approuve:1517452125687513158> Updated", value=str(updated), inline=True)
    embed.add_field(name="<:warning:1517452174991556758> Skipped", value=str(skipped), inline=True)
    if failed:
        embed.add_field(name="<:disapprove:1517452151012589662> Failed", value=str(failed), inline=True)

    try:
        await progress_message.edit(content=f"<:approve:1517452125687513158> Finished updating roles.", embed=embed)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        await interaction.followup.send(embed=embed, ephemeral=False)


@bot.tree.command(name="giveaway_adm", description="Create or cancel a giveaway")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    action="Create or cancel a giveaway",
    name="The giveaway title",
    winners="How many winners to select",
    time="How long the giveaway lasts (e.g. 1h, 30m, 2d)",
    role="Optional role to award to winners",
    temp_role="Optional temporary role to award to winners",
    temp_role_time="Temporary role duration in minutes",
    item="Optional item reward",
    money="Optional money reward",
    xp="Optional XP reward"
)
@app_commands.choices(action=[app_commands.Choice(name="Create", value="create"), app_commands.Choice(name="Cancel", value="cancel")])
async def adm_giveaway(
    interaction: discord.Interaction,
    action: str,
    name: str = None,
    winners: int = 1,
    time: str = None,
    role: discord.Role = None,
    temp_role: discord.Role = None,
    temp_role_time: int = 0,
    item: str = None,
    money: int = 0,
    xp: int = 0,
):
    if action == "cancel":
        if not name:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide the giveaway name to cancel.", ephemeral=True)
            return

        data = load_giveaway_data()
        matched = None
        for giveaway_id, giveaway in data.items():
            if str(giveaway.get('guild_id')) == str(interaction.guild_id) and giveaway.get('status') == 'active' and str(giveaway.get('name', '')).lower() == name.lower():
                matched = (giveaway_id, giveaway)
                break

        if not matched:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't find an active giveaway with that name.", ephemeral=True)
            return

        giveaway_id, giveaway = matched
        giveaway['status'] = 'cancelled'
        data.pop(giveaway_id, None)
        save_giveaway_data(data)

        channel = interaction.channel
        if channel and giveaway.get('message_id'):
            try:
                message = await channel.fetch_message(int(giveaway['message_id']))
                view = GiveawayView(giveaway_id, giveaway)
                await message.edit(view=view)
            except Exception:
                pass

        await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Cancelled giveaway **{name}**.")
        return

    if not name:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide a giveaway name.", ephemeral=True)
        return
    if winners <= 0:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Winners must be at least 1.", ephemeral=True)
        return
    if temp_role and temp_role_time <= 0:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Temporary role time must be greater than 0 when using a temp role.", ephemeral=True)
        return

    role_error = validate_role_selection(interaction, role, "role")
    if role_error:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(role_error, ephemeral=True)
        return

    temp_role_error = validate_role_selection(interaction, temp_role, "temporary role")
    if temp_role_error:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(temp_role_error, ephemeral=True)
        return

    duration_seconds = parse_duration_to_seconds(time or "30m")
    if duration_seconds is None or duration_seconds <= 0:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide a valid time like 30m, 1h, or 2d.", ephemeral=True)
        return

    giveaway_data = {
        'name': name,
        'host_id': interaction.user.id,
        'winners_count': winners,
        'entries': [],
        'status': 'active',
        'end_time': int((datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)).timestamp()),
        'guild_id': interaction.guild_id,
        'channel_id': interaction.channel_id,
        'role_id': role.id if role else None,
        'temp_role_id': temp_role.id if temp_role else None,
        'temp_role_time': temp_role_time if temp_role else 0,
        'item': item,
        'money': money,
        'xp': xp,
    }

    view = GiveawayView("placeholder", giveaway_data)
    await interaction.response.defer(); await interaction.followup.send(view=view)
    message = await interaction.original_response()

    giveaway_id = f"{interaction.guild_id}:{interaction.channel_id}:{message.id}"
    giveaway_data['message_id'] = message.id
    data = load_giveaway_data()
    data[giveaway_id] = giveaway_data
    save_giveaway_data(data)

    view = GiveawayView(giveaway_id, giveaway_data)
    try:
        await message.edit(view=view)
    except Exception:
        pass


@bot.command(name="json")
@commands.is_owner()
async def json_cmd(ctx: commands.Context, file: str, target_id: str | None = None):                                                                                  
    try:
        await ctx.trigger_typing()
    except Exception:
        try:
            await ctx.channel.trigger_typing()
        except Exception:
            pass

    kind = (file or "").lower()
    loaders = {
        'giveaway': load_giveaway_data,
        'giveaways': load_giveaway_data,
        'quest': load_quest_data,
        'quests': load_quest_data,
        'data': load_data,
        'economy': load_data,
        'level': load_levels,
        'levels': load_levels,
        'guild': load_guild_data,
        'guilds': load_guild_data,
        'settings': load_user_settings,
        'user': load_user_settings,
    }

    loader = loaders.get(kind)
    if not loader:
        await ctx.send("Unknown file. Valid options: giveaway, quest, data, level, guild, settings")
        return

    try:
        data = loader()
    except Exception as e:
        await ctx.send(f"Failed to load data: {e}")
        return

    if target_id:
        key = str(target_id)
    else:
        if ctx.guild and kind not in {'settings', 'user'}:
            key = str(ctx.guild.id)
        else:
            key = str(ctx.author.id)

    try:
        part = data.get(key) if isinstance(data, dict) else data
    except Exception:
        part = data

    try:
        text = json.dumps(part, indent=2, default=str)
    except Exception:
        text = str(part)

    if len(text) > 1900:
        buf = io.BytesIO(text.encode('utf-8'))
        buf.seek(0)
        await ctx.send(file=discord.File(buf, filename=f"{kind}_{key}.json"))
    else:
                                                   
        await ctx.send(f"```json\n{text}\n```")


# -------------------------------------------------------------------------------------------------------------
#                                               Deleted Edited / Ghost Pings / Error
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="deleted", description="View recently deleted messages and media")
@app_commands.allowed_installs(guilds=True, users=False)
async def deleted(interaction: discord.Interaction, user: discord.Member = None):
    clean_cache()
    guild_config, _ = get_guild_config(str(interaction.guild.id))
    if not guild_config.get("edit_delete_history_enabled", True):
        await interaction.response.defer(); await interaction.followup.send("<:disapprove:1517452151012589662> Deleted message history is disabled for this server.")
        return
    channel_msgs = [m for m in deleted_cache if m['channel'] == interaction.channel_id]
    if user:
        channel_msgs = [m for m in channel_msgs if m['author'].id == user.id]
    channel_msgs = channel_msgs[-10:]
    if not channel_msgs:
        await interaction.response.defer(); await interaction.followup.send("No deleted messages found in this channel recently.")
        return

    description_lines = []
    attachment_messages = []

    for m in channel_msgs:
        has_attachment = bool(m.get('attachment_url'))
        attachment_indicator = "<:image:1517497571470348539> " if has_attachment else ""
        if has_attachment:
            attachment_messages.append(m)
        content_text = m.get('content') if m.get('content') else "*[Attachment or Embed]*"
        description_lines.append(f"{attachment_indicator}**{m['author'].display_name}**: {content_text}\n-# Sent at {discord_timestamp(m['created_at'])}")

    full_description = "\n\n".join(description_lines)

    if attachment_messages:
        attachment_messages = attachment_messages[-3:]
        attachment_messages.sort(key=lambda x: x['time'], reverse=True)
        view = DeletedMessagesView(full_description, attachment_messages, interaction.user)
        await interaction.response.defer(); await interaction.followup.send(view=view)
        view.message = await interaction.original_response()
    else:
        view = V2InfoContainerView(
            "<:trash:1517497581058527404> Recent deleted messages:",
            full_description,
            discord.Color.red(),
        )
        await interaction.response.defer(); await interaction.followup.send(view=view)


@bot.tree.command(name="edited", description="Show recently edited messages in this channel")
@app_commands.describe(user="Optional: Only show edited messages from a specific user")
@app_commands.allowed_installs(guilds=True, users=False)
async def edited_command(interaction: discord.Interaction, user: discord.Member = None):
    global edited_cache
    clean_cache()
    guild_config, _ = get_guild_config(str(interaction.guild.id))
    if not guild_config.get("edit_delete_history_enabled", True):
        await interaction.response.defer(); await interaction.followup.send("<:disapprove:1517452151012589662> Edited message history is disabled for this server.")
        return

    channel_edited = [m for m in edited_cache if m['channel'] == interaction.channel_id]

    if user:
        channel_edited = [m for m in channel_edited if m['author_id'] == user.id]
    channel_edited = channel_edited[-10:]

    if not channel_edited:
        await interaction.response.defer(); await interaction.followup.send("No messages have been edited in this channel recently.")
        return

    text_layout = ""
    for msg in channel_edited[:10]:
        text_layout += f"**{msg['author'].display_name}**: ~~{msg['old_content']}~~ ➔ {msg['new_content']}\n-# Edited at {discord_timestamp(msg['edited_at'])} | [Jump to Message]({msg['jump_url']})\n\n"

    title_text = "<:edit:1517497568421085256> Recently Edited Messages"

    view = V2InfoContainerView(
        title_text,
        text_layout,
        discord.Color.orange(),
    )
    await interaction.response.defer(); await interaction.followup.send(view=view)


@bot.tree.command(name="where-ping", description="Show where a user has been pinged recently")
@app_commands.describe(user="The user to look up")
@app_commands.allowed_installs(guilds=True, users=False)
async def where_ping(interaction: discord.Interaction, user: discord.Member = None):
    clean_cache()
    target_user = user or interaction.user
    entries = []
    for entry in where_ping_cache:
        if entry.get('guild_id') != interaction.guild_id:
            continue
        if entry.get('mention_type') == 'user' and entry.get('mention_id') == target_user.id:
            entries.append(entry)
        elif entry.get('mention_type') == 'role' and isinstance(target_user, discord.Member):
            if target_user.get_role(entry.get('mention_id')) is not None:
                entries.append(entry)
    entries.sort(key=lambda entry: entry['time'], reverse=True)
    entries = entries[-10:]

    if not entries:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"No recent ping history was found for {target_user.display_name}.", ephemeral=True)
        return

    view = WherePingView(entries, target_user)
    await interaction.response.defer(ephemeral=True); await interaction.followup.send(view=view, ephemeral=True)


@bot.tree.command(name="errors", description="Show recent bot errors in this server")
@app_commands.allowed_installs(guilds=True, users=False)
async def errors(interaction: discord.Interaction):
    clean_cache()

    guild_errors = [entry for entry in bot_error_cache if entry.get("guild_id") == interaction.guild_id]
    if not guild_errors:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("No bot errors have been recorded for this server recently.", ephemeral=True)
        return

    recent_errors = list(reversed(guild_errors[-25:]))
    description_lines = []

    for entry in recent_errors:
        channel_id = entry.get("channel_id")
        if channel_id:
            channel_text = f"<#{channel_id}>"
        else:
            channel_text = "Unknown channel"

        user_obj = entry.get("user")
        user_text = getattr(user_obj, "display_name", getattr(user_obj, "name", "Unknown user"))
        error_message = entry.get("error_message", "No error message provided")
        if len(error_message) > 180:
            error_message = error_message[:177] + "..."

        description_lines.append(
            f"**{entry.get('command_name', 'unknown command')}** in {channel_text} by {user_text}\n"
            f"-# {entry.get('error_type', 'Error')}: {error_message}\n"
            f"-# At {discord_timestamp(entry['time'])}"
        )

    view = V2InfoContainerView(
        "<:warning:1517452174991556758> Recent Bot Errors",
        f"Showing latest {len(recent_errors)} of {len(guild_errors)} error(s).\n\n" + "\n\n".join(description_lines),
        discord.Color.red(),
    )
    await interaction.response.defer(ephemeral=True); await interaction.followup.send(view=view, ephemeral=True)


@bot.tree.command(name="forget", description="Clear your messages from the bot's memory")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
async def forget(interaction: discord.Interaction):
    clean_cache()
    global message_cache, deleted_cache, edited_cache, where_ping_cache
    
    message_cache = [m for m in message_cache if m['author'].id != interaction.user.id]
    deleted_cache = [m for m in deleted_cache if m['author'].id != interaction.user.id]
    edited_cache = [m for m in edited_cache if m['author'].id != interaction.user.id]
    where_ping_cache = [entry for entry in where_ping_cache if entry.get('mention', None) and entry['mention'].id != interaction.user.id]
    
    await interaction.response.defer(ephemeral=True); await interaction.followup.send("I've wiped your messages, edits, media, and ping history from my memory!", ephemeral=True)


@bot.tree.command(name="forget_adm", description="Clear edited and deleted history of a chosen user")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@app_commands.default_permissions(manage_messages=True)
async def adm_forget(interaction: discord.Interaction, user: discord.Member):
    clean_cache()
    global message_cache, deleted_cache, edited_cache, where_ping_cache
    message_cache = [m for m in message_cache if m['author'].id != user.id]
    deleted_cache = [m for m in deleted_cache if m['author'].id != user.id]
    edited_cache = [m for m in edited_cache if m['author'].id != user.id]
    where_ping_cache = [entry for entry in where_ping_cache if entry.get('mention', None) and entry['mention'].id != user.id]
    await interaction.response.defer(); await interaction.followup.send(
        f"Cleared deleted, edited, and ping history for {user.display_name}."
    )




# -------------------------------------------------------------------------------------------------------------
#                                               Counter command, its alone now ]: poor thing 😭 all his friends moved to /settings 😭😭😭
# -------------------------------------------------------------------------------------------------------------





@bot.tree.command(name="counter-number-set", description="Set the current count in a counter channel")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    channel="The counter channel to update",
    value="The new current count value"
)
async def counter_number_set(interaction: discord.Interaction, channel: discord.TextChannel, value: int):
    success = set_counter_value(str(interaction.guild.id), channel.id, value)
    if success:
        await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Counter in {channel.mention} is now set to {value}.", ephemeral=False)
    else:
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:warning:1517452174991556758> That channel does not have an active counter.", ephemeral=True)




# -------------------------------------------------------------------------------------------------------------
#                                               Board Commands
# -------------------------------------------------------------------------------------------------------------






# -------------------------------------------------------------------------------------------------------------
#                                               Lock Commands
# -------------------------------------------------------------------------------------------------------------




@bot.event
async def on_guild_channel_delete(channel):
    changed = False

    if channel.id in locked_channels:
        locked_channels.pop(channel.id)
        changed = True

    if channel.id in admin_log_channels:
        admin_log_channels.pop(channel.id)
        changed = True

    if changed:
        save_lock_config(locked_channels, admin_log_channels)




# -------------------------------------------------------------------------------------------------------------
#                                               Welcome/Goodbye Commands
# -------------------------------------------------------------------------------------------------------------




async def create_welcome_card(member):
    base_path = os.path.dirname(__file__)
    style = ensure_user_banner_assigned(str(member.id))
    bg_path = get_banner_asset_path("welcome_bg", style)
    font_path = resolve_font_path(base_path)

    if not bg_path or not os.path.exists(bg_path):
        print(f"Background not found at: {bg_path}")
        return None

    background, entry = assemble_banner_image(bg_path, style)
                                                          
    background = apply_named_overlay(background, "welcome_mg.png")
    avatar_bytes = await member.display_avatar.with_format("png").read()

    with Image.open(io.BytesIO(avatar_bytes)) as avatar:
        avatar = avatar.convert("RGBA").resize((160, 160))
        background.paste(avatar, (480, 40))

    draw = ImageDraw.Draw(background)
    try:
        font_big = ImageFont.truetype(font_path, 35)
        font_small = ImageFont.truetype(font_path, 15)
        font_medium = ImageFont.truetype(font_path, 25)
    except Exception as e:
        print(f"Font error: {e}. Using default.")
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()

    text_color = pick_text_color(entry, background)
    stroke_color = get_opposite_color(text_color)
    gray_color = tuple(max(0, min(255, int(c * 0.8))) for c in text_color)
    draw.text((35, 30), f"Welcome", fill=text_color, font=font_big, stroke_fill=stroke_color, stroke_width=2)
    draw.text((35, 80), format_banner_username(get_banner_name(member), 25), fill=text_color, font=font_medium, stroke_fill=stroke_color, stroke_width=2)
    guild = getattr(member, 'guild', None)
    guild_name = format_banner_limit_text((getattr(guild, 'name', None) or "DM") if guild is not None else "DM", 35)
    draw.text((35, 140), f"to the {guild_name} server", fill=gray_color, font=font_small, stroke_fill=get_opposite_color(gray_color), stroke_width=1)

    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="welcome.png")


async def create_goodbye_card(member):
    base_path = os.path.dirname(__file__)
    style = ensure_user_banner_assigned(str(member.id))
    bg_path = get_banner_asset_path("goodbye_bg", style)
    if not bg_path:
        bg_path = get_banner_asset_path("welcome_bg", style)
    font_path = resolve_font_path(base_path)

    if not bg_path or not os.path.exists(bg_path):
        print(f"Goodbye background not found at: {bg_path}")
        return None

    background, entry = assemble_banner_image(bg_path, style)
    background = apply_named_overlay(background, "welcome_mg.png")
    avatar_bytes = await member.display_avatar.with_format("png").read()

    with Image.open(io.BytesIO(avatar_bytes)) as avatar:
        avatar = avatar.convert("RGBA").resize((160, 160))
        background.paste(avatar, (480, 40))

    draw = ImageDraw.Draw(background)
    try:
        font_big = ImageFont.truetype(font_path, 35)
        font_small = ImageFont.truetype(font_path, 15)
        font_medium = ImageFont.truetype(font_path, 25)
    except Exception as e:
        print(f"Font error: {e}. Using default.")
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()

    text_color = pick_text_color(entry, background)
    stroke_color = get_opposite_color(text_color)
    gray_color = tuple(max(0, min(255, int(c * 0.8))) for c in text_color)
    draw.text((35, 30), "Goodbye", fill=text_color, font=font_big, stroke_fill=stroke_color, stroke_width=2)
    draw.text((35, 80), format_banner_username(get_banner_name(member), 25), fill=text_color, font=font_medium, stroke_fill=stroke_color, stroke_width=2)
    guild = getattr(member, 'guild', None)
    guild_name = format_banner_limit_text((getattr(guild, 'name', None) or "DM") if guild is not None else "DM", 35)
    draw.text((35, 140), f"from {guild_name}", fill=gray_color, font=font_small, stroke_fill=get_opposite_color(gray_color), stroke_width=1)
    draw.text((35, 170), "We hope to see you again soon!", fill=gray_color, font=font_small, stroke_fill=get_opposite_color(gray_color), stroke_width=1)

    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="goodbye.png")


async def create_banner_preview(member: discord.Member, kind: str = "welcome", style_override: str | None = None, quest_text: str | None = None):
    kind_name = str(kind or "welcome").lower()
    if kind_name in {"lvl", "level", "levelup"}:
        style_name = normalize_banner_style(style_override or get_user_banner_style(str(member.id)))
        bg_path = get_banner_asset_path("levelup_bg", style_name)
        if not bg_path or not os.path.exists(bg_path):
            return None

        background, entry = assemble_banner_image(bg_path, style_name)
                                             
        background = apply_named_overlay(background, "levelup_mg.png")
        avatar_bytes = await member.display_avatar.with_format("png").read()
        bg_width = background.width
        center_x = bg_width // 2

        with Image.open(io.BytesIO(avatar_bytes)) as avatar:
            avatar = avatar.convert("RGBA").resize((120, 120))
            background.paste(avatar, (center_x - 60, 40))

        draw = ImageDraw.Draw(background)
        font_path = resolve_font_path(os.path.dirname(__file__))
        try:
            font = ImageFont.truetype(font_path, 25)
        except Exception:
            font = ImageFont.load_default()

        text_color = pick_text_color(entry, background)
        stroke_color = get_opposite_color(text_color)
        draw.text((center_x, 190), f"{format_banner_username(get_banner_name(member))} you are now Level 1!", fill=text_color, font=font, anchor="mm", stroke_fill=stroke_color, stroke_width=2)
        buffer = io.BytesIO()
        background.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename="banner_level_preview.png")

    if kind_name in {"quest", "quest_bg"}:
        style_name = normalize_banner_style(style_override or get_user_banner_style(str(member.id)))
        bg_path = get_banner_asset_path("quest_bg", style_name)
        if not bg_path or not os.path.exists(bg_path):
            return None

        background, entry = assemble_banner_image(bg_path, style_name)
                                           
        background = apply_named_overlay(background, "quest_mg.png")
        avatar_bytes = await member.display_avatar.with_format("png").read()
                                                                                       
                                                                                             
        with Image.open(io.BytesIO(avatar_bytes)) as avatar:
                                                                                
            avatar_size = 100
            avatar = avatar.convert("RGBA").resize((avatar_size, avatar_size))
                                                                           
            avatar_x = max(480, background.width - avatar_size - 40)
            avatar_y = 40
            background.paste(avatar, (avatar_x, avatar_y))

        draw = ImageDraw.Draw(background)
        font_path = resolve_font_path(os.path.dirname(__file__))
        try:
            font_big = ImageFont.truetype(font_path, 32)
            font_medium = ImageFont.truetype(font_path, 18)
            font_small = ImageFont.truetype(font_path, 14)
        except Exception:
            font_big = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()

                                                                           
        center_y = background.height // 2
        title_y = center_y - 40
        username_y = center_y + 2
        bottom_text_y = background.height - 44

        text_color = pick_text_color(entry, background)
        stroke_color = get_opposite_color(text_color)
        gray_color = tuple(max(0, min(255, int(c * 0.8))) for c in text_color)
        draw.text((35, title_y), "Quest Complete!", fill=text_color, font=font_big, stroke_fill=stroke_color, stroke_width=2)
        draw.text((35, username_y), format_banner_username(get_banner_name(member), 22), fill=text_color, font=font_medium, stroke_fill=stroke_color, stroke_width=2)
                                                                              
                                                                                        
        quest_line = quest_text if quest_text else "You completed: <quest description>"
                        
        max_width = background.width - 80
        wrapped = wrap_text(quest_line, draw, font_small, max_width)
        for i, line in enumerate(wrapped[-2:]):
            draw.text((35, bottom_text_y + (i * 18)), line, fill=(200, 200, 200), font=font_small)
        buffer = io.BytesIO()
        background.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename="banner_quest_preview.png")

    if kind_name == "goodbye":
        style_name = normalize_banner_style(style_override or get_user_banner_style(str(member.id)))
        bg_path = get_banner_asset_path("goodbye_bg", style_name)
        if not bg_path or not os.path.exists(bg_path):
            bg_path = get_banner_asset_path("welcome_bg", style_name)
        if not bg_path or not os.path.exists(bg_path):
            return None

        background, entry = assemble_banner_image(bg_path, style_name)
                                                      
        background = apply_named_overlay(background, "welcome_mg.png")
        avatar_bytes = await member.display_avatar.with_format("png").read()

        with Image.open(io.BytesIO(avatar_bytes)) as avatar:
            avatar = avatar.convert("RGBA").resize((160, 160))
            background.paste(avatar, (480, 40))

        draw = ImageDraw.Draw(background)
        font_path = resolve_font_path(os.path.dirname(__file__))
        try:
            font_big = ImageFont.truetype(font_path, 35)
            font_small = ImageFont.truetype(font_path, 15)
            font_medium = ImageFont.truetype(font_path, 25)
        except Exception:
            font_big = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_medium = ImageFont.load_default()

        text_color = pick_text_color(entry, background)
        stroke_color = get_opposite_color(text_color)
        gray_color = tuple(max(0, min(255, int(c * 0.8))) for c in text_color)
        draw.text((35, 30), "Goodbye", fill=text_color, font=font_big, stroke_fill=stroke_color, stroke_width=2)
        draw.text((35, 80), format_banner_username(get_banner_name(member), 25), fill=text_color, font=font_medium, stroke_fill=stroke_color, stroke_width=2)
        guild = getattr(member, 'guild', None)
        guild_name = format_banner_limit_text((getattr(guild, 'name', None) or "DM") if guild is not None else "DM", 35)
        draw.text((35, 140), f"from {guild_name}", fill=gray_color, font=font_small, stroke_fill=get_opposite_color(gray_color), stroke_width=1)
        draw.text((35, 170), "We hope to see you again soon!", fill=gray_color, font=font_small, stroke_fill=get_opposite_color(gray_color), stroke_width=1)
        buffer = io.BytesIO()
        background.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename="banner_goodbye_preview.png")

    style_name = normalize_banner_style(style_override or get_user_banner_style(str(member.id)))
    bg_path = get_banner_asset_path("welcome_bg", style_name)
    if not bg_path or not os.path.exists(bg_path):
        return None

    background, entry = assemble_banner_image(bg_path, style_name)
                                  
    background = apply_named_overlay(background, "welcome_mg.png")
    avatar_bytes = await member.display_avatar.with_format("png").read()

    with Image.open(io.BytesIO(avatar_bytes)) as avatar:
        avatar = avatar.convert("RGBA").resize((160, 160))
        background.paste(avatar, (480, 40))

    draw = ImageDraw.Draw(background)
    font_path = resolve_font_path(os.path.dirname(__file__))
    try:
        font_big = ImageFont.truetype(font_path, 35)
        font_small = ImageFont.truetype(font_path, 15)
        font_medium = ImageFont.truetype(font_path, 25)
    except Exception:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()

    text_color = pick_text_color(entry, background)
    stroke_color = get_opposite_color(text_color)
    gray_color = tuple(max(0, min(255, int(c * 0.8))) for c in text_color)
    draw.text((35, 30), f"Welcome", fill=text_color, font=font_big, stroke_fill=stroke_color, stroke_width=2)
    draw.text((35, 80), format_banner_username(get_banner_name(member), 25), fill=text_color, font=font_medium, stroke_fill=stroke_color, stroke_width=2)
    guild = getattr(member, 'guild', None)
    guild_name = format_banner_limit_text((getattr(guild, 'name', None) or "DM") if guild is not None else "DM", 35)
    draw.text((35, 140), f"to the {guild_name} server", fill=gray_color, font=font_small, stroke_fill=get_opposite_color(gray_color), stroke_width=1)
    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="banner_welcome_preview.png")


def is_emoji_character(char: str) -> bool:
    if not char:
        return False

    codepoint = ord(char)
    if codepoint in {0x200D, 0xFE0F}:
        return True

    return (
        0x1F300 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
        or 0x1F1E6 <= codepoint <= 0x1F1FF
    )


def can_render_glyph(font: ImageFont.ImageFont, char: str) -> bool:
    if not font or not char:
        return False

    try:
        test_image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        test_draw = ImageDraw.Draw(test_image)
        test_draw.text((8, 8), char, fill=(255, 255, 255), font=font)
        return test_image.getbbox() is not None
    except Exception:
        return False


def find_font_file(base_path: str, filename_hint: str | None = None, text: str | None = None) -> str | None:
    fonts_dir = os.path.join(base_path, "fonts")
    roots = []
    if filename_hint:
        roots.extend([
            os.path.join(base_path, filename_hint),
            os.path.join(fonts_dir, filename_hint),
        ])
    roots.append(fonts_dir)
    roots.append(base_path)

    seen = set()
    preferred_paths: list[str] = []
    fallback_paths: list[str] = []

    for root in roots:
        if not root or root in seen:
            continue
        seen.add(root)
        if os.path.isfile(root):
            if filename_hint and os.path.basename(root).lower() != filename_hint.lower():
                continue
            preferred_paths.append(root)
            continue

        if not os.path.isdir(root):
            continue

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            filenames.sort()
            for name in filenames:
                if not name.lower().endswith((".ttf", ".ttc")):
                    continue
                full_path = os.path.join(dirpath, name)
                if full_path in seen:
                    continue
                seen.add(full_path)
                if filename_hint and name.lower() != filename_hint.lower():
                    continue
                if "notosans" in full_path.lower():
                    preferred_paths.append(full_path)
                else:
                    fallback_paths.append(full_path)

    for candidate in preferred_paths + fallback_paths:
        if not os.path.exists(candidate):
            continue
        try:
            font = ImageFont.truetype(candidate, 12)
            if text:
                characters_to_test = [char for char in text if ord(char) > 127 and not is_emoji_character(char)]
                if characters_to_test and any(can_render_glyph(font, char) for char in characters_to_test):
                    return candidate
            else:
                return candidate
        except Exception:
            continue

    return None


def resolve_font_path(base_path: str, preferred_names: tuple[str, ...] = ("Minecraft.ttf", "NotoSans-Regular.ttf", "NotoSansMono-Regular.ttf")) -> str | None:
    for name in preferred_names:
        font_path = find_font_file(base_path, name)
        if font_path:
            return font_path
    return find_font_file(base_path)


def load_emoji_font(base_path: str, size: int, fallback_font: ImageFont.ImageFont | None = None) -> ImageFont.ImageFont | None:
    candidate_paths = [
        os.path.join(base_path, "NotoEmoji.ttf"),
        find_font_file(base_path, "NotoEmoji.ttf"),
    ]

    for font_path in candidate_paths:
        if not font_path or not os.path.exists(font_path):
            continue
        try:
            font = ImageFont.truetype(font_path, size)
            if can_render_glyph(font, "😀"):
                return font
        except Exception:
            continue

    return fallback_font


def load_text_font(base_path: str, text: str, size: int, fallback_font: ImageFont.ImageFont | None = None) -> ImageFont.ImageFont | None:
    if not text:
        return fallback_font

    font_path = find_font_file(base_path)
    if not font_path:
        return fallback_font

    try:
        font = ImageFont.truetype(font_path, size)
        if any(ord(char) > 127 and not is_emoji_character(char) for char in text):
            if can_render_glyph(font, text[0]):
                return font
        return fallback_font
    except Exception:
        return fallback_font


def measure_text_width(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, emoji_font: ImageFont.ImageFont | None = None) -> int:
    width = 0
    for char in text:
        current_font = emoji_font if emoji_font and is_emoji_character(char) else font
        bbox = draw.textbbox((0, 0), char, font=current_font)
        width += bbox[2] - bbox[0]
    return width


def draw_text_with_font_fallback(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont, emoji_font: ImageFont.ImageFont | None = None, fill=(255, 255, 255)) -> None:
    x, y = xy
    for char in text:
        current_font = emoji_font if emoji_font and is_emoji_character(char) else font
        draw.text((x, y), char, fill=fill, font=current_font)
        bbox = draw.textbbox((0, 0), char, font=current_font)
        x += bbox[2] - bbox[0]


def wrap_text(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int, emoji_font: ImageFont.ImageFont | None = None) -> list[str]:
    lines = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph:
            lines.append("")
            continue

        words = paragraph.split(' ')
        if not words:
            lines.append("")
            continue

        current_line = words[0]
        for word in words[1:]:
            test_line = f"{current_line} {word}"
            if measure_text_width(test_line, draw, font, emoji_font) <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)

    return lines


async def format_quote_content(message: discord.Message, viewer_id: int | None = None) -> str:
    content = message.content.strip() or "[Embed or media content]"
    if not content:
        return content

                                                                                   
    content = re.sub(r"<@!?\$\d+>", "@game", content)
    content = re.sub(r"<a?:[A-Za-z0-9_]+:\d+>", "", content)
    content = re.sub(r"\s+", " ", content).strip()
    if not content:
        return "[Embed or media content]"

    replacements: list[tuple[str, str]] = []

                   
    for user_id in getattr(message, "raw_mentions", []) or []:
        user = None
        for mention in getattr(message, "mentions", []) or []:
            if getattr(mention, "id", None) == user_id:
                user = mention
                break
        if user is None and getattr(message, "guild", None):
            try:
                user = message.guild.get_member(user_id) or message.guild.get_user(user_id)
            except Exception:
                user = None
                                          
        if user is None:
            try:
                user = bot.get_user(user_id)
            except Exception:
                user = None
        if user is None:
            try:
                user = await bot.fetch_user(user_id)
            except Exception:
                user = None
            continue

        username = getattr(user, "name", None) or str(user_id)
        replacements.append((f"<@{user_id}>", f"@{username}"))
        replacements.append((f"<@!{user_id}>", f"@{username}"))

                      
    for channel_id in getattr(message, "raw_channel_mentions", []) or []:
        channel = None
        for mention in getattr(message, "channel_mentions", []) or []:
            if getattr(mention, "id", None) == channel_id:
                channel = mention
                break
        if channel is None and getattr(message, "guild", None):
            try:
                channel = message.guild.get_channel(channel_id)
            except Exception:
                channel = None
        if channel is None:
            continue

        channel_name = getattr(channel, "name", None) or str(channel_id)
        replacements.append((f"<#{channel_id}>", f"#{channel_name}"))
        replacements.append((f"<# {channel_id}>", f"#{channel_name}"))

                   
    if getattr(message, "guild", None):
        for role in getattr(message, "role_mentions", []) or []:
            role_name = getattr(role, "name", None) or str(getattr(role, "id", ""))
            replacements.append((f"<@&{role.id}>", f"@{role_name}"))

                                     
    for old, new in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        content = content.replace(old, new)

                                     
    def _get_viewer_tz():
        tzinfo = timezone.utc
        if viewer_id is not None:
            try:
                settings = load_user_settings()
                entry = get_user_settings_entry(settings, str(viewer_id))
                off = entry.get("timezone_offset")
                offs = parse_utc_offset(off) if off else None
                if offs is not None:
                    tzinfo = timezone(offs)
            except Exception:
                tzinfo = timezone.utc
        return tzinfo

    tzinfo = _get_viewer_tz()
    def _ts_repl_sync(match: re.Match) -> str:
        ts = int(match.group(1))
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tzinfo)
                                                 
        return dt.strftime("%A %B %H:%M")

    content = re.sub(r"<t:(\d+)(?::[^>]+)?>", _ts_repl_sync, content)

    return content.replace('\n', ' ')


async def create_quote_card(message: discord.Message, viewer_id: int | None = None):
    base_path = os.path.dirname(__file__)
    bg_path = os.path.join(base_path, "Quote_bg.png")
    fg_path = os.path.join(base_path, "Quote_fg.png")
    font_path = resolve_font_path(base_path)

    if not os.path.exists(bg_path) or not os.path.exists(fg_path):
        print(f"Quote background or foreground not found at: {bg_path}, {fg_path}")
        return None

    background = Image.open(bg_path).convert("RGBA")
    foreground = Image.open(fg_path).convert("RGBA")
    avatar_bytes = await message.author.display_avatar.with_format("png").read()

    with Image.open(io.BytesIO(avatar_bytes)) as avatar:
        avatar = avatar.convert("RGBA").resize((360, 360))
        avatar = ImageOps.grayscale(avatar).convert("RGBA")
        background.paste(avatar, (20, 20), avatar)

    background = Image.alpha_composite(background, foreground)
    draw = ImageDraw.Draw(background)

    try:
        font_big = ImageFont.truetype(font_path, 24)
        font_quote_small = ImageFont.truetype(font_path, 20)
        font_small = ImageFont.truetype(font_path, 16)
        font_body = ImageFont.truetype(font_path, 18)
        font_display = ImageFont.truetype(font_path, 20)
    except Exception as e:
        print(f"Font error: {e}. Using default.")
        font_big = ImageFont.load_default()
        font_quote_small = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_display = ImageFont.load_default()

    display_name_is_ascii = not any(ord(char) > 127 for char in message.author.display_name)
    display_name_value = message.author.display_name if display_name_is_ascii else message.author.name
    if len(display_name_value) > 65:
        display_name_value = display_name_value[:64] + "..."
    display_name_text = f"- {display_name_value}"

    username_value = message.author.name
    if len(username_value) > 62:
        username_value = username_value[:61] + "..."
    username_text = f"@{username_value}"
    show_username = display_name_is_ascii

    original_content = await format_quote_content(message, viewer_id=viewer_id)
    content_text = original_content
    has_emoji = any(is_emoji_character(char) for char in original_content)
    had_non_ascii = any(ord(char) > 127 and not is_emoji_character(char) for char in original_content)
    use_local_font = had_non_ascii or has_emoji
    quote_font_path = find_font_file(base_path, text=content_text) if use_local_font else font_path
    content_text = f'"{content_text}"'

    bg_width, bg_height = background.size
    text_x = 300
    text_y = 35
    max_text_width = min(400, bg_width - text_x - 30)
    footer_y = bg_height - 44

    quote_font_size = 24
    try:
        if quote_font_path:
            quote_font = ImageFont.truetype(quote_font_path, quote_font_size)
        else:
            quote_font = font_big
    except Exception:
        quote_font = font_big
    quote_emoji_font = load_emoji_font(base_path, quote_font_size, quote_font)
    lines = wrap_text(content_text, draw, quote_font, max_text_width, quote_emoji_font)

    if len(lines) > 4:
        quote_font_size = max(12, 24 - 2 * (len(lines) - 4))
        try:
            if quote_font_path:
                quote_font = ImageFont.truetype(quote_font_path, quote_font_size)
            else:
                quote_font = font_big
        except Exception:
            quote_font = font_big
        quote_emoji_font = load_emoji_font(base_path, quote_font_size, quote_font)
        lines = wrap_text(content_text, draw, quote_font, max_text_width, quote_emoji_font)
        if len(lines) > 4:
            quote_font_size = max(12, 24 - 2 * (len(lines) - 4))
            try:
                if quote_font_path:
                    quote_font = ImageFont.truetype(quote_font_path, quote_font_size)
                else:
                    quote_font = font_big
            except Exception:
                quote_font = font_big
            quote_emoji_font = load_emoji_font(base_path, quote_font_size, quote_font)
            lines = wrap_text(content_text, draw, quote_font, max_text_width, quote_emoji_font)

    line_height = int(getattr(quote_font, 'size', quote_font_size) * 1.4)
    max_lines = max(1, (footer_y - text_y) // line_height)
    if len(lines) > max_lines:
        visible = lines[:max_lines]
        ellipsis = "..."
        try:
            while ellipsis and measure_text_width(ellipsis, draw, quote_font, quote_emoji_font) > max_text_width:
                ellipsis = ellipsis[:-1]
        except Exception:
            pass

        last = visible[-1] if visible else ""
        if ellipsis and last:
            try:
                while last and measure_text_width(last + ellipsis, draw, quote_font, quote_emoji_font) > max_text_width:
                    last = last[:-1]
            except Exception:
                pass
            last = last.rstrip()
            if not last:
                visible[-1] = ellipsis
            else:
                visible[-1] = last + ellipsis
        else:
            try:
                while last and measure_text_width(last, draw, quote_font, quote_emoji_font) > max_text_width:
                    last = last[:-1]
            except Exception:
                pass
            visible[-1] = last

        lines = visible

    for line in lines:
        draw_text_with_font_fallback(draw, (text_x, text_y), line, quote_font, quote_emoji_font, fill=(255, 255, 255))
        text_y += line_height

    footer_y = bg_height - 44
    username_y = footer_y - 4
    display_name_limit = max(120, min(350, bg_width - text_x - 30))
    display_name_text = f"- {display_name_value}"
    display_font = font_display
    display_font_size = getattr(font_display, "size", 20)

    if len(display_name_text) > 20:
        display_font_size = max(10, display_font_size // 2)
        try:
            display_font = ImageFont.truetype(font_path, display_font_size)
        except Exception:
            display_font = font_display

    if measure_text_width(display_name_text, draw, display_font) > display_name_limit:
        while display_name_text and measure_text_width(display_name_text, draw, display_font) > display_name_limit:
            display_name_text = display_name_text[:-1].rstrip()

    if not display_name_text:
        display_name_text = "-"

    display_x = bg_width - 30
    draw.text((display_x, footer_y - 34), display_name_text, fill=(255, 255, 255), font=display_font, anchor="ra")
    if show_username:
        username_bbox = draw.textbbox((0, 0), username_text, font=font_small)
        username_x = bg_width - 30 - (username_bbox[2] - username_bbox[0])
        draw.text((username_x, username_y), username_text, fill=(100, 100, 100), font=font_small)

    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="quote.png")




# -------------------------------------------------------------------------------------------------------------
#                                               Economy Commands
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="economy-leaderboard", description="Show the server economy leaderboard")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_leaderboard(interaction: discord.Interaction, limit: int = 10):
    if not await ensure_economy_enabled(interaction):
        return
    if limit <= 0:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Limit must be greater than 0.", ephemeral=True)

    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    users = guild.get("users", {})
    if not users:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("No economy data for this server.", ephemeral=True)

    leaderboard = []
    for uid, udata in users.items():
        balance = udata.get("balance", 0)
        leaderboard.append((uid, balance))

    leaderboard.sort(key=lambda x: x[1], reverse=True)
    top = leaderboard[:limit]

    description_lines = []
    for idx, (uid, bal) in enumerate(top, start=1):
        try:
            member = await interaction.guild.fetch_member(int(uid))
            name = member.display_name
        except Exception:
            name = f"User left server (`{uid}`)"
        description_lines.append(f"`#{idx}` **{name}** - ${bal}")

    embed = discord.Embed(title=f"<:chalice:1517579767573123092> Economy Standings Leaderboard - {interaction.guild.name}", color=discord.Color.gold())
    embed.description = "\n".join(description_lines)
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="balance", description="Check your balance or another user's balance")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.describe(user="The user whose balance you want to check")
async def eco_balance(interaction: discord.Interaction, user: discord.Member = None):
    if not await ensure_economy_enabled(interaction):
        return
    target = user or interaction.user
    data = load_data()
    money = data.get(str(interaction.guild.id), {}).get("users", {}).get(str(target.id), {}).get("balance", 0)
    await interaction.response.defer(); await interaction.followup.send(f"<:money:1517580310395486239> {target.display_name}'s balance: **${money}**")


@bot.tree.command(name="daily", description="Claim your daily reward")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.checks.cooldown(1, 86400, key=lambda i: (i.user.id, i.guild.id))
async def eco_daily(interaction: discord.Interaction):
    if not await ensure_economy_enabled(interaction):
        return
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    earnings = random.randint(150, 200)
    user_data["balance"] += earnings
    save_data(data)
    await interaction.response.defer(); await interaction.followup.send(f"<:money:1517580310395486239> You claimed your daily reward and earned **${earnings}**!")


@bot.tree.command(name="pay", description="Pay another user from your balance")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_pay(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not await ensure_economy_enabled(interaction):
        return
    if amount <= 0:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Amount must be greater than 0.", ephemeral=True)
    data = load_data()
    guild_id = str(interaction.guild.id)
    sender_data = get_user_data(data, guild_id, str(interaction.user.id))
    receiver_data = get_user_data(data, guild_id, str(user.id))
    if sender_data["balance"] < amount:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You don't have enough money!", ephemeral=True)
    sender_data["balance"] -= amount
    receiver_data["balance"] += amount
    save_data(data)
    await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Successfully sent **${amount}** to {format_user_reference(user)}!")


@bot.tree.command(name="shop", description="View the server shop")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_shop(interaction: discord.Interaction):
    if not await ensure_economy_enabled(interaction):
        return
    data = load_data()
    shop_items = data.get(str(interaction.guild.id), {}).get("shop", {})
    if not shop_items:
        await interaction.response.defer(); await interaction.followup.send("The shop is currently empty!")
        return

    view = ShopView(shop_items, str(interaction.guild.id), str(interaction.user.id))
    await interaction.response.defer(); await interaction.followup.send(view=view)


@bot.tree.command(name="buy", description="Buy a shop item directly")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.describe(
    item="The shop item to buy",
    amount="How many of the item to buy (up to 99)"
)
async def eco_buy(interaction: discord.Interaction, item: str, amount: int = 1):
    if not await ensure_economy_enabled(interaction):
        return
    is_valid, error_message = validate_item_batch_amount(amount, action_name="buy")
    if not is_valid:
        await interaction.response.defer(ephemeral=True)
        return await interaction.followup.send(error_message, ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    guild = get_guild_data(data, guild_id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))

    canonical_item = find_item_key(guild.get("shop", {}), item)
    if canonical_item is None:
        await interaction.response.defer(ephemeral=True)
        return await interaction.followup.send("<:disapprove:1517452151012589662> That item is not available in the shop.", ephemeral=True)

    shop_info = guild["shop"][canonical_item]
    price = int(shop_info.get("price", 0))
    total_price = price * amount

    if user_data["balance"] < total_price:
        await interaction.response.defer(ephemeral=True)
        return await interaction.followup.send(
            f"<:disapprove:1517452151012589662> You can't afford this purchase. Total cost: **${total_price}**.",
            ephemeral=True,
        )

    user_data["balance"] -= total_price
    inventory_add(user_data["inventory"], canonical_item, amount)
    save_data(data)

    save_data(data)
                                               
    try:
        await increment_quest_progress(interaction.guild, interaction.user, 'buy', amount)
    except Exception:
        pass

    await interaction.response.defer(); await interaction.followup.send(
        f"<:approve:1517452125687513158> You bought **{amount}x {canonical_item}** for **${total_price}**!"
    )


@bot.tree.command(name="inventory", description="Check your inventory or another user's inventory")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.describe(user="The user whose inventory you want to check")
async def eco_inventory(interaction: discord.Interaction, user: discord.Member = None):
    if not await ensure_economy_enabled(interaction):
        return
    target = user or interaction.user
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(target.id))
    inv = user_data.get("inventory", {})
    embed = discord.Embed(title=f"<:box:1517581439552585759> {target.display_name}'s Inventory", color=discord.Color.green())
    if not inv:
        embed.description = "This inventory is currently empty."
    else:
        embed.description = "\n".join(f"• {item} ×{count}" for item, count in inv.items())
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="inventory-edit", description="Edit a user's inventory")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_inventory_edit(interaction: discord.Interaction, user: discord.Member, item: str, action: str, amount: int = 1):
    if not await ensure_economy_enabled(interaction):
        return
    item = normalize_item(item)
    action = action.lower().strip()
    if action not in ("add", "remove"):
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Action must be **add** or **remove**.", ephemeral=True)
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(user.id))
    if action == "add":
        inventory_add(user_data["inventory"], item, amount)
    else:
        removed = inventory_remove(user_data["inventory"], item, amount)
        if removed < amount:
            save_data(data)
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:warning:1517452174991556758> Only removed **{removed}x {item}** - {user.display_name} didn't have enough.", ephemeral=True
            )
    save_data(data)
    direction = "to" if action == "add" else "from"
    await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> {action.capitalize()}d **{amount}x {item}** {direction} {user.display_name}'s inventory.")


@bot.tree.command(name="balance-edit", description="Set a user's balance")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_balance_edit(interaction: discord.Interaction, user: discord.Member, amount: int):
    if not await ensure_economy_enabled(interaction):
        return
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(user.id))
    user_data["balance"] = amount
    save_data(data)
    await interaction.response.defer(); await interaction.followup.send(f"<:approve:1517452125687513158> Set {user.display_name}'s balance to **${amount}**.")




# -------------------------------------------------------------------------------------------------------------
#                                               Minigames
# -------------------------------------------------------------------------------------------------------------





@bot.tree.command(name="slot_game", description="Play the economy slot machine and wager money")
@app_commands.allowed_installs(guilds=True, users=False)
async def game_slot(interaction: discord.Interaction, amount: int):
    if not await ensure_economy_enabled(interaction):
        return
    if amount <= 0:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Bet amount must be greater than 0.", ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))
    before_balance = user_data["balance"]

    if before_balance < amount:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You don't have enough money to place that bet.", ephemeral=True)

    emojis = ['🍒', '🍎', '🍇', '💎', '🔔', '🍋']
    e1, e2, e3 = (random.choice(emojis) for _ in range(3))

    if e1 == e2 == e3:
        user_data["balance"] += amount*10
        result_text = f"<:chalice:1517579767573123092> **JACKPOT!** You won **${amount*10}**!"
        color = discord.Color.green()
    else:
        user_data["balance"] -= amount
        result_text = f"<:money:1517580310395486239> You lost **${amount}**. Better luck next time!"
        color = discord.Color.red()

    save_data(data)

    embed = discord.Embed(title="<:777:1518352060574208031> Economy Slot Machine", description=f"Bet: **${amount}**", color=color)
    embed.add_field(name="Result", value=f"| {e1} | {e2} | {e3} |", inline=False)
    embed.add_field(name="Outcome", value=result_text, inline=False)
    embed.set_footer(text=f"Before: ${before_balance} • After: ${user_data['balance']}")
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="coinflip_game", description="Play coinflip and wager money")
@app_commands.allowed_installs(guilds=True, users=False)
async def game_coinflip(interaction: discord.Interaction, amount: int):
    if not await ensure_economy_enabled(interaction):
        return
    if amount <= 0:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Bet amount must be greater than 0.", ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))
    before_balance = user_data["balance"]

    if before_balance < amount:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You don't have enough money to place that bet.", ephemeral=True)

    result = random.choice(["heads", "tails"])
    if result == "heads":
        user_data["balance"] += amount
        result_text = f"<:chalice:1517579767573123092> You won **${amount}**! The coin landed on **Heads**."
        color = discord.Color.green()
    else:
        user_data["balance"] -= amount
        result_text = f"<:money:1517580310395486239> You lost **${amount}**. The coin landed on **Tails**."
        color = discord.Color.red()

    save_data(data)

                                                             
    try:
        await increment_quest_progress(interaction.guild, interaction.user, 'coinflip', 1)
        if result == 'heads':
            await increment_quest_progress(interaction.guild, interaction.user, 'coinflip_win', 1)
    except Exception:
        pass

    embed = discord.Embed(title="<:coin:1518351100783231138> Coin Flip", description=f"Bet: **${amount}**", color=color)
    embed.add_field(name="Result", value=result_text, inline=False)
    embed.set_footer(text=f"Before: ${before_balance} • After: ${user_data['balance']}")
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


class MinesButton(discord.ui.Button):
    def __init__(self, index: int, row: int, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="❓", row=row)
        self.index = index
        self.row_index = row
        self.col_index = col

    async def callback(self, interaction: discord.Interaction):
        view: MinesGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)
        view.action_taken = True
        if self.index in view.mine_positions:
            self.style = discord.ButtonStyle.danger
            self.label = "💣"
            self.disabled = True
            view.reveal_board()
            view.finished = True
            view.disable_all_items()
            active_minigame_users.discard(view.user_id)
            data = load_data()
            user_data = get_user_data(data, view.guild_id, view.user_id)
            after_balance = user_data["balance"]
            view.embed.title = "💥 Minesweeper - Lost"
            view.embed.description = (
                f"You hit a mine and lost your wager of **${view.amount}**.\n"
                f"Safe tiles found: **{len(view.revealed_positions)}/{view.total_safe}**"
            )
            view.embed.set_footer(text=f"Before: ${view.before_balance} • After: ${after_balance}")
            await interaction.response.edit_message(embed=view.embed, view=view)
            return

        self.disabled = True
        self.style = discord.ButtonStyle.success
        view.revealed_positions.add(self.index)
        adjacent = view.adjacent_mine_count(self.index)
        self.label = str(adjacent) if adjacent > 0 else "0"
        view.update_embed()
        if len(view.revealed_positions) >= view.total_safe:
            await view.finish_game(interaction)
            return
        await interaction.response.edit_message(embed=view.embed, view=view)


class MinesCashoutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Cash Out", row=4)

    async def callback(self, interaction: discord.Interaction):
        view: MinesGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)
        if not view.action_taken:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You must reveal at least one tile before cashing out.", ephemeral=True)

        payout = view.calculate_payout()
        data = load_data()
        user_data = get_user_data(data, view.guild_id, view.user_id)
        user_data["balance"] += payout
        save_data(data)
        active_minigame_users.discard(view.user_id)
        view.finished = True
        view.disable_all_items()
        view.embed.title = "<:money:1517580310395486239> Minesweeper - Cash Out"
        view.embed.description = (
            f"You cashed out with **${payout}**.\n"
            f"Safe tiles found: **{len(view.revealed_positions)}/{view.total_safe}**"
        )
        view.embed.set_footer(text=f"Before: ${view.before_balance} • After: ${user_data['balance']}")
        await interaction.response.edit_message(embed=view.embed, view=view)

class MinesGameView(discord.ui.View):
    def __init__(self, amount: int, mines: int, guild_id: str, user_id: int, before_balance: int):
        super().__init__(timeout=600)
        self.amount = amount
        self.mines = mines
        self.guild_id = guild_id
        self.user_id = user_id
        self.before_balance = before_balance
        self.finished = False
        self.action_taken = False
        self.revealed_positions = set()
        self.total_cells = 20
        self.total_safe = self.total_cells - self.mines
        self.mine_positions = set(random.sample(range(self.total_cells), self.mines))
        self.initial_revealed_index = None
        self.embed = discord.Embed(
            title="<:explosive:1517578642723573880> Minesweeper Gamble",
            description="",
            color=discord.Color.red(),
        )
        for row in range(5):
            for col in range(4):
                index = row * 4 + col
                button = MinesButton(index=index, row=row, col=col)
                self.add_item(button)
        self.add_item(MinesCashoutButton())
        self.message = None
        self.reveal_initial_tile()
        self.update_embed()

    def player_safe_count(self) -> int:
        return len(self.revealed_positions) - (1 if self.initial_revealed_index is not None else 0)

    def calculate_payout(self) -> int:
        multiplier = 1 + self.mines * 0.01
        payout = self.amount * (multiplier ** self.player_safe_count())
        return int(round(payout))

    def adjacent_mine_count(self, index: int) -> int:
        row = index // 4
        col = index % 4
        count = 0
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr = row + dr
                nc = col + dc
                if 0 <= nr < 5 and 0 <= nc < 4:
                    if nr * 4 + nc in self.mine_positions:
                        count += 1
        return count

    def update_embed(self):
        safe_count = len(self.revealed_positions)
        payout = self.calculate_payout()
        self.embed.title = "<:explosive:1517578642723573880> Minesweeper Gamble"
        self.embed.description = (
            f"Bet: **${self.amount}**\n"
            f"Mines: **{self.mines}**\n"
            f"Safe tiles found: **{safe_count}/{self.total_safe}**\n"
            f"Cash out value: **${payout}**\n"
            f"Click any tile, or cash out at any time."
        )
        self.embed.set_footer(text=f"Before: ${self.before_balance}")

    def reveal_board(self):
        for item in self.children:
            if isinstance(item, MinesButton):
                if item.index in self.mine_positions:
                    item.disabled = True
                    item.style = discord.ButtonStyle.danger
                    item.label = "💣"
                else:
                    item.disabled = True

    def reveal_initial_tile(self):
        safe_positions = [i for i in range(self.total_cells) if i not in self.mine_positions]
        if not safe_positions:
            return
        initial_index = random.choice(safe_positions)
        self.initial_revealed_index = initial_index
        self.revealed_positions.add(initial_index)

        for item in self.children:
            if isinstance(item, MinesButton) and item.index == initial_index:
                item.disabled = True
                item.style = discord.ButtonStyle.primary
                adjacent = self.adjacent_mine_count(item.index)
                item.label = str(adjacent) if adjacent > 0 else "0"
                break

    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def finish_game(self, interaction: discord.Interaction):
        payout = self.calculate_payout()
        data = load_data()
        user_data = get_user_data(data, self.guild_id, self.user_id)
        user_data["balance"] += payout
        save_data(data)
                                                    
        try:
            guild = bot.get_guild(int(self.guild_id))
            member = None
            if guild:
                member = guild.get_member(self.user_id)
                if member is None:
                    try:
                        member = await guild.fetch_member(self.user_id)
                    except Exception:
                        member = None
            if guild and member:
                await increment_quest_progress(guild, member, 'win_mines', 1)
        except Exception:
            pass
        active_minigame_users.discard(self.user_id)
        self.finished = True
        self.disable_all_items()
        self.embed.title = "<:chalice:1517579767573123092> Minesweeper - Victory"
        self.embed.description = (
            f"You safely revealed all non-mine tiles and won **${payout}**!\n"
            f"Safe tiles found: **{len(self.revealed_positions)}/{self.total_safe}**"
        )
        self.embed.set_footer(text=f"Before: ${self.before_balance} • After: ${user_data['balance']}")
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.finished:
            return
        active_minigame_users.discard(self.user_id)
        self.finished = True
        self.disable_all_items()
        self.reveal_board()
        if self.message:
            self.embed.title = "<:hourglass:1517574046252924938> Minesweeper - Timed Out"
            self.embed.description = (
                f"Time expired and your wager of **${self.amount}** was lost.\n"
                f"Safe tiles found: **{len(self.revealed_positions)}/{self.total_safe}**"
            )
            self.embed.set_footer(text=f"Before: ${self.before_balance}")
            try:
                await self.message.edit(embed=self.embed, view=self)
            except Exception:
                pass


@bot.tree.command(name="minesweeper_game", description="Play minesweeper and wager money")
@app_commands.allowed_installs(guilds=True, users=False)
async def game_mines(interaction: discord.Interaction, amount: int, mines: int):
    if not await ensure_economy_enabled(interaction):
        return
    if amount <= 0:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Bet amount must be greater than 0.", ephemeral=True)
    if mines < 3 or mines > 10:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Number of mines must be between 3 and 10.", ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))
    before_balance = user_data["balance"]

    if interaction.user.id in active_minigame_users:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You already have an active minigame. Finish or wait for it to time out before starting another.", ephemeral=True)

    if before_balance < amount:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You don't have enough money to place that bet.", ephemeral=True)

    user_data["balance"] -= amount
    save_data(data)
    view = MinesGameView(amount=amount, mines=mines, guild_id=guild_id, user_id=interaction.user.id, before_balance=before_balance)
    active_minigame_users.add(interaction.user.id)
    await interaction.response.defer(); await interaction.followup.send(embed=view.embed, view=view)
    view.message = await interaction.original_response()


class TowerButton(discord.ui.Button):
    def __init__(self, row: int, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="❓", row=row)
        self.row_index = row
        self.col_index = col

    async def callback(self, interaction: discord.Interaction):
        view: TowersGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)
        if self.row_index != view.current_row:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You must click a button in the current row first.", ephemeral=True)

        view.action_taken = True
        if self.col_index in view.correct_positions[self.row_index]:
            self.style = discord.ButtonStyle.success
            self.disabled = True
            view.reveal_row(self.row_index)
            view.current_row -= 1
            view.update_embed()
            if view.current_row < 0:
                await view.finish_game(interaction)
                return
            view.update_row_buttons()
            await interaction.response.edit_message(embed=view.embed, view=view)
        else:
            self.style = discord.ButtonStyle.danger
            view.reveal_row(self.row_index)
            view.finished = True
            active_minigame_users.discard(view.user_id)
            view.disable_all_items()
            data = load_data()
            user_data = get_user_data(data, view.guild_id, view.user_id)
            after_balance = user_data["balance"]
            view.embed.title = "<:tower:1518350397008252958> Tower Gamble - Lost"
            view.embed.description = (
                f"You chose the wrong button and lost your wager of **${view.amount}**.\n"
                f"Rows cleared: {view.rows_cleared()}/5"
            )
            view.embed.set_footer(text=f"Before: ${view.before_balance} • After: ${after_balance}")
            await interaction.response.edit_message(embed=view.embed, view=view)


class CashoutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Cash Out", row=0)

    async def callback(self, interaction: discord.Interaction):
        view: TowersGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)
        if not view.action_taken:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You must pick at least one tile before cashing out.", ephemeral=True)

        payout = view.calculate_payout(view.rows_cleared())
        data = load_data()
        user_data = get_user_data(data, view.guild_id, view.user_id)
        user_data["balance"] += payout
        save_data(data)
        after_balance = user_data["balance"]
        active_minigame_users.discard(view.user_id)
        view.finished = True
        view.disable_all_items()
        view.embed.title = "<:money:1517580310395486239> Tower Gamble - Cash Out"
        view.embed.description = (
            f"You cashed out with **${payout}**.\n"
            f"Rows cleared: {view.rows_cleared()}/5"
        )
        view.embed.set_footer(text=f"Before: ${view.before_balance} • After: ${after_balance}")
        await interaction.response.edit_message(embed=view.embed, view=view)


class TowersGameView(discord.ui.View):
    def __init__(self, amount: int, guild_id: str, user_id: int, before_balance: int):
        super().__init__(timeout=600)
        self.amount = amount
        self.guild_id = guild_id
        self.user_id = user_id
        self.before_balance = before_balance
        self.finished = False
        self.action_taken = False
        self.current_row = 4
        self.correct_positions = [set(random.sample(range(3), 2)) for _ in range(5)]
        self.embed = discord.Embed(
            title="<:tower:1518350397008252958> Tower Gamble",
            description="",
            color=discord.Color.red(),
        )
        self.update_embed()
        for row in range(5):
            for col in range(3):
                button = TowerButton(row=row, col=col)
                button.disabled = row != self.current_row
                self.add_item(button)
        self.add_item(CashoutButton())
        self.message = None

    def rows_cleared(self) -> int:
        return max(0, 4 - self.current_row)

    def calculate_payout(self, completed_rows: int) -> int:
        return int(round(self.amount * (1.07 ** completed_rows)))

    def update_embed(self):
        completed = self.rows_cleared()
        potential = self.calculate_payout(completed)
        next_row = 5 - self.current_row
        self.embed.title = "<:tower:1518350397008252958> Tower Gamble"
        self.embed.description = (
            f"Bet: **${self.amount}**\n"
            f"Rows cleared: **{completed}/5**\n"
            f"Current cash out value: **${potential}**\n"
            f"Click a button in row **{next_row}** below, or cash out at any time."
        )
        self.embed.set_footer(text=f"Before: ${self.before_balance}")

    def update_row_buttons(self):
        for item in self.children:
            if isinstance(item, TowerButton):
                if item.row_index == self.current_row:
                    item.disabled = False
                    item.style = discord.ButtonStyle.secondary
                else:
                    item.disabled = True

    def reveal_row(self, row_index: int):
        for item in self.children:
            if isinstance(item, TowerButton) and item.row_index == row_index:
                item.disabled = True
                if item.col_index in self.correct_positions[row_index]:
                    item.style = discord.ButtonStyle.success
                else:
                    item.style = discord.ButtonStyle.danger

    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def finish_game(self, interaction: discord.Interaction):
        payout = self.calculate_payout(5)
        data = load_data()
        user_data = get_user_data(data, self.guild_id, self.user_id)
        user_data["balance"] += payout
        save_data(data)
                                                     
        try:
            guild = bot.get_guild(int(self.guild_id))
            member = None
            if guild:
                member = guild.get_member(self.user_id)
                if member is None:
                    try:
                        member = await guild.fetch_member(self.user_id)
                    except Exception:
                        member = None
            if guild and member:
                await increment_quest_progress(guild, member, 'win_towers', 1)
        except Exception:
            pass
        active_minigame_users.discard(self.user_id)
        self.finished = True
        self.disable_all_items()
        self.embed.title = "<:chalice:1517579767573123092> Tower Gamble - Victory"
        self.embed.description = (
            f"You reached the top and won **${payout}**!\n"
            f"Rows cleared: **5/5**"
        )
        self.embed.set_footer(text=f"Before: ${self.before_balance} • After: ${user_data['balance']}")
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.finished:
            return
        active_minigame_users.discard(self.user_id)
        self.finished = True
        self.disable_all_items()
        if self.message:
            data = load_data()
            user_data = get_user_data(data, self.guild_id, self.user_id)
            after_balance = user_data["balance"]
            self.embed.title = "<:hourglass:1517574046252924938> Tower Gamble - Timed Out"
            self.embed.description = (
                f"Time expired and your wager of **${self.amount}** was lost.\n"
                f"Rows cleared: **{self.rows_cleared()}/5**"
            )
            self.embed.set_footer(text=f"Before: ${self.before_balance} • After: ${after_balance}")
            try:
                await self.message.edit(embed=self.embed, view=self)
            except Exception:
                pass


@bot.tree.command(name="towers_game", description="Play tower gamble and wager money")
@app_commands.allowed_installs(guilds=True, users=False)
async def game_towers(interaction: discord.Interaction, amount: int):
    if not await ensure_economy_enabled(interaction):
        return
    if amount <= 0:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Bet amount must be greater than 0.", ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))
    before_balance = user_data["balance"]

    if interaction.user.id in active_minigame_users:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You already have an active minigame. Finish or wait for it to time out before starting another.", ephemeral=True)

    if before_balance < amount:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You don't have enough money to place that bet.", ephemeral=True)

    user_data["balance"] -= amount
    save_data(data)
    view = TowersGameView(amount=amount, guild_id=guild_id, user_id=interaction.user.id, before_balance=before_balance)
    active_minigame_users.add(interaction.user.id)
    await interaction.response.defer(); await interaction.followup.send(embed=view.embed, view=view)
    view.message = await interaction.original_response()

class DeveloperCodeSelect(discord.ui.Select):
    def __init__(self, correct_index: int):
        self.correct_index = correct_index
        options = [discord.SelectOption(label=f"Code {i+1}", value=str(i)) for i in range(10)]
        super().__init__(placeholder="Choose the different code...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        view: WorkGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)

        selected_index = int(self.values[0])
        
        if selected_index == self.correct_index:
            view.finished = True
            view.disable_all_items()
            payout = get_work_payout(view.difficulty)
            data = load_data()
            user_data = get_user_data(data, view.guild_id, view.user_id)
            user_data["balance"] += payout
            save_data(data)
                                                                          
            try:
                guild = bot.get_guild(int(view.guild_id))
                member = None
                if guild:
                    member = guild.get_member(view.user_id)
                    if member is None:
                        try:
                            member = await guild.fetch_member(view.user_id)
                        except Exception:
                            member = None
                if guild and member:
                    event = 'work_win_hard' if view.difficulty == 'hard' else 'work_win_easy_normal'
                    await increment_quest_progress(guild, member, event, 1)
            except Exception:
                pass
            view.embed.title = "<:list:1517497572770451567> Developer Job - Success!"
            view.embed.description = f"You found the odd code string and earned **${payout}**!"
            await interaction.response.edit_message(embed=view.embed, view=view)
        else:
            view.finished = True
            view.disable_all_items()
            view.embed.title = "<:list:1517497572770451567> Developer Job - Failed!"
            view.embed.description = "That's not the odd code! You didn't earn anything this time."
            await interaction.response.edit_message(embed=view.embed, view=view)


class DeveloperCodeButton(discord.ui.Button):
    def __init__(self, index: int, code: str, is_odd: bool, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label=code, row=row)
        self.index = index
        self.code = code
        self.is_odd = is_odd

    async def callback(self, interaction: discord.Interaction):
        view: WorkGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)

        if self.is_odd:
            view.finished = True
            view.disable_all_items()
            payout = get_work_payout(view.difficulty)
            data = load_data()
            user_data = get_user_data(data, view.guild_id, view.user_id)
            user_data["balance"] += payout
            save_data(data)
                                                                            
            try:
                guild = bot.get_guild(int(view.guild_id))
                member = None
                if guild:
                    member = guild.get_member(view.user_id)
                    if member is None:
                        try:
                            member = await guild.fetch_member(view.user_id)
                        except Exception:
                            member = None
                if guild and member:
                    event = 'work_win_hard' if view.difficulty == 'hard' else 'work_win_easy_normal'
                    await increment_quest_progress(guild, member, event, 1)
            except Exception:
                pass
            view.embed.title = "<:list:1517497572770451567> Developer Job - Success!"
            view.embed.description = f"You found the odd code string and earned **${payout}**!"
            await interaction.response.edit_message(embed=view.embed, view=view)
        else:
            self.disabled = True
            self.style = discord.ButtonStyle.danger
            view.finished = True
            view.disable_all_items()
            view.embed.title = "<:list:1517497572770451567> Developer Job - Failed!"
            view.embed.description = "That's not the odd code! You didn't earn anything this time."
            await interaction.response.edit_message(embed=view.embed, view=view)


class FarmerCropButton(discord.ui.Button):
    def __init__(self, index: int, crop: str, is_target: bool, is_dirt: bool, row: int, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label=crop, row=row)
        self.index = index
        self.crop = crop
        self.is_target = is_target
        self.is_dirt = is_dirt
        self.col_index = col

    async def callback(self, interaction: discord.Interaction):
        view: WorkGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)

        if self.is_dirt:
            self.disabled = True
            await interaction.response.defer()
            return

        if self.is_target:
            view.correct_crops_clicked.add(self.index)
            self.disabled = True
            self.style = discord.ButtonStyle.success
            if len(view.correct_crops_clicked) == len(view.target_crop_indices):
                view.finished = True
                view.disable_all_items()
                payout = get_work_payout(view.difficulty)
                data = load_data()
                user_data = get_user_data(data, view.guild_id, view.user_id)
                user_data["balance"] += payout
                save_data(data)
                                                                         
                try:
                    guild = bot.get_guild(int(view.guild_id))
                    member = None
                    if guild:
                        member = guild.get_member(view.user_id)
                        if member is None:
                            try:
                                member = await guild.fetch_member(view.user_id)
                            except Exception:
                                member = None
                    if guild and member:
                        event = 'work_win_hard' if view.difficulty == 'hard' else 'work_win_easy_normal'
                        await increment_quest_progress(guild, member, event, 1)
                except Exception:
                    pass
                view.embed.title = "🌱 Farmer Job - Success!"
                view.embed.description = f"You collected all the correct crops and earned **${payout}**!"
                await interaction.response.edit_message(embed=view.embed, view=view)
            else:
                await interaction.response.defer()
        else:
            self.disabled = True
            self.style = discord.ButtonStyle.danger
            view.finished = True
            view.disable_all_items()
            view.embed.title = "🌱 Farmer Job - Failed!"
            view.embed.description = "You clicked the wrong crop! You didn't earn anything this time."
            await interaction.response.edit_message(embed=view.embed, view=view)


class WorkGameView(discord.ui.View):
    def __init__(self, job_type: str, guild_id: str, user_id: int, amount: int, difficulty: str = "normal"):
        difficulty_settings = WORK_DIFFICULTY_SETTINGS.get(difficulty, WORK_DIFFICULTY_SETTINGS["normal"])
        super().__init__(timeout=difficulty_settings["timeout"])
        self.job_type = job_type
        self.guild_id = guild_id
        self.user_id = user_id
        self.amount = amount
        self.difficulty = difficulty if difficulty in WORK_DIFFICULTY_SETTINGS else "normal"
        self.timeout_seconds = difficulty_settings["timeout"]
        self.developer_button_count = difficulty_settings["developer_buttons"]
        self.farmer_target_count = difficulty_settings["farmer_targets"]
        self.math_operations = difficulty_settings["math_operations"]
        self.finished = False
        self.correct_crops_clicked = set()
        self.target_crop_indices = set()
        self.embed = discord.Embed(color=discord.Color.blue())
        self.message = None

        if job_type == "developer":
            self.setup_developer_job()
        elif job_type == "farmer":
            self.setup_farmer_job()
        elif job_type == "math":
            self.setup_math_job()

    def setup_developer_job(self):
        code_string = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", k=6))
        code_options = [code_string] * (self.developer_button_count - 1)
        odd_code = self.mutate_string(code_string)
        code_options.append(odd_code)
        random.shuffle(code_options)
        
        self.embed.title = "<:list:1517497572770451567> Developer Job"
        self.embed.description = (
            f"Find the code string that is different from the others!\n"
            f"<:timer:1517996239583576194> **{self.timeout_seconds} seconds left**"
        )
        
        odd_index = code_options.index(odd_code)
        for i, code in enumerate(code_options):
            is_odd = (i == odd_index)
            button = DeveloperCodeButton(i, code, is_odd, row=i // 5)
            self.add_item(button)

    def setup_farmer_job(self):
        crops = ["🥕", "🥬", "🌾", "🫛", "🥔"]
        target_crop = random.choice(crops)
        wrong_crops = random.sample([c for c in crops if c != target_crop], 2)

        target_positions = set(random.sample(range(8), self.farmer_target_count))
        wrong_positions = set(random.sample([i for i in range(8) if i not in target_positions], 2))
        self.target_crop_indices = target_positions

        self.embed.title = "🌱 Farmer Job"
        self.embed.description = (
            f"Collect all **{len(target_positions)}** {target_crop} crops from the farm!\n"
            f"Click the right crops and avoid the others.\n"
            f"<:timer:1517996239583576194> **{self.timeout_seconds} seconds left**"
        )

        for i in range(8):
            row = i // 4
            col = i % 4
            if i in target_positions:
                button = FarmerCropButton(i, target_crop, True, False, row, col)
            elif i in wrong_positions:
                wrong_crop = wrong_crops.pop()
                button = FarmerCropButton(i, wrong_crop, False, False, row, col)
            else:
                button = FarmerCropButton(i, "🟫", False, True, row, col)
            self.add_item(button)

    def setup_math_job(self):
        self.embed.title = "<:plus:1518348756570079262> Math Teacher Job"
        self.embed.description = f"Solve the equation!\n<:timer:1517996239583576194> **{self.timeout_seconds} seconds left**"
        
        operation = random.choice(self.math_operations)
        if operation == "/":
            num2 = random.randint(2, 12)
            self.correct_answer = random.randint(2, 12)
            num1 = num2 * self.correct_answer
        else:
            num1 = random.randint(10, 99)
            num2 = random.randint(1, 50)
        
        if operation == "+":
            self.correct_answer = num1 + num2
        elif operation == "-":
            self.correct_answer = num1 - num2
        elif operation == "*":
            self.correct_answer = num1 * num2
        else:
            self.correct_answer = num1 // num2
        
        self.equation = f"{num1} {operation} {num2} = ?"
        self.embed.description = f"**{self.equation}**\n<:timer:1517996239583576194> **{self.timeout_seconds} seconds left**"
        
        answer_input = discord.ui.TextInput(
            label="Your Answer",
            placeholder="Enter the answer",
            min_length=1,
            max_length=10,
        )
    
        class MathAnswerModal(discord.ui.Modal):
            def __init__(self, view: "WorkGameView"):
                super().__init__(title="Answer")
                self.add_item(answer_input)
                self.view = view
            
            async def on_submit(self, modal_interaction: discord.Interaction):
                if modal_interaction.user.id != self.view.user_id:
                    await modal_interaction.response.defer(ephemeral=True); await modal_interaction.followup.send("<:multi:1518348755261460661> This is not for you.", ephemeral=True)
                    return
                if self.view.finished:
                    await modal_interaction.response.defer(ephemeral=True); await modal_interaction.followup.send("<:disapprove:1517452151012589662> Game already finished.", ephemeral=True)
                    return
                
                try:
                    user_answer = int(answer_input.value)
                    if user_answer == self.view.correct_answer:
                        self.view.finished = True
                        self.view.disable_all_items()
                        payout = get_work_payout(self.view.difficulty)
                        data = load_data()
                        user_data = get_user_data(data, self.view.guild_id, self.view.user_id)
                        user_data["balance"] += payout
                        save_data(data)
                        self.view.embed.title = "<:multi:1518348755261460661> Math Teacher Job - Success!"
                        self.view.embed.description = f"Correct! The answer is **{self.view.correct_answer}**. You earned **${payout}**!"
                        await modal_interaction.response.defer()
                                                                               
                        try:
                            guild = bot.get_guild(int(self.view.guild_id))
                            member = None
                            if guild:
                                member = guild.get_member(self.view.user_id)
                                if member is None:
                                    try:
                                        member = await guild.fetch_member(self.view.user_id)
                                    except Exception:
                                        member = None
                            if guild and member:
                                event = 'work_win_hard' if self.view.difficulty == 'hard' else 'work_win_easy_normal'
                                await increment_quest_progress(guild, member, event, 1)
                        except Exception:
                            pass
                        await self.view.message.edit(embed=self.view.embed, view=self.view)
                    else:
                        self.view.finished = True
                        self.view.disable_all_items()
                        self.view.embed.title = "<:minus:1518348754111959150> Math Teacher Job - Failed!"
                        self.view.embed.description = f"Wrong! The correct answer is **{self.view.correct_answer}**. You didn't earn anything this time."
                        await modal_interaction.response.defer(ephemeral=True)
                        await self.view.message.edit(embed=self.view.embed, view=self.view)
                except ValueError:
                    await modal_interaction.response.defer(ephemeral=True); await modal_interaction.followup.send("<:disapprove:1517452151012589662> Please enter a valid number.", ephemeral=True)
        
        submit_button = discord.ui.Button(label="Submit Answer", style=discord.ButtonStyle.primary)
        
        async def submit_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
            await interaction.response.send_modal(MathAnswerModal(self))
        
        submit_button.callback = submit_callback
        self.add_item(submit_button)

    def mutate_string(self, s: str) -> str:
        chars = list(s)
        pos = random.randint(0, len(chars) - 1)
        pool = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        pool = pool.replace(chars[pos], "")
        chars[pos] = random.choice(pool)
        return "".join(chars)

    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        self.disable_all_items()
        if self.message:
            self.embed.title = "<:timer:1517996239583576194> Work - Timed Out"
            self.embed.description = "Time expired! You didn't earn anything this time."
            try:
                await self.message.edit(embed=self.embed, view=self)
            except Exception:
                pass


work_cooldowns = {}

WORK_DIFFICULTY_SETTINGS = {
    "easy": {
        "timeout": 30,
        "developer_buttons": 8,
        "farmer_targets": 2,
        "math_operations": ["+", "-"],
        "payout_range": (200, 300),
    },
    "normal": {
        "timeout": 25,
        "developer_buttons": 10,
        "farmer_targets": 3,
        "math_operations": ["*", "-"],
        "payout_range": (450, 550),
    },
    "hard": {
        "timeout": 20,
        "developer_buttons": 12,
        "farmer_targets": 4,
        "math_operations": ["*", "/"],
        "payout_range": (700, 800),
    },
}


def get_work_payout(difficulty: str) -> int:
    settings = WORK_DIFFICULTY_SETTINGS.get(difficulty, WORK_DIFFICULTY_SETTINGS["normal"])
    low, high = settings["payout_range"]
    return random.randint(low, high)


@bot.tree.command(name="work_game", description="Work to earn money (get 1 of 3 random jobs, 2 hour cooldown)")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.describe(difficulty="Choose the work difficulty")
@app_commands.choices(
    difficulty=[
        app_commands.Choice(name="Easy", value="easy"),
        app_commands.Choice(name="Normal", value="normal"),
        app_commands.Choice(name="Hard", value="hard"),
    ]
)
async def game_work(interaction: discord.Interaction, difficulty: str = "normal"):
    if not await ensure_economy_enabled(interaction):
        return
    difficulty = difficulty.lower().strip()
    if difficulty not in WORK_DIFFICULTY_SETTINGS:
        difficulty = "normal"

    user_id = str(interaction.user.id)
    guild_id = str(interaction.guild.id)
    cooldown_key = f"{guild_id}_{user_id}"
    
    now = datetime.now()
    if cooldown_key in work_cooldowns:
        last_use = work_cooldowns[cooldown_key]
        elapsed = (now - last_use).total_seconds()
        remaining = 7200 - elapsed
        
        if remaining > 0:
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:timer:1517996239583576194> You can work again in **{minutes}m {seconds}s**.",
                ephemeral=True
            )
    
    data = load_data()
    user_data = get_user_data(data, guild_id, user_id)
    
    job_type = random.choice(["developer", "farmer", "math"])
    amount = 0
    
    work_cooldowns[cooldown_key] = now
    
    view = WorkGameView(job_type, guild_id, interaction.user.id, amount, difficulty)
    await interaction.response.defer(); await interaction.followup.send(embed=view.embed, view=view)
    view.message = await interaction.original_response()




# -------------------------------------------------------------------------------------------------------------
#                                               Crafting Commands
# -------------------------------------------------------------------------------------------------------------




MAX_ITEM_BATCH_SIZE = 99
def validate_item_batch_amount(amount: int, *, action_name: str) -> tuple[bool, str | None]:
    if amount <= 0:
        return False, f"<:disapprove:1517452151012589662> You must {action_name} at least 1 item."
    if amount > MAX_ITEM_BATCH_SIZE:
        return False, f"<:disapprove:1517452151012589662> You can only {action_name} up to {MAX_ITEM_BATCH_SIZE} items at once."
    return True, None


@bot.tree.command(name="craft", description="Craft an item")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_craft(interaction: discord.Interaction, item: str, amount: int = 1):
    if not await ensure_economy_enabled(interaction):
        return
    is_valid, error_message = validate_item_batch_amount(amount, action_name="craft")
    if not is_valid:
        await interaction.response.defer(ephemeral=True)
        return await interaction.followup.send(error_message, ephemeral=True)

    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    canonical_item = find_item_key(guild["recipes"], item)
    if not canonical_item:
        await interaction.response.defer(ephemeral=True)
        return await interaction.followup.send("<:disapprove:1517452151012589662> This item is not craftable.", ephemeral=True)
    recipe = guild["recipes"][canonical_item]
    delay = recipe.get("delay", 0)
    requirement_text = format_recipe_requirements(recipe)
    for req_item, count in sorted(recipe["reqs"].items(), key=lambda item: item[0].lower()):
        if inventory_count(user_data["inventory"], req_item) < (count * amount):
            await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(f"<:disapprove:1517452151012589662> You don't have enough **{req_item}**.", ephemeral=True)
    await interaction.response.defer(); await interaction.followup.send(f"🔨 Starting to craft {amount}x **{canonical_item}**... (Wait {delay}s)\nRequirements: {requirement_text}")
    if delay > 0:
        await asyncio.sleep(delay)
        data = load_data()
        guild = get_guild_data(data, str(interaction.guild.id))
        user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
        for req_item, count in sorted(recipe["reqs"].items(), key=lambda item: item[0].lower()):
            if inventory_count(user_data["inventory"], req_item) < (count * amount):
                return await interaction.followup.send("<:disapprove:1517452151012589662> Crafting failed: You spent your ingredients while waiting!", ephemeral=True)
    for req_item, count in sorted(recipe["reqs"].items(), key=lambda item: item[0].lower()):
        inventory_remove(user_data["inventory"], req_item, count * amount)
    inventory_add(user_data["inventory"], canonical_item, amount)
    save_data(data)
                                           
    try:
        await increment_quest_progress(interaction.guild, interaction.user, 'craft', amount)
    except Exception:
        pass

    await interaction.followup.send(f"<:approve:1517452125687513158> Finished crafting {amount}x **{canonical_item}**!")


@bot.tree.command(name="use", description="Use an item from your inventory")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_use(interaction: discord.Interaction, item: str, number_of_times: int = 1):
    if not await ensure_economy_enabled(interaction):
        return
    is_valid, error_message = validate_item_batch_amount(number_of_times, action_name="use")
    if not is_valid:
        await interaction.response.defer(ephemeral=True)
        return await interaction.followup.send(error_message, ephemeral=True)

    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    if inventory_count(user_data["inventory"], item) < number_of_times:
        await interaction.response.defer(ephemeral=True)
        return await interaction.followup.send(f"<:disapprove:1517452151012589662> You need **{number_of_times}x** of this item to do that.", ephemeral=True)
    canonical_item = find_item_key(guild["item_uses"], item)
    if not canonical_item:
        await interaction.response.defer(ephemeral=True)
        return await interaction.followup.send("<:disapprove:1517452151012589662> This item has no special use effect.", ephemeral=True)
    effect = guild["item_uses"][canonical_item]
    if number_of_times > 1 and (effect.get("role_id") or effect.get("temp_role_id")):
        await interaction.response.defer(ephemeral=True)
        return await interaction.followup.send("<:disapprove:1517452151012589662> You cannot use role-giving items multiple times at once.", ephemeral=True)
    if effect.get("instant_message"):
        await interaction.response.defer(); await interaction.followup.send(effect["instant_message"])
    else:
        await interaction.response.defer()
    if effect.get("delay", 0) > 0:
        await asyncio.sleep(effect["delay"])
    total_money = 0
    reward_items_given = []
    total_xp = 0
    for _ in range(number_of_times):
        inventory_remove(user_data["inventory"], item)
        total_money += effect.get("money", 0)
        total_xp += effect.get("xp", 0)
        if effect.get("give_item"):
            reward_name = effect["give_item"]
            reward_amount = effect.get("give_item_amount", 1)
            inventory_add(user_data["inventory"], reward_name, reward_amount)
            reward_items_given.append(reward_name)
        if number_of_times == 1:
            if effect.get("role_id"):
                role = interaction.guild.get_role(effect["role_id"])
                if role and interaction.guild.me.top_role > role:
                    try:
                        await interaction.user.add_roles(role)
                    except discord.Forbidden as error:
                        add_bot_error_entry(interaction.guild.id, interaction.channel_id, interaction.user, "item use role grant", error)
            if effect.get("temp_role_id"):
                role = interaction.guild.get_role(effect["temp_role_id"])
                if role and interaction.guild.me.top_role > role:
                    try:
                        await interaction.user.add_roles(role)
                    except discord.Forbidden as error:
                        add_bot_error_entry(interaction.guild.id, interaction.channel_id, interaction.user, "item use temp role grant", error)
                        continue
                    async def remove_role(r):
                            await asyncio.sleep(effect["duration"])
                            try:
                                await interaction.user.remove_roles(r)
                            except discord.Forbidden as error:
                                add_bot_error_entry(interaction.guild.id, interaction.channel_id, interaction.user, "item use temp role remove", error)
                    bot.loop.create_task(remove_role(role))
    user_data["balance"] += total_money
    save_data(data)
    if total_xp > 0:
        await add_xp(interaction.user, interaction.guild, total_xp, announce_channel=interaction.channel)
    final_msg = f"<:spark:1517583248421552305> [{number_of_times}x] {effect['message']}"
    if total_money > 0:
        final_msg += f" (Reward: ${total_money})"
    if total_xp > 0:
        final_msg += f" (+{total_xp} XP)"
    if reward_items_given:
        final_msg += f" (Received: {reward_items_given[0]}!)"
    if interaction.response.is_done():
        await interaction.followup.send(final_msg)
    else:
        await interaction.response.defer(); await interaction.followup.send(final_msg)
                                              
    try:
        await increment_quest_progress(interaction.guild, interaction.user, 'use', number_of_times)
    except Exception:
        pass


@bot.tree.command(name="sell", description="Sell a specific amount of an item from your inventory")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_sell(interaction: discord.Interaction, item: str, amount: int = 1):
    if not await ensure_economy_enabled(interaction):
        return
    is_valid, error_message = validate_item_batch_amount(amount, action_name="sell")
    if not is_valid:
        await interaction.response.defer(ephemeral=True)
        return await interaction.followup.send(error_message, ephemeral=True)

    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    canonical_item = find_item_key(guild.get("item_values", {}), item)
    if canonical_item is None:
        await interaction.response.defer(ephemeral=True)
        return await interaction.followup.send(f"<:disapprove:1517452151012589662> **{item}** cannot be sold. No price has been set for it.", ephemeral=True)
    item_price = guild["item_values"][canonical_item]
    user_count = inventory_count(user_data["inventory"], canonical_item)
    if user_count < amount:
        await interaction.response.defer(ephemeral=True)
        return await interaction.followup.send(
            f"<:disapprove:1517452151012589662> You don't have enough! You have **{user_count}x {canonical_item}**, but tried to sell **{amount}x**.", ephemeral=True
        )
    inventory_remove(user_data["inventory"], canonical_item, amount)
    total_value = item_price * amount
    user_data["balance"] += total_value
    save_data(data)
    await interaction.response.defer(); await interaction.followup.send(
        f"<:money:1517580310395486239> You sold **{amount}x {canonical_item}** for a total of **${total_value}**!\n"
        f"Your new balance is **${user_data['balance']}**."
    )
                                                
    try:
        await increment_quest_progress(interaction.guild, interaction.user, 'sell', amount)
    except Exception:
        pass


@bot.tree.command(name="trash", description="Delete an item from your inventory")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_trash(interaction: discord.Interaction, item: str, amount: int = 1):
    if not await ensure_economy_enabled(interaction):
        return
    is_valid, error_message = validate_item_batch_amount(amount, action_name="delete")
    if not is_valid:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send(error_message, ephemeral=True)

    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    canonical_item = find_item_key(guild.get("recipes", {}), item)
    if canonical_item is None:
        canonical_item = find_item_key(guild.get("item_uses", {}), item)
    if canonical_item is None:
        canonical_item = find_item_key(guild.get("item_values", {}), item)
    if canonical_item is None:
        canonical_item = normalize_item(item)

    user_count = inventory_count(user_data["inventory"], canonical_item)
    if user_count < amount:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:disapprove:1517452151012589662> You don't have enough! You have **{user_count}x {canonical_item}**, but tried to delete **{amount}x**.",
            ephemeral=True,
        )

    inventory_remove(user_data["inventory"], canonical_item, amount)
    save_data(data)
    await interaction.response.defer(); await interaction.followup.send(
        f"<:trash:1517497581058527404> Deleted **{amount}x {canonical_item}** from your inventory."
    )


@bot.tree.command(name="give", description="Give an item from your inventory to another user")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_give(interaction: discord.Interaction, user: discord.Member, item: str, amount: int = 1):
    if not await ensure_economy_enabled(interaction):
        return
    is_valid, error_message = validate_item_batch_amount(amount, action_name="give")
    if not is_valid:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send(error_message, ephemeral=True)

    if user.id == interaction.user.id:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You can't give an item to yourself.", ephemeral=True)

    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    sender_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    receiver_data = get_user_data(data, str(interaction.guild.id), str(user.id))

    canonical_item = find_item_key(guild.get("recipes", {}), item)
    if canonical_item is None:
        canonical_item = find_item_key(guild.get("item_uses", {}), item)
    if canonical_item is None:
        canonical_item = find_item_key(guild.get("item_values", {}), item)
    if canonical_item is None:
        canonical_item = normalize_item(item)

    sender_count = inventory_count(sender_data["inventory"], canonical_item)
    if sender_count < amount:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:disapprove:1517452151012589662> You don't have enough! You have **{sender_count}x {canonical_item}**, but tried to give **{amount}x**.",
            ephemeral=True,
        )

    inventory_remove(sender_data["inventory"], canonical_item, amount)
    inventory_add(receiver_data["inventory"], canonical_item, amount)
    save_data(data)
    await interaction.response.defer(); await interaction.followup.send(
        f"<:approve:1517452125687513158> Gave **{amount}x {canonical_item}** to {format_user_reference(user)}."
    )


class TradeItemModal(Modal):
    def __init__(self, trade_view, user_id: str):
        super().__init__(title="Trade Item")
        self.trade_view = trade_view
        self.user_id = user_id
        self.action_input = TextInput(label="Action (add/remove)", placeholder="add or remove", required=True, max_length=10)
        self.item_input = TextInput(label="Item name", placeholder="Item name", required=True)
        self.amount_input = TextInput(label="Amount", placeholder="1", required=True, max_length=10)
        self.add_item(self.action_input)
        self.add_item(self.item_input)
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        action = self.action_input.value.strip().lower()
        if action not in ("add", "remove"):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Action must be add or remove.", ephemeral=True)
            return

        item_name = normalize_item(self.item_input.value)
        try:
            amount = int(self.amount_input.value.strip())
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Amount must be a number.", ephemeral=True)
            return

        if amount <= 0 or amount > MAX_ITEM_BATCH_SIZE:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:disapprove:1517452151012589662> Amount must be between 1 and {MAX_ITEM_BATCH_SIZE}.",
                ephemeral=True,
            )
            return

        data = load_data()
        user_data = get_user_data(data, str(interaction.guild.id), self.user_id)
        offer = self.trade_view.offers[self.user_id]

        if action == "add":
            available = inventory_count(user_data["inventory"], item_name)
            if available < amount:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    f"<:disapprove:1517452151012589662> You only have {available}x {item_name} available to add.",
                    ephemeral=True,
                )
                return
            offer["items"][item_name] = offer["items"].get(item_name, 0) + amount
        else:
            current = offer["items"].get(item_name, 0)
            if current < amount:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    f"<:disapprove:1517452151012589662> Your offer only contains {current}x {item_name}.",
                    ephemeral=True,
                )
                return
            if amount == current:
                offer["items"].pop(item_name, None)
            else:
                offer["items"][item_name] = current - amount

        self.trade_view.reset_acceptances()
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Your trade offer has been updated.", ephemeral=True)
        await self.trade_view.refresh_trade_message()


class TradeMoneyModal(Modal):
    def __init__(self, trade_view, user_id: str, max_money: int):
        super().__init__(title="Trade Money")
        self.trade_view = trade_view
        self.user_id = user_id
        self.max_money = max_money
        self.money_input = TextInput(label=f"Money (0 - {max_money})", placeholder="0", required=True, max_length=12)
        self.add_item(self.money_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.money_input.value.strip())
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Amount must be a number.", ephemeral=True)
            return

        if amount < 0 or amount > self.max_money:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:disapprove:1517452151012589662> Amount must be between 0 and {self.max_money}.",
                ephemeral=True,
            )
            return

        self.trade_view.offers[self.user_id]["money"] = amount
        self.trade_view.reset_acceptances()
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Your trade money offer has been updated.", ephemeral=True)
        await self.trade_view.refresh_trade_message()


class TradeView(TimeoutDisabledLayoutView):
    def __init__(self, initiator: discord.Member, partner: discord.Member):
        super().__init__(timeout=600)
        self.initiator_id = str(initiator.id)
        self.partner_id = str(partner.id)
        self.initiator_name = initiator.display_name
        self.partner_name = partner.display_name
        self.offers = {
            self.initiator_id: {"items": {}, "money": 0, "status": "pending"},
            self.partner_id: {"items": {}, "money": 0, "status": "pending"},
        }
        self.trade_message = None
        self.trade_ended = False

        self.items_button = Button(label="Items", style=discord.ButtonStyle.secondary)
        self.money_button = Button(label="Money", style=discord.ButtonStyle.secondary)
        self.accept_button = Button(label="Accept", style=discord.ButtonStyle.success)
        self.decline_button = Button(label="Decline", style=discord.ButtonStyle.danger)

        self.items_button.callback = self.on_items_clicked
        self.money_button.callback = self.on_money_clicked
        self.accept_button.callback = self.on_accept_clicked
        self.decline_button.callback = self.on_decline_clicked

        self.refresh_view()

    def refresh_view(self):
        self.clear_items()
        self.add_item(self.build_container())
        self.add_item(discord.ui.ActionRow(self.items_button, self.money_button))
        self.add_item(discord.ui.ActionRow(self.accept_button, self.decline_button))
        self.update_button_states()

    def update_button_states(self):
        disabled = self.trade_ended
        self.items_button.disabled = disabled
        self.money_button.disabled = disabled
        self.accept_button.disabled = disabled
        self.decline_button.disabled = disabled

    def get_status_emoji(self, user_id: str) -> str:
        status = self.offers[user_id]["status"]
        if status == "accepted":
            return "<:approve:1517452125687513158>"
        if status == "declined":
            return "<:disapprove:1517452151012589662>"
        return "<:warning:1517452174991556758>"

    def format_offer_lines(self, user_id: str) -> list[str]:
        offer = self.offers[user_id]
        lines = []
        if offer["items"]:
            for item_name, amount in offer["items"].items():
                lines.append(f"• {item_name} ×{amount}")
        else:
            lines.append("• _(no items offered)_")
        lines.append(f"• Money: **${offer['money']}**")
        return lines

    def build_container(self) -> Container:
        initiator_emoji = self.get_status_emoji(self.initiator_id)
        partner_emoji = self.get_status_emoji(self.partner_id)

        status_lines = []
        if self.trade_ended:
            if any(offer["status"] == "declined" for offer in self.offers.values()):
                declined_users = [
                    self.initiator_name if self.offers[self.initiator_id]["status"] == "declined" else self.partner_name,
                ]
                status_lines.append(TextDisplay(f"<:disapprove:1517452151012589662> Trade declined by {', '.join(declined_users)}. The offer has been closed."))
            else:
                status_lines.append(TextDisplay("<:approve:1517452125687513158> The trade has been completed successfully!"))
        else:
            accepted = [
                self.initiator_name if self.offers[self.initiator_id]["status"] == "accepted" else None,
                self.partner_name if self.offers[self.partner_id]["status"] == "accepted" else None,
            ]
            accepted = [name for name in accepted if name]
            pending = [
                self.initiator_name if self.offers[self.initiator_id]["status"] == "pending" else None,
                self.partner_name if self.offers[self.partner_id]["status"] == "pending" else None,
            ]
            pending = [name for name in pending if name]

            if accepted and pending:
                status_lines.append(TextDisplay(f"<:warning:1517452174991556758> {', '.join(accepted)} accepted. Waiting on {', '.join(pending)}."))
            elif accepted and not pending:
                status_lines.append(TextDisplay("<:approve:1517452125687513158> Both users have accepted. Finalizing trade..."))
            else:
                status_lines.append(TextDisplay("<:warning:1517452174991556758> Trade pending. Add items or money, then both users must accept."))

        lines = [
            TextDisplay(f"## <:loop:1518977798939742449> Trade"),
            *status_lines,
            Separator(),
            TextDisplay(f"{initiator_emoji} {self.initiator_name}'s offer:"),
        ]
        lines.extend(TextDisplay(line) for line in self.format_offer_lines(self.initiator_id))
        lines.append(Separator())
        lines.append(TextDisplay(f"{partner_emoji} {self.partner_name}'s offer:"))
        lines.extend(TextDisplay(line) for line in self.format_offer_lines(self.partner_id))

        return Container(*lines, accent_color=discord.Color.blue())

    async def refresh_trade_message(self):
        self.refresh_view()
        if self.trade_message:
            await self.trade_message.edit(view=self)

    def reset_acceptances(self):
        for offer in self.offers.values():
            if offer["status"] != "declined":
                offer["status"] = "pending"

    async def on_items_clicked(self, interaction: discord.Interaction):
        if str(interaction.user.id) not in self.offers:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You are not part of this trade.", ephemeral=True)
        max_money = get_user_data(load_data(), str(interaction.guild.id), str(interaction.user.id))["balance"]
        await interaction.response.send_modal(TradeItemModal(self, str(interaction.user.id)))

    async def on_money_clicked(self, interaction: discord.Interaction):
        if str(interaction.user.id) not in self.offers:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You are not part of this trade.", ephemeral=True)
        max_money = get_user_data(load_data(), str(interaction.guild.id), str(interaction.user.id))["balance"]
        await interaction.response.send_modal(TradeMoneyModal(self, str(interaction.user.id), max_money))

    async def on_accept_clicked(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id not in self.offers:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You are not part of this trade.", ephemeral=True)
        if self.trade_ended:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This trade has already ended.", ephemeral=True)

        self.offers[user_id]["status"] = "accepted"
        await self.refresh_trade_message()

        if all(offer["status"] == "accepted" for offer in self.offers.values()):
            await self.complete_trade(interaction)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:warning:1517452174991556758> Trade accepted. Waiting for the other user.", ephemeral=True)

    async def on_decline_clicked(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id not in self.offers:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You are not part of this trade.", ephemeral=True)
        if self.trade_ended:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This trade has already ended.", ephemeral=True)

        self.offers[user_id]["status"] = "declined"
        self.trade_ended = True
        await self.refresh_trade_message()
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You declined the trade.", ephemeral=True)

    async def complete_trade(self, interaction: discord.Interaction):
        data = load_data()
        guild_id = str(interaction.guild.id)
        sender_id, receiver_id = self.initiator_id, self.partner_id
        sender_data = get_user_data(data, guild_id, sender_id)
        receiver_data = get_user_data(data, guild_id, receiver_id)

        for user_id, offer in self.offers.items():
            if user_id == self.initiator_id:
                counterparty_id = self.partner_id
            else:
                counterparty_id = self.initiator_id
            counterparty_data = get_user_data(data, guild_id, counterparty_id)
            for item_name, amount in offer["items"].items():
                if inventory_count(get_user_data(data, guild_id, user_id)["inventory"], item_name) < amount:
                    self.reset_acceptances()
                    await self.refresh_trade_message()
                    return await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                        f"<:disapprove:1517452151012589662> Trade failed because {format_user_reference(interaction.guild.get_member(int(user_id)) or interaction.user)} no longer has enough {item_name}.",
                        ephemeral=True,
                    )
            if get_user_data(data, guild_id, user_id)["balance"] < offer["money"]:
                self.reset_acceptances()
                await self.refresh_trade_message()
                return await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    f"<:disapprove:1517452151012589662> Trade failed because {format_user_reference(interaction.guild.get_member(int(user_id)) or interaction.user)} no longer has enough money.",
                    ephemeral=True,
                )

        for user_id, offer in self.offers.items():
            counterparty_id = self.partner_id if user_id == self.initiator_id else self.initiator_id
            counterparty_data = get_user_data(data, guild_id, counterparty_id)
            for item_name, amount in offer["items"].items():
                inventory_remove(get_user_data(data, guild_id, user_id)["inventory"], item_name, amount)
                inventory_add(counterparty_data["inventory"], item_name, amount)
            get_user_data(data, guild_id, user_id)["balance"] -= offer["money"]
            counterparty_data["balance"] += offer["money"]

        save_data(data)
        self.trade_ended = True
        await self.refresh_trade_message()
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Trade completed successfully.", ephemeral=True)

    async def on_timeout(self):
        if self.trade_ended:
            return
                                                  
        for offer in self.offers.values():
            offer["status"] = "declined"
        self.trade_ended = True
        try:
            await super().on_timeout()
        except Exception:
            pass
                                                           
        try:
            await self.refresh_trade_message()
        except Exception:
            pass
                                                         
        msg = self._get_timeout_message()
        if msg is not None:
            try:
                await msg.channel.send("<:disapprove:1517452151012589662> Trade auto-declined due to inactivity.")
            except Exception:
                pass


@bot.tree.command(name="trade", description="Start a trade with another user")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_trade(interaction: discord.Interaction, user: discord.Member):
    if not await ensure_economy_enabled(interaction):
        return
    if user.id == interaction.user.id:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You can't trade with yourself.", ephemeral=True)
    if user.bot:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You can't trade with bots.", ephemeral=True)

    view = TradeView(interaction.user, user)
    await interaction.response.defer(); await interaction.followup.send(view=view)
    view.trade_message = await interaction.original_response()


@bot.tree.command(name="values_info", description="Show all items that can be sold and their prices")
@app_commands.allowed_installs(guilds=True, users=False)
async def info_values(interaction: discord.Interaction):
    if not await ensure_economy_enabled(interaction):
        return
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    prices = guild.get("item_values", {})
    if not prices:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No items have a selling price set yet.", ephemeral=True)

    embed = discord.Embed(title="<:money:1517580310395486239> Item Market Prices", color=discord.Color.gold())
    for item, price in prices.items():
        embed.add_field(name=item, value=f"Sell Price: **${price}**", inline=False)
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="recipes_info", description="Show all available crafting recipes")
@app_commands.allowed_installs(guilds=True, users=False)
async def info_recipes(interaction: discord.Interaction):
    if not await ensure_economy_enabled(interaction):
        return
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    recipes = guild.get("recipes", {})
    if not recipes:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No crafting recipes found.", ephemeral=True)

    embed = discord.Embed(title="<:craft:1518348021161660539> Crafting Book", color=discord.Color.blue())
    for result_item, recipe in sorted(recipes.items(), key=lambda item: item[0].lower()):
        ing_list = format_recipe_requirements(recipe)
        delay_str = f"<:timer:1517996239583576194> {recipe.get('delay', 0)}s" if recipe.get("delay", 0) > 0 else ""
        embed.add_field(
            name=result_item,
            value=f"Requires: {ing_list}" + (f"\n{delay_str}" if delay_str else ""),
            inline=False,
        )
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="uses_info", description="Show what items do when used")
@app_commands.allowed_installs(guilds=True, users=False)
async def info_uses(interaction: discord.Interaction):
    if not await ensure_economy_enabled(interaction):
        return
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    uses = guild.get("item_uses", {})
    if not uses:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No item effects have been set up.", ephemeral=True)

    embed = discord.Embed(title="<:Vial:1517681553377857628> Item Effects Directory", color=discord.Color.green())
    for item, effect in uses.items():
        details = []
        money = effect.get("money", 0)
        if money > 0:
            details.append(f"<:money:1517580310395486239> Gives Money: **${money}**")
        xp_amount = effect.get("xp", 0)
        if xp_amount > 0:
            details.append(f"<:Vial:1517681553377857628> Grants XP: **{xp_amount} XP**")
        give_item = effect.get("give_item")
        if give_item:
            amt = effect.get("give_item_amount", 1)
            details.append(f"<:box:1517581439552585759> Gives: **{amt}x {give_item}**")
        if effect.get("role_id"):
            role = interaction.guild.get_role(effect["role_id"])
            if role:
                details.append(f"<:shield:1518340640801427566> Grants Role: **{role.name}**")
        if effect.get("temp_role_id"):
            role = interaction.guild.get_role(effect["temp_role_id"])
            dur = effect.get("duration", 0)
            if role:
                details.append(f"<:hourglass:1517574046252924938> Temp Role: **{role.name}** ({dur}s)")
        delay = effect.get("delay", 0)
        if delay > 0:
            details.append(f"<:timer:1517996239583576194> Delay: {delay}s")
        msg = effect.get("message")
        if msg and msg != "Used item!":
            details.append(f"<:list:1517497572770451567> Message: *{msg}*")
        if details:
            embed.add_field(name=item, value="\n".join(details), inline=False)

    if not embed.fields:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No item effects have been set up.", ephemeral=True)

    await interaction.response.defer(); await interaction.followup.send(embed=embed)




# -------------------------------------------------------------------------------------------------------------
#                                               Leveling System
# -------------------------------------------------------------------------------------------------------------




async def add_xp(member: discord.Member, guild: discord.Guild, xp_to_add: int, announce_channel=None):
    if member.bot:
        return
        
    if not is_levels_enabled(str(guild.id)):
        return

    levels = load_levels()
    guild_id = str(guild.id)
    user_id = str(member.id)
    
    if guild_id not in levels:
        levels[guild_id] = {"config": {"channel_id": None, "rewards": {}}, "users": {}}
        
    if user_id not in levels[guild_id]["users"]:
        levels[guild_id]["users"][user_id] = {"xp": 0, "level": 0, "color": get_user_color(user_id) or "white"}
        
    user_data = levels[guild_id]["users"][user_id]
    user_data["xp"] += xp_to_add
    
    levels_gained = 0
    while user_data["xp"] >= get_xp_needed(user_data["level"]):
        user_data["xp"] -= get_xp_needed(user_data["level"])
        user_data["level"] += 1
        levels_gained += 1
    leveled_up = levels_gained > 0
        
    has_leveled_up_before = get_user_has_leveled_up_before(user_id)
    first_time_level_up = leveled_up and not has_leveled_up_before

    save_levels(levels)
    if levels_gained > 0:
        try:
            await increment_quest_progress(guild, member, 'gain_levels', levels_gained)
        except Exception:
            pass
    
    if leveled_up:
        rewards = levels[guild_id]["config"].get("rewards", {})
        current_level = user_data["level"]
        reward = rewards.get(str(current_level))
        level_up_notification_sent = False
        if reward:
            if isinstance(reward, (str, int)):
                reward = {"role_id": int(reward)}

            if reward.get("money", 0) > 0 or reward.get("give_item") or reward.get("xp", 0) > 0:
                data = load_data()
                economy_user = get_user_data(data, guild_id, member.id)
                if reward.get("money", 0) > 0:
                    economy_user["balance"] += reward["money"]
                if reward.get("give_item"):
                    inventory_add(economy_user["inventory"], reward["give_item"], reward.get("give_item_amount", 1))
                save_data(data)

            if reward.get("role_id"):
                role = guild.get_role(int(reward["role_id"]))
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role)
                    except discord.Forbidden as error:
                        add_bot_error_entry(guild.id, None, member, f"level reward role: {role.name}", error)

            if reward.get("temp_role_id"):
                role = guild.get_role(int(reward["temp_role_id"]))
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role)
                    except discord.Forbidden as error:
                        add_bot_error_entry(guild.id, None, member, f"level temp role: {role.name}", error)
                        role = None
                if role and reward.get("duration", 0) > 0:
                    async def remove_temp_role(r):
                        await asyncio.sleep(reward.get("duration", 0))
                        try:
                            await member.remove_roles(r)
                        except discord.Forbidden as error:
                            add_bot_error_entry(guild.id, None, member, f"level temp role remove: {r.name}", error)
                    bot.loop.create_task(remove_temp_role(role))

            if reward.get("xp", 0) > 0:
                await add_xp(member, guild, reward["xp"], announce_channel=announce_channel)

        guild_config = get_guild_config(str(guild.id))[0]
        if guild_config.get("level_up_message_enabled", False) and announce_channel is not None:
            try:
                settings = load_user_settings()
                level_up_message = f"{format_user_reference_with_setting(member, settings)} just reached **Level {current_level}**!"
                if first_time_level_up:
                    level_up_message += "\n-# Use /settings and go to the user settings to disable pings."
                await announce_channel.send(level_up_message)
                level_up_notification_sent = True
            except discord.Forbidden as error:
                add_bot_error_entry(guild.id, announce_channel.id, member, "level up message", error)
            except Exception:
                pass

        channel_id = levels[guild_id]["config"].get("channel_id")
        target_channel = guild.get_channel(int(channel_id)) if channel_id else None
        
        if target_channel:
            card_bytes = await create_levelup_card(member, current_level)
            if card_bytes:
                file = discord.File(fp=card_bytes, filename="levelup.png")
                try:
                    settings = load_user_settings()
                    level_banner_message = f"{format_user_reference_with_setting(member, settings)}, you just reached **Level {current_level}**!"
                    if first_time_level_up:
                        level_banner_message += "\n-# Use /settings and go to the user settings to disable pings."
                    await target_channel.send(
                        content=level_banner_message,
                        file=file
                    )
                    level_up_notification_sent = True
                except discord.Forbidden as error:
                    add_bot_error_entry(guild.id, target_channel.id, member, "level banner", error)

        if first_time_level_up and level_up_notification_sent:
            set_user_has_leveled_up_before(user_id, True)


async def create_levelup_card(member: discord.Member, level: int):
    base_path = os.path.dirname(__file__)
    style = ensure_user_banner_assigned(str(member.id))
    bg_path = get_banner_asset_path("levelup_bg", style)
    font_path = resolve_font_path(base_path)

    if not bg_path or not os.path.exists(bg_path):
        return None

    background, entry = assemble_banner_image(bg_path, style)
                                                                           
    background = apply_named_overlay(background, "levelup_mg.png")
    avatar_bytes = await member.display_avatar.with_format("png").read()
    
    bg_width = background.width
    center_x = bg_width // 2

    with Image.open(io.BytesIO(avatar_bytes)) as avatar:
        avatar = avatar.convert("RGBA").resize((120, 120))
        background.paste(avatar, (center_x - 60, 40))
        
    draw = ImageDraw.Draw(background)
    try:
        font = ImageFont.truetype(font_path, 25)
    except Exception:
        font = ImageFont.load_default()
    text_color = pick_text_color(entry, background)
    stroke_color = get_opposite_color(text_color)
    draw.text((center_x, 190), f"{format_banner_username(get_banner_name(member))} you are now Level {level}!", fill=text_color, font=font, anchor="mm", stroke_fill=stroke_color, stroke_width=2)
    
    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


@tasks.loop(minutes=2.0)
async def voice_xp_tracker():
    await bot.wait_until_ready()
    for guild in bot.guilds:
        for voice_channel in guild.voice_channels:
            real_members = [m for m in voice_channel.members if not m.bot and not m.voice.self_deaf and not m.voice.deaf]
            if len(real_members) >= 1:
                for member in real_members:
                    await add_xp(member, guild, random.randint(5, 10))
                    try:
                        await increment_quest_progress(guild, member, 'voice_minutes', 2)
                    except Exception:
                        pass

COLOR_EMOJIS = {
    "white": "<:Square_White:1517679898414813427>", "black": "<:Square_Black:1517679889615032540>", "red": "<:Square_Red:1517679897068306522>", "blue": "<:Square_Blue:1517679890932043897>", 
    "green": "<:Square_Green:1517679893234716843>", "yellow": "<:Square_Yellow:1517679899769311302>", "purple": "<:Square_Purple:1517679895738581062>", "orange": "<:Square_Orange:1517679894526562405>", "brown": "<:Square_Brown:1517679892039204955>", "random": "<:spark:1517583248421552305>"
}


@bot.tree.command(name="level", description="View your current server tier standing level rank card")
@app_commands.allowed_installs(guilds=True, users=False)
async def view_level(interaction: discord.Interaction, user: discord.Member = None):
    if not await ensure_levels_enabled(interaction):
        return
    target = user or interaction.user
    levels = load_levels()
    g_id, u_id = str(interaction.guild_id), str(target.id)
    
    user_data = levels.get(g_id, {}).get("users", {}).get(u_id, {"xp": 0, "level": 0, "color": "white"})
    
    current_xp = user_data["xp"]
    current_lvl = user_data["level"]
    chosen_color = resolve_user_color_name(get_user_color(u_id) or user_data.get("color", "white") or "white")
    xp_needed = get_xp_needed(current_lvl)

    ratio = current_xp / xp_needed if xp_needed > 0 else 0
    filled_blocks = min(max(int(ratio * 10), 0), 10)
    empty_blocks = 10 - filled_blocks
    
    filled_emoji = COLOR_EMOJIS.get(chosen_color, "<:Square_White:1517679898414813427>")
    empty_emoji = COLOR_EMOJIS.get("black", "<:Square_Black:1517679889615032540>")
    
    progress_bar = (filled_emoji * filled_blocks) + (empty_emoji * empty_blocks)
    
    embed = discord.Embed(
        title=f"<:chalice:1517579767573123092> Rank Profile - {target.display_name}",
        color=get_user_color_value(str(target.id))
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Current Tier", value=f"<:spark:1517583248421552305> **Level {current_lvl}**", inline=True)
    embed.add_field(name="Experience Nodes", value=f"<:Vial:1517681553377857628> `{current_xp:,}` / `{xp_needed:,}` XP", inline=True)
    embed.add_field(name="Progress Metrics", value=progress_bar, inline=False)
    
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="level-leaderboard", description="Display the top 10 highest-level users in this guild")
@app_commands.allowed_installs(guilds=True, users=False)
async def level_leaderboard(interaction: discord.Interaction):
    if not await ensure_levels_enabled(interaction):
        return
    levels = load_levels()
    g_id = str(interaction.guild_id)
    
    users_dict = levels.get(g_id, {}).get("users", {})
    if not users_dict:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("📭 No active XP statistics logged in this server yet.", ephemeral=True)
        
    sorted_users = sorted(users_dict.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)
    
    embed = discord.Embed(
        title=f"<:graph:1517584522877866065> Level Standings Leaderboard - {interaction.guild.name}",
        color=get_user_color_value(str(interaction.user.id))
    )
    
    description_text = ""
    for index, (u_id, data) in enumerate(sorted_users[:10], start=1):
        member = interaction.guild.get_member(int(u_id))
        name_str = member.display_name if member else f"User left server (`{u_id}`)"
        description_text += f"`#{index}` **{name_str}** - Lvl {data['level']} ({data['xp']} XP)\n"
        
    embed.description = description_text
    await interaction.response.defer(); await interaction.followup.send(embed=embed)


@bot.tree.command(name="level-edit", description="Manually adjust or set a target user's level and XP indexes")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.checks.has_permissions(manage_guild=True)
async def lvl_edit(interaction: discord.Interaction, user: discord.Member, level: int, xp: int = 0):
    if not await ensure_levels_enabled(interaction):
        return
    levels = load_levels()
    g_id, u_id = str(interaction.guild_id), str(user.id)
    
    if g_id not in levels: levels[g_id] = {"config": {}, "users": {}}
    
    levels[g_id]["users"][u_id] = {
        "xp": max(0, xp),
        "level": max(0, level),
        "color": levels[g_id]["users"].get(u_id, {}).get("color", "white")
    }
    save_levels(levels)
    await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:gear:1517576939097952496> Action complete. Set {format_user_reference(user)} to **Level {level}** with **{xp} XP**.", ephemeral=True)


def save_level_reward_data(guild_id: str, level: int, reward_data: dict) -> None:
    levels = load_levels()
    if guild_id not in levels:
        levels[guild_id] = {"config": {"channel_id": None, "rewards": {}}, "users": {}}
    if "rewards" not in levels[guild_id]["config"]:
        levels[guild_id]["config"]["rewards"] = {}
    levels[guild_id]["config"]["rewards"][str(level)] = reward_data
    save_levels(levels)


def format_level_reward_summary(guild: discord.Guild, level: str, reward_data: dict) -> str:
    parts = []

    role_id = reward_data.get("role_id")
    if role_id:
        role = guild.get_role(role_id)
        parts.append(f"Role: {role.mention if role else f'`{role_id}`'}")

    temp_role_id = reward_data.get("temp_role_id")
    if temp_role_id:
        role = guild.get_role(temp_role_id)
        duration = reward_data.get("duration", 0)
        parts.append(f"Temp role: {role.mention if role else f'`{temp_role_id}`'} for `{duration}s`")

    money = reward_data.get("money", 0)
    if money > 0:
        parts.append(f"Money: `${money}`")

    xp = reward_data.get("xp", 0)
    if xp > 0:
        parts.append(f"XP: `{xp}`")

    give_item = reward_data.get("give_item")
    if give_item:
        amount = reward_data.get("give_item_amount", 1)
        parts.append(f"Item: `{amount}x {give_item}`")

    if not parts:
        return f"Level {level}: No rewards configured."

    return f"Level {level}: " + " | ".join(parts)


@bot.tree.command(name="rewards_info", description="Show the level rewards configured for this guild")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.describe(level="Optional specific level to inspect")
async def info_lvl_rewards(interaction: discord.Interaction, level: int = None):
    if not await ensure_levels_enabled(interaction):
        return
    levels = load_levels()
    g_id = str(interaction.guild_id)
    guild_data = levels.get(g_id, {})
    rewards = guild_data.get("config", {}).get("rewards", {})

    if not rewards:
        return await interaction.response.defer(ephemeral=True); await interaction.followup.send("📭 No level rewards are configured for this server yet.", ephemeral=True)

    embed = discord.Embed(
        title=f"<:box:1517581439552585759> Level Rewards - {interaction.guild.name}",
        color=discord.Color.gold()
    )

    if level is not None:
        reward_data = rewards.get(str(level))
        if not reward_data:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No rewards are configured for level {level} in this server.", ephemeral=True)

        embed.description = format_level_reward_summary(interaction.guild, str(level), reward_data)
    else:
        sorted_levels = sorted(rewards.items(), key=lambda item: int(item[0]))
        embed.description = "\n".join(
            format_level_reward_summary(interaction.guild, lvl, reward_data)
            for lvl, reward_data in sorted_levels
        )

    await interaction.response.defer(); await interaction.followup.send(embed=embed)




# -------------------------------------------------------------------------------------------------------------
#                                               Owner Commands
# -------------------------------------------------------------------------------------------------------------


def update_env_setting(key: str, value: str) -> None:
    env_path = os.path.join(BASE_DIR, ".env")
    lines = []
    found = False

    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    lines.append(line)
                    continue
                if stripped.startswith(f"{key}="):
                    if any(ch.isspace() for ch in value) or any(ch in value for ch in "#=!"):
                        escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')
                        lines.append(f'{key}="{escaped_value}"\n')
                    else:
                        lines.append(f"{key}={value}\n")
                    found = True
                else:
                    lines.append(line)

    if not found:
        if any(ch.isspace() for ch in value) or any(ch in value for ch in "#=!"):
            escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}="{escaped_value}"\n')
        else:
            lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as handle:
        handle.write("".join(lines))

    os.environ[key] = value


@bot.command(name="help")
async def legacy_prefix_help(ctx: commands.Context):
    prefix = (PREFIX or "!").strip() or "!"
    help_text = f"""
<:nUtils:1518376146008539146> List of owner commands (prefix `{prefix}`): ```text
{PREFIX}say - Make the bot say something in the current channel (server admins and owners can use this one)
{prefix}ping - Check the bot latency
{prefix}help - Shows this help menu
{prefix}ver - Shows or updates the bot version
{prefix}alt - Shows or updates the alternate version label
{prefix}activity - Shows or updates the bot activity text
{prefix}banner - Preview a banner style
{prefix}backups - List backup files
{prefix}json - shows the json entry for the server
{prefix}servers - Shows the server list
{prefix}blacklist - ban a server from using the bot
{prefix}stats - Shows runtime system stats (CPU, memory, disk, network, uptime)
{prefix}shutdown - Shutdown the bot with an optional channel + reason
```looking for help with the / commands ? run /help !"""
    await ctx.send(help_text, allowed_mentions=discord.AllowedMentions.none())


@bot.command(name="ping")
async def legacy_prefix_ping(ctx: commands.Context):
    start_time = time.perf_counter()
    ws_latency = round(bot.latency * 1000)
    message = await ctx.send(
        f"🏓 Pong! - **WebSocket:** {ws_latency}ms - **API Round-Trip:** calculating...",
        allowed_mentions=discord.AllowedMentions.none(),
    )
    end_time = time.perf_counter()
    api_latency = round((end_time - start_time) * 1000)
    await message.edit(
        content=f"🏓 Pong! - **WebSocket:** {ws_latency}ms - **API Round-Trip:** {api_latency}ms",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.command(name="stats")
async def legacy_prefix_stats(ctx: commands.Context):
    if not await bot.is_owner(ctx.author):
        return await ctx.send(F"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    if psutil is None:
        return await ctx.send("<:disapprove:1517452151012589662> `psutil` is not available, so process stats cannot be gathered.")

    try:
        process = psutil.Process(os.getpid())
        process_cpu = process.cpu_percent(interval=None)
        process_memory = process.memory_info()
        process_io = process.io_counters()
        uptime_seconds = max(0.0, time.monotonic() - BOT_START_MONOTONIC)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return await ctx.send("<:disapprove:1517452151012589662> process stats are unavailable for this bot instance.")

    stats_text = f"""```text
Process: {os.path.basename(sys.argv[0]) or 'python'}
CPU: {process_cpu:.1f}%
Memory: {process_memory.rss / (1024 ** 2):.1f} MiB
Threads: {process.num_threads()}
Disk read: {process_io.read_bytes / (1024 ** 2):.1f} MiB
Disk write: {process_io.write_bytes / (1024 ** 2):.1f} MiB
Uptime: {format_duration(uptime_seconds)}
```"""
    await ctx.send(stats_text, allowed_mentions=discord.AllowedMentions.none())


@bot.command(name="ver")
async def set_bot_version(ctx: commands.Context, *, new_value: str = ""):
    if not await bot.is_owner(ctx.author):
        return await ctx.send(F"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    global VERSION

    if not new_value.strip():
        return await ctx.send(f"Current version: `{VERSION or ''}`")

    cleaned_value = new_value.strip()
    update_env_setting("BOT_VERSION", cleaned_value)
    VERSION = cleaned_value

    if update_presence.is_running():
        update_presence.restart()

    await ctx.send(f"Updated BOT_VERSION in .env to `{VERSION}`.")


@bot.command(name="alt")
async def set_bot_alt_version(ctx: commands.Context, *, new_value: str = ""):
    if not await bot.is_owner(ctx.author):
        return await ctx.send(F"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    global VERSION_ALTERNATE

    if not new_value.strip():
        return await ctx.send(f"Current alternate version: `{VERSION_ALTERNATE or ''}`")

    cleaned_value = new_value.strip()
    update_env_setting("BOT_VERSION_ALTERNATE", cleaned_value)
    VERSION_ALTERNATE = cleaned_value

    if update_presence.is_running():
        update_presence.restart()

    await ctx.send(f"Updated BOT_VERSION_ALTERNATE in .env to `{VERSION_ALTERNATE}`.")


@bot.command(name="activity")
async def set_bot_activity(ctx: commands.Context, *, new_value: str = ""):
    if not await bot.is_owner(ctx.author):
        return await ctx.send(F"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    global ACTIVITY_TEXT

    if not new_value.strip():
        return await ctx.send(f"Current activity: `{ACTIVITY_TEXT or ''}`")

    cleaned_value = new_value.strip()
    update_env_setting("ACTIVITY", cleaned_value)
    ACTIVITY_TEXT = cleaned_value

    if update_presence.is_running():
        update_presence.restart()

    await ctx.send(f"Updated ACTIVITY in .env to `{ACTIVITY_TEXT}`.")


@bot.command(name="banner")
async def banner_preview_command(ctx: commands.Context, *args: str):
    style_choice = None
    kind_choice = "welcome"

    if not await bot.is_owner(ctx.author):
        return await ctx.send(F"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    if args:
        normalized = [arg.lower() for arg in args]
        kinds = {"welcome", "goodbye", "lvl", "level", "levelup", "quest"}
                                                                          
        for arg in normalized:
            if arg in kinds:
                kind_choice = arg
            elif style_choice is None:
                style_choice = arg

    kind_choice = "welcome" if kind_choice not in {"welcome", "goodbye", "lvl", "level", "levelup", "quest"} else kind_choice
    style_name = normalize_banner_style(style_choice or get_user_banner_style(str(ctx.author.id)))
    style_label = "Admin" if style_name == "admin" else (style_name if style_name == "1000" else style_name.title())
    kind_label = (
        "Welcome" if kind_choice == "welcome" else
        "Goodbye" if kind_choice == "goodbye" else
        "Level" if kind_choice in {"lvl", "level", "levelup"} else
        "Quest"
    )

    preview = await create_banner_preview(ctx.author, kind=kind_choice, style_override=style_name)
    if preview is None:
        return await ctx.send(f"<:disapprove:1517452151012589662> No banner found for style `{style_label}` and kind `{kind_label}`.")

    await ctx.send(f"Banner preview: `{style_label}` / `{kind_label}`", file=preview)


@bot.command(name="backups")
async def backups_command(ctx: commands.Context):
    if not await bot.is_owner(ctx.author):
        return await ctx.send(F"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    view = BackupListView(ctx.author.id)
    message = await ctx.send(view=view)
    view.message = message


@bot.command(name="blacklist")
async def manage_blacklist(ctx: commands.Context, action: str = "", guild_id: str = ""):
    if not await bot.is_owner(ctx.author):
        return await ctx.send(F"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    global BLACKLISTED_GUILDS

    if not action:
        return await ctx.send(
            f"Usage: {PREFIX}blacklist ls | {PREFIX}blacklist add <guild_id> | {PREFIX}blacklist rm <guild_id>",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    act = action.lower()

    if act in ("ls", "list", "show"):
        if not BLACKLISTED_GUILDS:
            return await ctx.send("No blacklisted servers configured.", allowed_mentions=discord.AllowedMentions.none())

        lines = []
        for gid in BLACKLISTED_GUILDS:
            try:
                guild_obj = bot.get_guild(int(gid))
            except Exception:
                guild_obj = None
            name = guild_obj.name if guild_obj else "(not in cache)"
            lines.append(f"{gid} - {name}")

        payload = "\n".join(lines)
        return await ctx.send(f"Blacklisted servers:\n```\n{payload}\n```", allowed_mentions=discord.AllowedMentions.none())

    if act == "add":
        if not guild_id or not guild_id.isdigit():
            return await ctx.send(f"Provide a valid numeric guild id: {PREFIX}blacklist add 123456789", allowed_mentions=discord.AllowedMentions.none())

        gid_int = int(guild_id)
        if gid_int in BLACKLISTED_GUILDS:
            return await ctx.send(f"Guild `{guild_id}` is already blacklisted.", allowed_mentions=discord.AllowedMentions.none())

        BLACKLISTED_GUILDS.append(gid_int)
                         
        env_value = ",".join(str(x) for x in BLACKLISTED_GUILDS)
        update_env_setting("SERVER_BLACKLIST", env_value)
        await ctx.send(f"Added `{guild_id}` to the server blacklist.", allowed_mentions=discord.AllowedMentions.none())
        return

    if act in ("rm", "remove", "del"):
        if not guild_id or not guild_id.isdigit():
            return await ctx.send(f"Provide a valid numeric guild id: {PREFIX}blacklist rm 123456789", allowed_mentions=discord.AllowedMentions.none())

        gid_int = int(guild_id)
        if gid_int not in BLACKLISTED_GUILDS:
            return await ctx.send(f"Guild `{guild_id}` is not in the blacklist.", allowed_mentions=discord.AllowedMentions.none())

        BLACKLISTED_GUILDS = [g for g in BLACKLISTED_GUILDS if g != gid_int]
        env_value = ",".join(str(x) for x in BLACKLISTED_GUILDS)
        update_env_setting("SERVER_BLACKLIST", env_value)
        await ctx.send(f"Removed `{guild_id}` from the server blacklist.", allowed_mentions=discord.AllowedMentions.none())

    else:
        return await ctx.send(
            f"Unknown action `{action}`. Use `ls`, `add` or `rm`.",
            allowed_mentions=discord.AllowedMentions.none(),
        )


@bot.command(name="shutdown")
async def own_shutdown(ctx: commands.Context, *, args: str = ""):
    if not await bot.is_owner(ctx.author):
        return await ctx.send(F"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    channel = None
    reason = "No reason provided"

    if args:
        parts = args.split(maxsplit=1)
        if parts and parts[0].startswith("#"):
            channel_name = parts[0].lstrip("#")
            channel = discord.utils.get(ctx.guild.text_channels, name=channel_name) if ctx.guild else None
            if len(parts) > 1:
                reason = parts[1]
        else:
            reason = args

    if channel is None:
        channel = bot.get_channel(1514173159052415026)
    if channel is None and isinstance(ctx.channel, discord.TextChannel):
        channel = ctx.channel
    shutdown_text = f"🔌 {reason}"
    shutdown_embed = discord.Embed(
        title="Bot Shutdown Initiated",
        description=shutdown_text,
        color=discord.Color.light_gray()
    )

    published = False
    if channel is not None:
        try:
            sent_msg = await channel.send(embed=shutdown_embed)
            if channel.type == discord.ChannelType.news:
                try:
                    await sent_msg.publish()
                    published = True
                except Exception:
                    published = False
        except discord.Forbidden as error:
            add_bot_error_entry(ctx.guild.id if ctx.guild else None, channel.id, ctx.author, "shutdown notice", error)
            await ctx.send(f"<:disapprove:1517452151012589662> Could not send the shutdown notice to {channel.mention}.")
            return
        except Exception as e:
            await ctx.send(f"<:disapprove:1517452151012589662> Could not send the shutdown notice to {channel.mention}. Error: {e}")
            return

    if update_presence.is_running():
        update_presence.cancel()
        await asyncio.sleep(1)

    response_text = "Going to sleep..."
    if channel is not None:
        response_text = (
            f"<:nUtils:1518376146008539146> Bot is shutting down."
        )

    await ctx.send(response_text)

    shutdown_activity = discord.Activity(type=discord.ActivityType.watching, name="App is shutting down!!! !! !")
    sleep_activity = discord.Activity(type=discord.ActivityType.watching, name="App is sleeping... zZzZzZ")
    for shard_id in bot.shards:
        await bot.change_presence(activity=shutdown_activity, status=discord.Status.dnd, shard_id=shard_id)
    await asyncio.sleep(10)
    for shard_id in bot.shards:
        await bot.change_presence(activity=sleep_activity, status=discord.Status.idle, shard_id=shard_id)
    await bot.close()


class ServersListView(LayoutView):
    def __init__(self, user_id: int, guilds: list[discord.Guild], page: int = 1):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guilds = guilds
        self.page = page
        self.message: discord.Message | None = None
        self.guilds_per_page = 5
        self.build_components()

    def build_components(self):
        self.clear_items()
        total_servers = len(self.guilds)
        total_pages = max(1, math.ceil(total_servers / self.guilds_per_page))
        current_page = min(max(1, self.page), total_pages)
        start_index = (current_page - 1) * self.guilds_per_page
        page_guilds = self.guilds[start_index:start_index + self.guilds_per_page]

        container_items = [
            TextDisplay("💻 **Bot Servers**"),
            TextDisplay(f"Page {current_page}/{total_pages} · {total_servers} server(s) available."),
            Separator(),
        ]

        if not page_guilds:
            container_items.append(TextDisplay("No servers found."))
        else:
            for index, guild in enumerate(page_guilds, start=start_index + 1):
                row_text = f"{index}. **{guild.name}**\nMembers: {guild.member_count} · ID: `{guild.id}`"
                invite_button = Button(label="Invite", style=discord.ButtonStyle.primary, custom_id=f"server_invite_{guild.id}")

                async def invite_callback(interaction: discord.Interaction, guild_to_invite: discord.Guild = guild):
                    await self.generate_guild_invite(interaction, guild_to_invite)

                invite_button.callback = invite_callback
                container_items.append(Section(row_text, accessory=invite_button))

        self.add_item(Container(*container_items, accent_color=discord.Color.blurple()))

        prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="server_prev")
        next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="server_next")
        close_button = Button(label="Close", style=discord.ButtonStyle.danger, custom_id="server_close")
        prev_button.callback = self.open_previous_page
        next_button.callback = self.open_next_page
        close_button.callback = self.close_view
        prev_button.disabled = current_page <= 1
        next_button.disabled = current_page >= total_pages

        self.add_item(discord.ui.ActionRow(prev_button, next_button, close_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This server panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def open_previous_page(self, interaction: discord.Interaction):
        new_view = ServersListView(self.user_id, self.guilds, page=self.page - 1)
        new_view.message = interaction.message
        await interaction.response.edit_message(view=new_view)

    async def open_next_page(self, interaction: discord.Interaction):
        new_view = ServersListView(self.user_id, self.guilds, page=self.page + 1)
        new_view.message = interaction.message
        await interaction.response.edit_message(view=new_view)

    async def close_view(self, interaction: discord.Interaction):
        if interaction.message:
            await interaction.message.delete()
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Server list closed.", ephemeral=True)

    async def generate_guild_invite(self, interaction: discord.Interaction, guild: discord.Guild):
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This invite action is only for the original user.", ephemeral=True)
            return

        channel = guild.system_channel
        if channel is None:
            channel = next(
                (c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite),
                None,
            )
        if channel is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:disapprove:1517452151012589662> I could not find a valid invite channel in **{guild.name}**.",
                ephemeral=True,
            )
            return

        try:
            invite = await channel.create_invite(max_age=0, max_uses=0, unique=True)
        except Exception as exc:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:disapprove:1517452151012589662> Failed to create an invite for **{guild.name}**: {exc}",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"Invite for **{guild.name}**: {invite.url}", ephemeral=True)


@bot.command(name="servers")
async def list_servers(ctx: commands.Context):
    if not await bot.is_owner(ctx.author):
        return await ctx.send(F"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    guilds = sorted(bot.guilds, key=lambda g: g.name.lower())
    view = ServersListView(ctx.author.id, guilds)
    message = await ctx.send(view=view)
    view.message = message




# -------------------------------------------------------------------------------------------------------------
#                                               Personalization Commands
# -------------------------------------------------------------------------------------------------------------




USER_COLOR_OPTIONS = ["random"] + [name for name in COLOR_EMOJIS.keys() if name != "black" and name != "random"]


def resolve_user_color_name(color_name: str | None) -> str:
    cleaned = str(color_name or "white").strip().lower()
    if cleaned == "random":
        palette = [name for name in USER_COLOR_OPTIONS if name != "random"]
        return random.choice(palette) if palette else "white"
    return cleaned if cleaned in COLOR_EMOJIS or cleaned in {"white", "black", "red", "blue", "green", "yellow", "purple", "orange", "brown"} else "white"


def get_user_color_value(user_id: str) -> discord.Color:
    settings = load_user_settings()
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


class SettingsMenuView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, username: str, color: discord.Color):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.username = username
        self.color = color
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.user_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="settings_open_user",
        )
        self.guild_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="settings_open_guild",
        )

        async def open_user(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            new_view = UserSettingsView(
                interaction.user.id,
                current_color=user_settings.get("color", "white"),
                current_pings=user_settings.get("user_pings", True),
                current_style=user_settings.get("banner_style", "normal"),
                settings_message=interaction.message,
            )
            await interaction.response.edit_message(view=new_view)

        async def open_guild(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use guild settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            new_view = GuildSettingsMenuView(
                interaction.user.id,
                str(interaction.guild.id),
            )
            await interaction.response.edit_message(view=new_view)

        self.user_button.callback = open_user
        self.guild_button.callback = open_guild

        container = Container(
            TextDisplay(f"<:gear:1517576939097952496> **Settings for {self.username}**"),
            Separator(),
            Section("<:edit:1517497568421085256> User settings", accessory=self.user_button),
            Section("<:drawer:1517497564189036574> Guild settings", accessory=self.guild_button),
            Separator(),
            TextDisplay("Found a bug ? Report it in the [support server](https://discord.gg/FSBPvc9zqY)"),
            accent_color=self.color,
        )
        self.add_item(container)


class NotesMenuView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.notes_button = Button(label="Open", style=discord.ButtonStyle.primary, custom_id="notes_menu_notes")
        self.reminders_button = Button(label="Open", style=discord.ButtonStyle.primary, custom_id="notes_menu_reminders")
        self.checklists_button = Button(label="Open", style=discord.ButtonStyle.primary, custom_id="notes_menu_checklists")

        async def open_notes(interaction: discord.Interaction):
            await interaction.response.edit_message(view=NotesView(self.user_id))

        async def open_reminders(interaction: discord.Interaction):
            await interaction.response.edit_message(view=RemindersView(self.user_id))

        async def open_checklists(interaction: discord.Interaction):
            await interaction.response.edit_message(view=ChecklistView(self.user_id))

        self.notes_button.callback = open_notes
        self.reminders_button.callback = open_reminders
        self.checklists_button.callback = open_checklists
        user = bot.get_user(self.user_id)
        username = user.display_name if user else str(self.user_id)
        self.add_item(Container(
            TextDisplay(f"<:gear:1517576939097952496> **Notes menu for {username}**"),
            Separator(),
            Section("<:edit:1517497568421085256> Notes", accessory=self.notes_button),
            Section("<:list:1517497572770451567> Checklists", accessory=self.checklists_button),            
            Section("<:timer:1517996239583576194> Reminders", accessory=self.reminders_button),
            Separator(),
            TextDisplay("Found a bug ? Report it in the [support server](https://discord.gg/FSBPvc9zqY)"),
            accent_color=get_user_color_value(str(self.user_id)),
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This menu is only for the original user.", ephemeral=True)
            return False
        return True


class NotesView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, note_index: int = 0):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.note_index = max(0, min(note_index, MAX_USER_NOTES - 1))
        self.notes = get_user_notes(str(self.user_id))
        self.build_components()

    def build_components(self):
        self.clear_items()
        current_note = self.notes[self.note_index] if self.note_index < len(self.notes) else ""
        note_text = current_note or "*No note written yet.*"

        self.edit_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="notes_edit")
        self.share_button = Button(label="Share", style=discord.ButtonStyle.success, custom_id="notes_share", disabled=not bool(current_note.strip()))
        self.cycle_button = Button(label="Next note", style=discord.ButtonStyle.secondary, custom_id="notes_cycle")
        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="notes_back")

        async def edit_note(interaction: discord.Interaction):
            await interaction.response.send_modal(NoteEditModal(self.user_id, self.note_index, current_note))

        async def share_note(interaction: discord.Interaction):
            if interaction.guild and await run_automod_check_for_interaction(interaction, note_text, source_label="/share-note"):
                return
            owner = bot.get_user(self.user_id)
            owner_name = owner.display_name if owner else str(self.user_id)
            await interaction.response.defer(); await interaction.followup.send(
                view=SharedNoteView(self.user_id, owner_name, note_text),
                ephemeral=False,
            )

        async def cycle_note(interaction: discord.Interaction):
            new_index = (self.note_index + 1) % MAX_USER_NOTES
            await interaction.response.edit_message(view=NotesView(self.user_id, new_index))

        async def back_to_menu(interaction: discord.Interaction):
            await interaction.response.edit_message(view=NotesMenuView(self.user_id))

        self.edit_button.callback = edit_note
        self.share_button.callback = share_note
        self.cycle_button.callback = cycle_note
        self.back_button.callback = back_to_menu

        self.add_item(Container(
            TextDisplay(get_notes_header(self.user_id)),
            Separator(),
            TextDisplay(note_text),
            accent_color=get_user_color_value(str(self.user_id)),
        ))
        self.add_item(discord.ui.ActionRow(self.edit_button, self.share_button, self.cycle_button, self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This notes panel is only for the original user.", ephemeral=True)
            return False
        return True


class NoteEditModal(Modal):
    def __init__(self, user_id: int, note_index: int, current_text: str = ""):
        super().__init__(title="Edit Note")
        self.user_id = user_id
        self.note_index = note_index
        self.note_input = TextInput(
            label="Note",
            style=discord.TextStyle.long,
            default=current_text,
            required=False,
            max_length=1000,
        )
        self.add_item(self.note_input)

    async def on_submit(self, interaction: discord.Interaction):
        notes = get_user_notes(str(self.user_id))
        while len(notes) < MAX_USER_NOTES:
            notes.append("")
        notes[self.note_index] = self.note_input.value.strip()
        save_user_notes(str(self.user_id), notes)
        await interaction.response.edit_message(view=NotesView(self.user_id, self.note_index))


class SharedNoteView(TimeoutDisabledLayoutView):
    def __init__(self, owner_id: int, owner_name: str, note_text: str):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.owner_name = owner_name
        self.note_text = note_text
        self.build_components()

    def build_components(self):
        self.clear_items()
        title = f"<:edit:1517497568421085256> {self.owner_name}'s Note"
        self.add_item(Container(
            TextDisplay(title),
            Separator(),
            TextDisplay(self.note_text or "*No note written yet.*"),
            accent_color=get_user_color_value(str(self.owner_id)),
        ))


class SharedChecklistView(TimeoutDisabledLayoutView):
    def __init__(self, owner_id: int, owner_name: str, item_lines: list[str]):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.owner_name = owner_name
        self.item_lines = item_lines or ["No list items yet."]
        self.build_components()

    def build_components(self):
        self.clear_items()
        title = f"<:list:1517497572770451567> {self.owner_name}'s Checklist"
        self.add_item(Container(
            TextDisplay(title),
            Separator(),
            TextDisplay("\n".join(self.item_lines)),
            accent_color=get_user_color_value(str(self.owner_id)),
        ))


class ReminderModal(Modal):
    def __init__(self, user_id: int, settings_message: discord.Message, existing_index: int | None = None):
        title = "Edit Reminder" if existing_index is not None else "Create Reminder"
        super().__init__(title=title)
        self.user_id = user_id
        self.settings_message = settings_message
        self.existing_index = existing_index
        self.name_input = TextInput(label="Reminder name", placeholder="Brief title", required=True, max_length=100)
        self.description_input = TextInput(label="Reminder description", style=discord.TextStyle.long, required=False, max_length=400)
        self.time_input = TextInput(label="Reminder time", placeholder="Examples: 1h, 30m, 10:00, 20/02, 20/02 23:00, 20/02/2010 23:00", required=True)
        self.repeat_input = TextInput(label="Repeat interval (optional)", placeholder="Examples: 2h, 30d 20m — leave blank for no repeat", required=False)
        self.add_item(self.name_input)
        self.add_item(self.description_input)
        self.add_item(self.time_input)
        self.add_item(self.repeat_input)

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip() or "Reminder"
        description = self.description_input.value.strip()
        when = parse_reminder_time(self.time_input.value, str(self.user_id))
        repeat_seconds = None
        repeat_value = (self.repeat_input.value or "").strip()
        if repeat_value:
            repeat_seconds = parse_duration_to_seconds(repeat_value)
            if repeat_seconds is None:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid repeat interval. Examples: '1h', '30m', '2d 3h'.", ephemeral=True)
                return

                                                                                   
        if self.existing_index is not None and repeat_seconds is None:
            try:
                existing_reminders = get_user_reminders(str(self.user_id))
                if 0 <= self.existing_index < len(existing_reminders):
                    existing_repeat = existing_reminders[self.existing_index].get("repeat")
                    if isinstance(existing_repeat, int) and existing_repeat > 0:
                        repeat_seconds = int(existing_repeat)
            except Exception:
                pass

        if when is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid reminder time. Examples: '1h', '30m', '10:00', '20/02', '20/02 23:00', '20/02/2010 23:00'.", ephemeral=True)
            return

        reminder = {
            "name": name,
            "description": description,
            "when": when,
            "send": "dm",
        }
        if repeat_seconds:
            reminder["repeat"] = int(repeat_seconds)

        if self.existing_index is None and not can_add_user_reminder(str(self.user_id)):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                "<:disapprove:1517452151012589662> You can have up to 7 reminders at once.",
                ephemeral=True,
            )
            return

        reminders = get_user_reminders(str(self.user_id))
        if self.existing_index is None:
            reminders.append(reminder)
            saved_text = f"<:approve:1517452125687513158> Reminder saved for <t:{when}:F>."
        else:
            if 0 <= self.existing_index < len(reminders):
                reminders[self.existing_index] = reminder
            saved_text = f"<:approve:1517452125687513158> Reminder updated for <t:{when}:F>."
        save_user_reminders(str(self.user_id), reminders)
        try:
            await interaction.response.edit_message(view=RemindersView(self.user_id))
        except Exception:
            try:
                await self.settings_message.edit(view=RemindersView(self.user_id))
            except Exception:
                pass
        await safe_send(interaction, saved_text, ephemeral=True)


class RemindersView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.reminders = get_user_reminders(str(user_id))
        self.build_components()


class ReminderActionModal(Modal):
    def __init__(self, user_id: int, settings_message: discord.Message, action: str):
        title = "Edit reminder" if action == "edit" else "Delete reminder"
        super().__init__(title=title)
        self.user_id = user_id
        self.settings_message = settings_message
        self.action = action
        self.reminder_input = TextInput(label="Reminder number or name", placeholder="1 or reminder name", required=True, max_length=100)
        self.add_item(self.reminder_input)

    async def on_submit(self, interaction: discord.Interaction):
        reminders = get_user_reminders(str(self.user_id))
        if not reminders:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You have no reminders yet.", ephemeral=True)
            return

        index = find_reminder_index(reminders, self.reminder_input.value)
        if index is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Reminder not found. Use number or exact name.", ephemeral=True)
            return

        if self.action == "delete":
            reminders.pop(index)
            save_user_reminders(str(self.user_id), reminders)
            try:
                await interaction.response.edit_message(view=RemindersView(self.user_id))
            except Exception:
                try:
                    await self.settings_message.edit(view=RemindersView(self.user_id))
                except Exception:
                    pass
            await safe_send(interaction, "<:trash:1517497581058527404> Reminder deleted.", ephemeral=True)
            return

        reminder = reminders[index]
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Reminder found. Click below to continue editing.",
            view=ReminderEditLaunchView(self.user_id, self.settings_message, index, reminder),
            ephemeral=True,
        )


class ReminderShareModal(Modal):
    def __init__(self, user_id: int, settings_message: discord.Message):
        super().__init__(title="Share reminder")
        self.user_id = user_id
        self.settings_message = settings_message
        self.reminder_input = TextInput(label="Reminder number or name", placeholder="1 or reminder name", required=True, max_length=100)
        self.add_item(self.reminder_input)

    async def on_submit(self, interaction: discord.Interaction):
        reminders = get_user_reminders(str(self.user_id))
        if not reminders:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You have no reminders yet.", ephemeral=True)
            return

        index = find_reminder_index(reminders, self.reminder_input.value)
        if index is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Reminder not found. Use number or exact name.", ephemeral=True)
            return

        reminder = reminders[index]
        destination = get_reminder_destination(reminder, interaction.guild)
        reminder_text = get_reminder_message_text(reminder)
        reminder_name = reminder.get("name", "Reminder")

        owner = bot.get_user(self.user_id)
        creator_name = owner.display_name if owner else str(self.user_id)
        reminder_text = f"{reminder.get('name', '')} {reminder.get('description', '')}"
        if interaction.guild and await run_automod_check_for_interaction(interaction, reminder_text, source_label="/share-reminder"):
            return
        await interaction.response.defer(); await interaction.followup.send(
            view=SharedReminderView(self.user_id, creator_name, reminder),
            ephemeral=False,
        )


class SharedReminderView(TimeoutDisabledLayoutView):
    def __init__(self, owner_id: int, creator_name: str, reminder: dict):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.creator_name = creator_name
        self.reminder = reminder
        self.save_button = Button(label="Add to personal reminders", style=discord.ButtonStyle.primary, custom_id="shared_reminder_add")
        self.save_button.callback = self.add_reminder
        self.build_components()

    def build_components(self):
        self.clear_items()
        title = self.reminder.get("name", "Reminder")
        description = self.reminder.get("description", "").strip() or "No description provided."
        when = get_reminder_display(self.reminder)
        destination = get_reminder_destination(self.reminder, None)

        repeat_text = get_reminder_repeat_text(self.reminder)
        info_lines = [
            TextDisplay(f"When: {when}"),
            TextDisplay(f"Repeats: {repeat_text}"),
        ]
        if destination:
            info_lines.insert(1, TextDisplay(f"Destination: {destination}"))
        info_lines.append(TextDisplay(f"Reminder creator: {self.creator_name}"))

        self.add_item(Container(
            TextDisplay(f"<:timer:1517996239583576194> {title}"),
            TextDisplay(description),
            Separator(),
            *info_lines,
            accent_color=get_user_color_value(str(self.owner_id)),
        ))
        self.add_item(discord.ui.ActionRow(self.save_button))

    async def add_reminder(self, interaction: discord.Interaction):
        user_reminders = get_user_reminders(str(interaction.user.id))
        if len(user_reminders) >= MAX_USER_REMINDERS:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                "<:disapprove:1517452151012589662> You can have up to 7 reminders at once.",
                ephemeral=True,
            )
            return

        if any(
            existing.get("name") == self.reminder.get("name")
            and existing.get("when") == self.reminder.get("when")
            and existing.get("send") == self.reminder.get("send")
            and existing.get("description", "") == self.reminder.get("description", "")
            and existing.get("channel_id") == self.reminder.get("channel_id")
            for existing in user_reminders
        ):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> This reminder is already in your personal reminders.", ephemeral=True)
            return

        reminder_copy = self.reminder.copy()
        original_description = reminder_copy.get("description", "").strip()
        if original_description:
            reminder_copy["description"] = f"{original_description} (by {self.creator_name})"
        else:
            reminder_copy["description"] = f"by {self.creator_name}"

        user_reminders.append(reminder_copy)
        save_user_reminders(str(interaction.user.id), user_reminders)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Reminder added to your personal reminders.", ephemeral=True)


class ReminderEditLaunchView(TimeoutDisabledView):
    def __init__(self, user_id: int, settings_message: discord.Message, index: int, reminder: dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.settings_message = settings_message
        self.index = index
        self.reminder = reminder

        self.open_button = Button(label="Open edit modal", style=discord.ButtonStyle.primary, custom_id="open_reminder_edit")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_reminder_edit")

        self.open_button.callback = self.open_edit
        self.cancel_button.callback = self.cancel

        self.add_item(self.open_button)
        self.add_item(self.cancel_button)

    async def open_edit(self, interaction: discord.Interaction):
        modal = ReminderModal(self.user_id, self.settings_message, existing_index=self.index)
        modal.name_input.default = self.reminder.get("name", "")
        modal.description_input.default = self.reminder.get("description", "")
        reminder_when = self.reminder.get("when")
        if isinstance(reminder_when, int):
            try:
                                                                   
                offs = None
                try:
                    settings = load_user_settings()
                    entry = get_user_settings_entry(settings, str(self.user_id))
                    off = entry.get("timezone_offset")
                    offs = parse_utc_offset(off) if off else None
                except Exception:
                    offs = None
                utc_dt = datetime.utcfromtimestamp(reminder_when)
                if offs is not None:
                    local_dt = utc_dt + offs
                else:
                    local_dt = utc_dt
                modal.time_input.default = f"{local_dt:%d/%m/%Y %H:%M}"
            except (OSError, OverflowError, ValueError):
                modal.time_input.default = str(reminder_when)
        else:
            modal.time_input.default = str(reminder_when)
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Reminder edit cancelled.", ephemeral=True)


class RemindersView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.reminders = get_user_reminders(str(user_id))
        self.build_components()

    def build_components(self):
        self.clear_items()
        reminder_lines = []
        for index, reminder in enumerate(self.reminders):
            reminder_lines.append(f"{index + 1}. {reminder.get('name', 'Reminder')} : {get_reminder_display(reminder)}")
            repeat_text = get_reminder_repeat_text(reminder)
            reminder_lines.append(f"Repeats: {repeat_text}")
            if reminder.get("description"):
                reminder_lines.append(reminder.get("description", ""))
            reminder_lines.append("")

        notice = "No reminders set yet." if not reminder_lines else "\n".join(reminder_lines)

        self.create_button = Button(label="Create", style=discord.ButtonStyle.success, custom_id="reminder_create")
        self.edit_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="reminder_edit", disabled=not bool(self.reminders))
        self.delete_button = Button(label="Delete", style=discord.ButtonStyle.danger, custom_id="reminder_delete", disabled=not bool(self.reminders)) 
        self.share_button = Button(label="Share", style=discord.ButtonStyle.success, custom_id="reminder_share", disabled=not bool(self.reminders))
        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="reminder_back")

        async def create_reminder(interaction: discord.Interaction):
            await interaction.response.send_modal(ReminderModal(self.user_id, interaction.message))        

        async def edit_reminder(interaction: discord.Interaction):
            await interaction.response.send_modal(ReminderActionModal(self.user_id, interaction.message, action="edit"))

        async def delete_reminder(interaction: discord.Interaction):
            await interaction.response.send_modal(ReminderActionModal(self.user_id, interaction.message, action="delete"))

        async def share_reminder(interaction: discord.Interaction):
            await interaction.response.send_modal(ReminderShareModal(self.user_id, interaction.message))

        async def back_to_menu(interaction: discord.Interaction):
            await interaction.response.edit_message(view=NotesMenuView(self.user_id))

        self.create_button.callback = create_reminder
        self.edit_button.callback = edit_reminder
        self.delete_button.callback = delete_reminder
        self.share_button.callback = share_reminder
        self.back_button.callback = back_to_menu

        self.add_item(Container(
            TextDisplay(get_reminders_header(self.user_id)),
            Separator(),
            TextDisplay(notice),
            accent_color=get_user_color_value(str(self.user_id)),
        ))
        self.add_item(discord.ui.ActionRow(self.create_button, self.edit_button, self.delete_button, self.share_button, self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This reminders panel is only for the original user.", ephemeral=True)
            return False
        return True


class ChecklistView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, page: int = 0):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.page = max(0, page)
        self.lists = get_user_lists(str(self.user_id))
        self.items = self.lists[0] if self.lists and isinstance(self.lists[0], list) else []
        self.build_components()

    def build_components(self):
        self.clear_items()
        item_lines = [format_checklist_item(item, idx) for idx, item in enumerate(self.items)]
        if not item_lines:
            item_lines = ["No list items yet."]

        self.edit_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="checklist_edit")
        self.share_button = Button(label="Share", style=discord.ButtonStyle.success, custom_id="checklist_share", disabled=not bool(self.items))
        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="checklist_back")

        async def edit_list(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                view=ChecklistActionView(self.user_id, self.page, interaction.message),
                ephemeral=True,
            )

        async def share_list(interaction: discord.Interaction):
            share_text = "\n".join(item_lines)
            if interaction.guild and await run_automod_check_for_interaction(interaction, share_text, source_label="/share-list"):
                return
            owner = bot.get_user(self.user_id)
            owner_name = owner.display_name if owner else str(self.user_id)
            await interaction.response.defer(); await interaction.followup.send(
                view=SharedChecklistView(self.user_id, owner_name, item_lines),
                ephemeral=False,
            )

        async def back_to_menu(interaction: discord.Interaction):
            await interaction.response.edit_message(view=NotesMenuView(self.user_id))

        self.edit_button.callback = edit_list
        self.share_button.callback = share_list
        self.back_button.callback = back_to_menu

        header_text = f"<:list:1517497572770451567> Lists for {bot.get_user(self.user_id).display_name if bot.get_user(self.user_id) else str(self.user_id)}"
        self.add_item(Container(
            TextDisplay(header_text),
            Separator(),
            TextDisplay("\n".join(item_lines)),
            accent_color=get_user_color_value(str(self.user_id)),
        ))
        self.add_item(discord.ui.ActionRow(self.edit_button, self.share_button, self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This checklist panel is only for the original user.", ephemeral=True)
            return False
        return True


class ChecklistActionView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.page = page
        self.settings_message = settings_message
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="checklist_add")
        self.mark_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="checklist_edit")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="checklist_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="checklist_cancel")

        async def add_item(interaction: discord.Interaction):
            await interaction.response.send_modal(ChecklistAddModal(self.user_id, self.page, self.settings_message))

        async def mark_item(interaction: discord.Interaction):
            await interaction.response.send_modal(ChecklistMarkModal(self.user_id, self.page, self.settings_message))

        async def remove_item(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                view=ChecklistRemoveChoiceView(self.user_id, self.page, self.settings_message),
                ephemeral=True,
            )

        async def cancel(interaction: discord.Interaction):
            self.add_button.disabled = True
            self.mark_button.disabled = True
            self.remove_button.disabled = True
            self.cancel_button.disabled = True
            await interaction.response.edit_message(view=self)

        self.add_button.callback = add_item
        self.mark_button.callback = mark_item
        self.remove_button.callback = remove_item
        self.cancel_button.callback = cancel

        self.add_item(discord.ui.ActionRow(self.add_button, self.mark_button, self.remove_button, self.cancel_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This checklist menu is only for the original user.", ephemeral=True)
            return False
        return True


async def refresh_checklist_message(interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
    if settings_message is None:
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except (discord.NotFound, discord.HTTPException):
                settings_message = None
    if settings_message is None:
        return
    try:
        await settings_message.edit(view=view)
        return
    except (discord.NotFound, discord.HTTPException):
        pass
    try:
        await interaction.followup.edit_message(message_id=settings_message.id, view=view)
        return
    except Exception:
        pass
    try:
        await interaction.edit_original_response(view=view)
    except Exception:
        pass


class ChecklistAddModal(Modal):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(title="Add checklist item")
        self.user_id = user_id
        self.page = page
        self.settings_message = settings_message
        self.content_input = TextInput(label="Item content", style=discord.TextStyle.long, required=True, max_length=200)
        self.color_input = TextInput(label="Mark color", placeholder="red, yellow, green, none", required=False, max_length=10)
        self.add_item(self.content_input)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        lists = get_user_lists(str(self.user_id))
        item_list = lists[0]
        if len(item_list) >= MAX_USER_LIST_ITEMS:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You already have the maximum of 30 items.", ephemeral=True)
            return
        color = self.color_input.value.strip().lower()
        if color == "":
            color = "none"
        if color not in {"red", "yellow", "green", "none"}:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Use red, yellow, green, or none.", ephemeral=True)
            return
        item_list.append({"content": self.content_input.value.strip(), "status": color})
        save_user_lists(str(self.user_id), lists)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Checklist item added.", ephemeral=True)
        await refresh_checklist_message(interaction, ChecklistView(self.user_id, self.page), self.settings_message)


class ChecklistMarkModal(Modal):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(title="Edit checklist item")
        self.user_id = user_id
        self.page = page
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item ID or name to edit", required=True, max_length=100)
        self.content_input = TextInput(label="New content", style=discord.TextStyle.long, required=False, max_length=200)
        self.color_input = TextInput(label="Mark color", placeholder="red, yellow, green, remove", required=False, max_length=10)
        self.add_item(self.item_input)
        self.add_item(self.content_input)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        lists = get_user_lists(str(self.user_id))
        item_list = lists[0]
        index = find_checklist_item_index(item_list, self.item_input.value)
        if index is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Item not found.", ephemeral=True)
            return
        new_content = self.content_input.value.strip()
        new_color = self.color_input.value.strip().lower()
        if not new_content and not new_color:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Provide new content, a mark color, or both.", ephemeral=True)
            return
        if new_content:
            item_list[index]["content"] = new_content
        if new_color:
            if new_color not in {"red", "yellow", "green", "remove"}:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Use red, yellow, green, or remove.", ephemeral=True)
                return
            item_list[index]["status"] = "none" if new_color == "remove" else new_color
        save_user_lists(str(self.user_id), lists)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Checklist item updated.", ephemeral=True)
        await refresh_checklist_message(interaction, ChecklistView(self.user_id, self.page), self.settings_message)


class ChecklistRemoveChoiceView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.page = page
        self.settings_message = settings_message
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="checklist_remove_single")
        self.clear_button = Button(label="Clear all", style=discord.ButtonStyle.secondary, custom_id="checklist_clear_all")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="checklist_remove_cancel")

        async def remove_single(interaction: discord.Interaction):
            await interaction.response.send_modal(ChecklistRemoveModal(self.user_id, self.page, self.settings_message))

        async def clear_all(interaction: discord.Interaction):
            lists = get_user_lists(str(self.user_id))
            lists[0] = []
            save_user_lists(str(self.user_id), lists)
            await refresh_checklist_message(interaction, ChecklistView(self.user_id, self.page), self.settings_message)
            self.remove_button.disabled = True
            self.clear_button.disabled = True
            self.cancel_button.disabled = True
            await interaction.response.edit_message(view=self)

        async def cancel(interaction: discord.Interaction):
            self.remove_button.disabled = True
            self.clear_button.disabled = True
            self.cancel_button.disabled = True
            await interaction.response.edit_message(view=self)

        self.remove_button.callback = remove_single
        self.clear_button.callback = clear_all
        self.cancel_button.callback = cancel
        self.add_item(discord.ui.ActionRow(self.remove_button, self.clear_button, self.cancel_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This checklist action is only for the original user.", ephemeral=True)
            return False
        return True


class ChecklistRemoveModal(Modal):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(title="Remove checklist item")
        self.user_id = user_id
        self.page = page
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item ID or name to remove", required=True, max_length=100)
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        lists = get_user_lists(str(self.user_id))
        item_list = lists[0]
        index = find_checklist_item_index(item_list, self.item_input.value)
        if index is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Item not found.", ephemeral=True)
            return
        item_list.pop(index)
        save_user_lists(str(self.user_id), lists)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:trash:1517497581058527404> Checklist item removed.", ephemeral=True)
        await refresh_checklist_message(interaction, ChecklistView(self.user_id, self.page), self.settings_message)


class UserSettingsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, current_color: str, current_pings: bool, current_style: str = "normal", settings_message: discord.Message | None = None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.current_color = current_color or "white"
        self.current_pings = current_pings
        self.current_style = str(current_style or "normal").strip().lower()
        self.settings_message = settings_message
        self.build_components()

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
        if settings_message is None:
            settings_message = self.settings_message or interaction.message
            if settings_message is None:
                try:
                    settings_message = await interaction.original_response()
                except (discord.NotFound, discord.HTTPException):
                    settings_message = None
        if settings_message is None:
            return

        try:
            await settings_message.edit(view=view)
            return
        except (discord.NotFound, discord.HTTPException):
            pass

        try:
            channel = bot.get_channel(settings_message.channel.id)
            if channel is not None:
                fresh_message = await channel.fetch_message(settings_message.id)
                await fresh_message.edit(view=view)
                return
        except Exception:
            pass

        try:
            await interaction.followup.edit_message(message_id=settings_message.id, view=view)
            return
        except Exception:
            pass

        try:
            await interaction.edit_original_response(view=view)
        except Exception:
            pass

    def build_components(self):
        self.clear_items()
        self.ping_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.secondary,
            custom_id="user_settings_pings",
        )

        async def ping_callback(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            self.current_pings = not self.current_pings
            user_settings["user_pings"] = self.current_pings
            save_user_settings(settings)
            refreshed_view = UserSettingsView(
                self.user_id,
                self.current_color,
                self.current_pings,
                self.current_style,
                settings_message=self.settings_message,
            )
            await interaction.response.edit_message(view=refreshed_view)
            if self.settings_message is not None and self.settings_message.id != interaction.message.id:
                try:
                    await self.settings_message.edit(view=refreshed_view)
                except (discord.NotFound, discord.HTTPException):
                    pass

        self.ping_button.callback = ping_callback

                                 
        try:
            _settings = load_user_settings()
            _entry = get_user_settings_entry(_settings, str(self.user_id))
            _tz_val = _entry.get("timezone_offset")
        except Exception:
            _tz_val = None

        tz_label = "Set"
        self.timezone_button = discord.ui.Button(
            label=tz_label,
            style=discord.ButtonStyle.secondary,
            custom_id="user_settings_timezone",
        )

        async def timezone_callback(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            current = user_settings.get("timezone_offset")
            modal = TimezoneModal(str(interaction.user.id), current, settings_message=self.settings_message)
            try:
                await interaction.response.send_modal(modal)
            except Exception:
                try:
                    await interaction.followup.send("<:disapprove:1517452151012589662> Could not open modal.", ephemeral=True)
                except Exception:
                    pass

        self.timezone_button.callback = timezone_callback

        self.color_select = discord.ui.Select(
            placeholder="Select your profile color",
            options=[
                discord.SelectOption(label="Random", value="random", default=(self.current_color == "random"), description="Use a random color each time")
                if color == "random"
                else discord.SelectOption(label=color.title(), value=color, default=(color == self.current_color), description=f"Use the {color} color")
                for color in USER_COLOR_OPTIONS
            ],
            custom_id="user_settings_color_select",
            min_values=1,
            max_values=1,
        )

        async def color_select_callback(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            selected_color = self.color_select.values[0]
            user_settings["color"] = selected_color
            save_user_settings(settings)
            self.current_color = selected_color

            refreshed_view = UserSettingsView(
                self.user_id,
                selected_color,
                self.current_pings,
                self.current_style,
                settings_message=self.settings_message,
            )
            await interaction.response.edit_message(view=refreshed_view)
            if self.settings_message is not None and self.settings_message.id != interaction.message.id:
                try:
                    await self.settings_message.edit(view=refreshed_view)
                except (discord.NotFound, discord.HTTPException):
                    pass

        self.color_select.callback = color_select_callback

                                                                             
        self.banner_style_select = discord.ui.Select(
            placeholder="Banner styles managed centrally",
            options=[
                discord.SelectOption(label="Random", value="random", default=(str(self.current_style).lower() == "random"), description="Choose a random banner style each time"),
            ],
            custom_id="user_settings_banner_style_select",
            min_values=1,
            max_values=1,
        )

        async def banner_style_select_callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send("Banner styles are now managed centrally via banners.json and cannot be set here.", ephemeral=True)
            except Exception:
                pass

        self.banner_style_select.callback = banner_style_select_callback

        self.back_button = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="user_settings_back")

        async def back_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

        self.back_button.callback = back_callback

                                                                
        banner_open_button = Button(label="Open", style=discord.ButtonStyle.secondary, custom_id="user_settings_banners_open")
        async def banner_open_cb(interaction: discord.Interaction):
            try:
                await interaction.response.edit_message(view=UserBannersView(str(interaction.user.id), settings_message=self.settings_message))
            except Exception:
                try:
                    await interaction.followup.send("Could not open banners panel.", ephemeral=True)
                except Exception:
                    pass
        banner_open_button.callback = banner_open_cb

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **User settings**"),
            TextDisplay("Adjust your personal preferences below."),
            Separator(),
            Section(f"<:bell:1517497562184024275> Ping notifications: {'Enabled' if self.current_pings else 'Disabled'}", accessory=self.ping_button),
            Section(f"<:timer:1517996239583576194> Timezone: {('UTC'+_tz_val) if _tz_val else 'UTC (not set)'}", accessory=self.timezone_button),
                                  
            Section("<:image:1517497571470348539> User banners", accessory=banner_open_button),
            TextDisplay(f"<:rainbow:1518708398772846722> User color: {COLOR_EMOJIS.get(self.current_color, self.current_color)} {self.current_color if isinstance(self.current_color, str) else ''}"),
                                                                
            accent_color=get_user_color_value(str(self.user_id)),
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.color_select))
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True


class TimezoneModal(Modal):
    def __init__(self, user_id: str, current_offset: str | None, settings_message: discord.Message | None = None):
        super().__init__(title="Set timezone offset")
        self.user_id = user_id
        self.settings_message = settings_message
        default = current_offset or "+00:00"
        self.offset_input = TextInput(label="UTC offset (e.g. +02:00, -1:00, +12:30)", placeholder="+02:00", required=False, default=default, max_length=6)
        self.add_item(self.offset_input)

    async def on_submit(self, interaction: discord.Interaction):
        val = (self.offset_input.value or "").strip()
        settings = load_user_settings()
        entry = get_user_settings_entry(settings, str(self.user_id))
        if not val:
                                    
            if entry.get("timezone_offset"):
                entry.pop("timezone_offset", None)
                save_user_settings(settings)
        else:
            offs = parse_utc_offset(val)
            if offs is None:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid timezone format. Use +02:00 or -1:00.", ephemeral=True)
                return
            sign = "-" if offs.total_seconds() < 0 else "+"
            total_minutes = int(abs(int(offs.total_seconds())) // 60)
            hh = total_minutes // 60
            mm = total_minutes % 60
            normalized = f"{sign}{hh:02d}:{mm:02d}"
            entry["timezone_offset"] = normalized
            save_user_settings(settings)

        refreshed = UserSettingsView(int(self.user_id), get_user_color(str(self.user_id)), get_user_pings_enabled(str(self.user_id)), get_user_banner_style(str(self.user_id)), settings_message=self.settings_message)
        try:
            await interaction.response.edit_message(view=refreshed)
        except Exception:
            try:
                if self.settings_message is not None:
                    await self.settings_message.edit(view=refreshed)
            except Exception:
                pass
        try:
            await safe_send(interaction, "<:approve:1517452125687513158> Timezone updated.", ephemeral=True)
        except Exception:
            pass

class UserColorSelectionView(TimeoutDisabledView):
    def __init__(self, user_id: int, current_color: str, settings_message: discord.Message | None = None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.current_color = current_color or "white"
        self.settings_message = settings_message
        self.color_select = discord.ui.Select(
            placeholder="Select a profile color",
            options=[
                discord.SelectOption(label=color.title(), value=color, description=f"Use the {color} color")
                for color in USER_COLOR_OPTIONS
            ],
            custom_id="user_color_select",
            min_values=1,
            max_values=1,
        )

        async def color_select_callback(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            selected_color = self.color_select.values[0]
            user_settings["color"] = selected_color
            save_user_settings(settings)

            refreshed_view = UserSettingsView(
                self.user_id,
                selected_color,
                get_user_pings_enabled(str(self.user_id)),
                get_user_banner_style(str(self.user_id)),
                settings_message=self.settings_message,
            )

            target_message = self.settings_message or interaction.message
            if target_message is not None:
                try:
                    await target_message.edit(view=refreshed_view)
                except (discord.NotFound, discord.HTTPException):
                    pass

            try:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Color updated.", ephemeral=True)
            except Exception:
                try:
                    await interaction.followup.send("<:approve:1517452125687513158> Color updated.", ephemeral=True)
                except Exception:
                    pass

        self.color_select.callback = color_select_callback
        self.cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="user_color_select_cancel")

        async def cancel_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(content="Cancelled.", view=None)

        self.cancel_button.callback = cancel_callback
        self.add_item(self.color_select)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True


class UserBannerStyleSelectionView(TimeoutDisabledView):
    def __init__(self, user_id: int, current_style: str, settings_message: discord.Message | None = None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.current_style = normalize_banner_style(current_style)
        self.settings_message = settings_message
        banner_style_options = [
            discord.SelectOption(label="Normal", value="normal", description="Use the classic banner"),
            discord.SelectOption(label="Alt", value="alt", description="Use the alternate banner"),
            discord.SelectOption(label="1000", value="1000", description="Use the 1000-user milestone banner"),
        ]

        self.banner_style_select = discord.ui.Select(
            placeholder="Select a banner style",
            options=banner_style_options,
            custom_id="user_banner_style_select",
            min_values=1,
            max_values=1,
        )

        async def banner_style_select_callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send("Banner styles are managed via banners.json; selection disabled.", ephemeral=True)
            except Exception:
                pass

        self.banner_style_select.callback = banner_style_select_callback
        self.cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="user_banner_style_select_cancel")

        async def cancel_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(content="Cancelled.", view=None)

        self.cancel_button.callback = cancel_callback
        self.add_item(self.banner_style_select)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True


class BannerSearchModal(Modal):
    def __init__(self, user_id: str, settings_message: discord.Message | None = None):
        super().__init__(title="Search banners")
        self.user_id = user_id
        self.settings_message = settings_message
        self.query = TextInput(label="Banner name or category", placeholder="Try: forest or category:vanilla", required=True, max_length=100)
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        q = (self.query.value or "").strip()
        defs = load_banner_definitions()
        matches = get_banner_search_matches(defs, q)
        if not matches:
            try:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No banners matched that name or category.", ephemeral=True)
            except Exception:
                pass
            return
                                                                             
        options = matches[:6]
        if len(options) == 1:
            chosen = options[0]
            try:
                member = interaction.user
                file = await create_banner_preview(member, kind="welcome", style_override=chosen)
                if file is None:
                    try:
                        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Could not generate preview for this banner.", ephemeral=True)
                    except Exception:
                        pass
                    return
                preview_view = BannerPreviewView(str(self.user_id), chosen, settings_message=self.settings_message)
                try:
                    await interaction.response.send_message(file=file, view=preview_view, ephemeral=True)
                except Exception:
                    try:
                        await interaction.followup.send("Could not open preview.", ephemeral=True)
                    except Exception:
                        pass
            except Exception:
                try:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send("Could not open preview.", ephemeral=True)
                except Exception:
                    pass
            return

                                                            
        view = TimeoutDisabledView()
        for name in options:
            btn = Button(label=name.replace('_',' '), style=discord.ButtonStyle.primary)
            async def sel_cb(inter, chosen=name):
                try:
                    member = inter.user
                    file = await create_banner_preview(member, kind="welcome", style_override=chosen)
                    if file is None:
                        try:
                            await inter.response.defer(ephemeral=True); await inter.followup.send("Could not generate preview for this banner.", ephemeral=True)
                        except Exception:
                            pass
                        return
                    preview_view = BannerPreviewView(str(self.user_id), chosen, settings_message=self.settings_message)
                    try:
                        await inter.response.send_message(file=file, view=preview_view, ephemeral=True)
                    except Exception:
                        try:
                            await inter.followup.send("Could not open preview.", ephemeral=True)
                        except Exception:
                            pass
                except Exception:
                    try:
                        await inter.response.defer(ephemeral=True); await inter.followup.send("Could not open preview.", ephemeral=True)
                    except Exception:
                        pass
            btn.callback = sel_cb
            view.add_item(btn)
        try:
            await interaction.response.send_message("Multiple matches — pick one:", view=view, ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send("Could not present matches.", ephemeral=True)
            except Exception:
                pass


class UserBannersView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: str, page: int = 0, settings_message: discord.Message | None = None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.page = page
        self.settings_message = settings_message
        self.per_page = 6
        self.build_components()

    def build_components(self):
        self.clear_items()
        defs = load_banner_definitions()
        keys = list(defs.keys())
        total_pages = max(1, (len(keys) + self.per_page - 1) // self.per_page)
        start = self.page * self.per_page
        page_items = keys[start:start + self.per_page]

        parts = [
            TextDisplay("## <:image:1517497571470348539> User banners"),
            TextDisplay("Scroll available banners and pick one. Search by name or category."),
            Separator(),
            TextDisplay(f"Page {self.page+1}/{total_pages}"),
        ]

        for name in page_items:
            label = name.replace('_', ' ')
            desc = defs.get(name, {}).get('label') or defs.get(name, {}).get('desc') or ''
            preview_button = Button(label="Preview", style=discord.ButtonStyle.primary, custom_id=f"banner_preview:{name}")

            async def preview_cb(interaction: discord.Interaction, chosen=name):
                try:
                    member = interaction.user
                    file = await create_banner_preview(member, kind="welcome", style_override=chosen)
                    if file is None:
                        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Could not generate preview for this banner.", ephemeral=True)
                        return
                    preview_view = BannerPreviewView(str(self.user_id), chosen, settings_message=self.settings_message)
                    await interaction.response.send_message(file=file, view=preview_view, ephemeral=True)
                except Exception:
                    try:
                        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Could not open preview.", ephemeral=True)
                    except Exception:
                        pass

            preview_button.callback = preview_cb
            parts.append(Section(f"**{label}**\n{desc}", accessory=preview_button))

        parts.append(Separator())
        container = Container(*parts, accent_color=discord.Color.blue())
        self.add_item(container)

        prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="banners_prev", disabled=self.page == 0)
        next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="banners_next", disabled=self.page >= total_pages - 1)
        search_button = Button(label="Search", style=discord.ButtonStyle.primary, custom_id="banners_search")
        cancel_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="banners_cancel")

        async def prev_cb(interaction: discord.Interaction):
            if self.page > 0:
                self.page -= 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        async def next_cb(interaction: discord.Interaction):
            if self.page < total_pages - 1:
                self.page += 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        prev_button.callback = prev_cb
        next_button.callback = next_cb
        async def search_cb(interaction: discord.Interaction):
            try:
                await interaction.response.send_modal(BannerSearchModal(str(interaction.user.id), settings_message=self.settings_message))
            except Exception:
                try:
                    await interaction.followup.send("Could not open search.", ephemeral=True)
                except Exception:
                    pass

        async def cancel_cb(interaction: discord.Interaction):
            try:
                refreshed = UserSettingsView(int(self.user_id), get_user_color(str(self.user_id)), get_user_pings_enabled(str(self.user_id)), get_user_banner_style(str(self.user_id)), settings_message=self.settings_message)
                await interaction.response.edit_message(view=refreshed)
            except Exception:
                try:
                    await interaction.followup.send("Could not return to settings.", ephemeral=True)
                except Exception:
                    pass

        search_button.callback = search_cb
        cancel_button.callback = cancel_cb
        self.add_item(discord.ui.ActionRow(prev_button, next_button, search_button, cancel_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != int(self.user_id):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This panel is only for the original user.", ephemeral=True)
            return False
        return True


class BannerPreviewView(TimeoutDisabledView):
    def __init__(self, user_id: str, style_name: str, settings_message: discord.Message | None = None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.style_name = style_name
        self.settings_message = settings_message
        self.confirm_button = Button(label="Select this banner", style=discord.ButtonStyle.success)
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary)

        async def confirm_cb(interaction: discord.Interaction):
            try:
                settings = load_user_settings()
                entry = get_user_settings_entry(settings, str(self.user_id))
                entry['banner_style'] = self.style_name
                save_user_settings(settings)
                refreshed = UserSettingsView(int(self.user_id), get_user_color(str(self.user_id)), get_user_pings_enabled(str(self.user_id)), get_user_banner_style(str(self.user_id)), settings_message=self.settings_message)
                try:
                    await interaction.response.edit_message(content=f"<:approve:1517452125687513158> Banner set to **{self.style_name.replace('_',' ')}**.", view=None)
                except Exception:
                    try:
                        await interaction.followup.send(f"<:approve:1517452125687513158> Banner set to **{self.style_name.replace('_',' ')}**.", ephemeral=True)
                    except Exception:
                        pass
                                                           
                try:
                    if self.settings_message is not None:
                        await self.settings_message.edit(view=refreshed)
                except Exception:
                    pass
            except Exception:
                try:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Could not set banner.", ephemeral=True)
                except Exception:
                    pass

        async def cancel_cb(interaction: discord.Interaction):
            try:
                await interaction.response.edit_message(content="Canceled.", view=None)
            except Exception:
                try:
                    await interaction.followup.send("Canceled.", ephemeral=True)
                except Exception:
                    pass

        self.confirm_button.callback = confirm_cb
        self.cancel_button.callback = cancel_cb
        self.add_item(self.confirm_button)
                                                                                                  
        self.touch_button = Button(label="Fix mobile preview", style=discord.ButtonStyle.secondary)
        async def touch_cb(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
            except Exception:
                try:
                    await interaction.followup.send("", ephemeral=True)
                except Exception:
                    pass

        self.touch_button.callback = touch_cb
        self.add_item(self.touch_button)
        self.add_item(self.cancel_button)


class GuildSettingsMenuView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, guild_id: str):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.color = get_user_color_value(str(user_id))
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.general_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id=f"guild_settings_menu_general_{self.user_id}",
        )
        self.channel_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id=f"guild_settings_menu_channel_{self.user_id}",
        )
        self.economy_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id=f"guild_settings_menu_economy_{self.user_id}",
        )
        self.level_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id=f"guild_settings_menu_level_{self.user_id}",
        )
        self.automod_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id=f"guild_settings_menu_automod_{self.user_id}",
        )

        async def open_general(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use guild settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            guild_config, _ = get_guild_config(self.guild_id)
            new_view = GuildSettingsView(
                interaction.user.id,
                self.guild_id,
                ghost_pings=guild_config.get("ghost_ping_enabled", False),
                history_enabled=guild_config.get("edit_delete_history_enabled", True),
                economy_enabled=guild_config.get("economy_enabled", True),
                levels_enabled=guild_config.get("levels_enabled", True),
                level_up_enabled=guild_config.get("level_up_message_enabled", False),
                join_dm_enabled=guild_config.get("join_dm_enabled", False),
                join_dm_message=guild_config.get("join_dm_message"),
                join_role_ids=guild_config.get("join_role_ids", []),
            )
            await interaction.response.edit_message(view=new_view)

        async def open_channel_settings(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use channel settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_channels:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Channels permission.",
                    ephemeral=True,
                )
                return

            new_view = ChannelSettingsView(
                interaction.user.id,
                self.guild_id,
                get_user_color_value(str(interaction.user.id)),
            )
            await interaction.response.edit_message(view=new_view)

        async def open_economy_settings(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use economy settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            new_view = EconomySettingsView(
                interaction.user.id,
                self.guild_id,
                get_user_color_value(str(interaction.user.id)),
            )
            await interaction.response.edit_message(view=new_view)

        async def open_level_settings(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use level settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            new_view = LevelSettingsView(
                interaction.user.id,
                self.guild_id,
                get_user_color_value(str(interaction.user.id)),
                settings_message=interaction.message,
            )
            await interaction.response.edit_message(view=new_view)

        async def open_automod_settings(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use automod settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            new_view = AutomodSettingsView(
                interaction.user.id,
                self.guild_id,
                get_user_color_value(str(interaction.user.id)),
            )
            await interaction.response.edit_message(view=new_view)

        async def back_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

        self.general_button.callback = open_general
        self.channel_button.callback = open_channel_settings
        self.economy_button.callback = open_economy_settings
        self.level_button.callback = open_level_settings
        self.automod_button.callback = open_automod_settings

        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id=f"guild_settings_menu_back_{self.user_id}")
        self.back_button.callback = back_callback

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **Guild settings**"),
            TextDisplay("Choose which guild section to configure."),
            Separator(),
            Section("<:edit:1517497568421085256> General settings", accessory=self.general_button),
            Section("<:list:1517497572770451567> Channel settings", accessory=self.channel_button),
            Section("<:money:1517580310395486239> Economy settings", accessory=self.economy_button),
            Section("<:chalice:1517579767573123092> Level settings", accessory=self.level_button),
            Section("<:warning:1517452174991556758> Automod settings", accessory=self.automod_button),
            Separator(),
            TextDisplay("Locked channel setting removed due to not being used and containing bugs"),
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True


class GuildSettingsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, guild_id: str, ghost_pings: bool, history_enabled: bool, economy_enabled: bool = True, levels_enabled: bool = True, level_up_enabled: bool = False, join_dm_enabled: bool = False, join_dm_message: str | None = None, join_role_ids: list[int] | None = None, page: int = 1):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.ghost_pings = ghost_pings
        self.history_enabled = history_enabled
        self.economy_enabled = economy_enabled
        self.levels_enabled = levels_enabled
        self.level_up_enabled = level_up_enabled
        self.join_dm_enabled = join_dm_enabled
        self.join_dm_message = join_dm_message or ""
        self.join_role_ids = list(join_role_ids or [])
        self.page = max(1, min(int(page), 2))
        self.color = get_user_color_value(str(user_id))
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.ghost_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_ghost_pings",
        )
        self.history_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_history",
        )
        self.economy_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_economy",
        )
        self.levels_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_levels",
        )
        self.level_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_level_up",
        )

        async def ghost_callback(interaction: discord.Interaction):
            guild_config, data = get_guild_config(self.guild_id)
            self.ghost_pings = not self.ghost_pings
            guild_config["ghost_ping_enabled"] = self.ghost_pings
            save_guild_data(data)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page))

        async def history_callback(interaction: discord.Interaction):
            guild_config, data = get_guild_config(self.guild_id)
            self.history_enabled = not self.history_enabled
            guild_config["edit_delete_history_enabled"] = self.history_enabled
            save_guild_data(data)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page))

        async def economy_callback(interaction: discord.Interaction):
            guild_config, data = get_guild_config(self.guild_id)
            self.economy_enabled = not self.economy_enabled
            guild_config["economy_enabled"] = self.economy_enabled
            save_guild_data(data)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page))

        async def level_system_callback(interaction: discord.Interaction):
            guild_config, data = get_guild_config(self.guild_id)
            self.levels_enabled = not self.levels_enabled
            guild_config["levels_enabled"] = self.levels_enabled
            save_guild_data(data)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page))

        async def level_callback(interaction: discord.Interaction):
            guild_config, guild_data = get_guild_config(self.guild_id)
            levels = load_levels()
            if self.guild_id not in levels:
                levels[self.guild_id] = {"config": {}}
            config = levels[self.guild_id].get("config", {})

            self.level_up_enabled = not self.level_up_enabled
            guild_config["level_up_message_enabled"] = self.level_up_enabled
            save_guild_data(guild_data)

            config["level_up_message_enabled"] = self.level_up_enabled
            levels[self.guild_id]["config"] = config
            save_levels(levels)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page))

        self.ghost_button.callback = ghost_callback
        self.history_button.callback = history_callback
        self.economy_button.callback = economy_callback
        self.levels_button.callback = level_system_callback
        self.level_button.callback = level_callback

        self.back_button = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="guild_settings_back")

        async def back_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

        self.back_button.callback = back_callback

        fun_data = load_fun_data()
        auto_reply_triggers = sorted(fun_data.get(self.guild_id, {}).keys()) if self.guild_id in fun_data else []
        auto_reply_text = "\n".join(auto_reply_triggers) if auto_reply_triggers else "None"
        join_dm_preview = self.join_dm_message.strip() if self.join_dm_message else "No message set"
        join_role_names = []
        guild = bot.get_guild(int(self.guild_id)) if self.guild_id.isdigit() else None
        if guild is not None:
            for role_id in self.join_role_ids:
                try:
                    role = guild.get_role(int(role_id))
                except (TypeError, ValueError):
                    continue
                if role is not None:
                    join_role_names.append(role.name)
        join_role_preview = ", ".join(join_role_names[:6]) if join_role_names else "None"
        if len(join_role_names) > 6:
            join_role_preview += "..."

        if self.page == 1:
            self.join_dm_edit_button = None
            self.auto_reply_button = None
            self.join_roles_button = None
            page_button = discord.ui.Button(label="Page 2", style=discord.ButtonStyle.secondary, custom_id="guild_settings_next")
            page_button.callback = self.open_page_two
            container_items = [
                TextDisplay("<:gear:1517576939097952496> **General settings**"),
                TextDisplay("Page 1/2 - Adjust the main toggles below."),
                Separator(),
                Section(f"<:ghost:1517497569939558470> Ghost pings: {'Enabled' if self.ghost_pings else 'Disabled'}", accessory=self.ghost_button),
                Section(f"<:trash:1517497581058527404> Edit/Delete history: {'Enabled' if self.history_enabled else 'Disabled'}", accessory=self.history_button),
                Section(f"<:money:1517580310395486239> Economy: {'Enabled' if self.economy_enabled else 'Disabled'}", accessory=self.economy_button),
                Section(f"<:chalice:1517579767573123092> Levels: {'Enabled' if self.levels_enabled else 'Disabled'}", accessory=self.levels_button),
                Section(f"<:spark:1517583248421552305> Level-up and Quest in channel messages: {'Enabled' if self.level_up_enabled else 'Disabled'}", accessory=self.level_button),
            ]
        else:
            self.join_dm_edit_button = discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.primary,
                custom_id="guild_join_dm_edit",
            )
            self.auto_reply_button = discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.primary,
                custom_id="guild_auto_reply",
            )
            self.join_roles_button = discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.primary,
                custom_id="guild_join_roles_edit",
            )
            self.join_dm_edit_button.callback = self.handle_join_dm_edit
            self.auto_reply_button.callback = self.handle_auto_reply_edit
            self.join_roles_button.callback = self.handle_join_roles_edit
            page_button = discord.ui.Button(label="Page 1", style=discord.ButtonStyle.secondary, custom_id="guild_settings_prev")
            page_button.callback = self.open_page_one
            container_items = [
                TextDisplay("<:gear:1517576939097952496> **General settings**"),
                TextDisplay("Page 2/2 - Manage join DM and auto-reply settings below."),
                Separator(),
                Section(f"<:mail:1529115056866984061> Join DM: {'Enabled' if self.join_dm_enabled else 'Disabled'}\n{join_dm_preview}", accessory=self.join_dm_edit_button),
                Section(f"<:spark:1517583248421552305> Auto-reply triggers\n{auto_reply_text}", accessory=self.auto_reply_button),
                Section(f"<:bell:1517497562184024275> Join roles\n{join_role_preview}", accessory=self.join_roles_button),
            ]

        container = Container(*container_items, accent_color=self.color)
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(page_button, self.back_button))

    async def open_page_two(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=2))

    async def open_page_one(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=1))

    async def handle_join_dm_edit(self, interaction: discord.Interaction):
        guild_config, _ = get_guild_config(self.guild_id)
        await interaction.response.send_modal(
            JoinDMModal(
                self.save_join_dm_message,
                self.guild_id,
                guild_config.get("join_dm_enabled", False),
                guild_config.get("join_dm_message"),
                interaction.message,
            )
        )

    async def save_join_dm_message(self, interaction: discord.Interaction, enabled: bool, message: str, settings_message: discord.Message | None = None):
        guild_config, data = get_guild_config(self.guild_id)
        self.join_dm_enabled = enabled
        guild_config["join_dm_enabled"] = enabled
        guild_config["join_dm_message"] = message if message not in (None, "") else None
        save_guild_data(data)
        self.join_dm_message = guild_config["join_dm_message"] or ""
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Join DM settings saved.", ephemeral=True)

        await self.refresh_settings_message(
            interaction,
            GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page),
            settings_message,
        )

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
        if settings_message is None:
            settings_message = interaction.message
            if settings_message is None:
                try:
                    settings_message = await interaction.original_response()
                except (discord.NotFound, discord.HTTPException):
                    settings_message = None
        if settings_message is None:
            return
        try:
            await settings_message.edit(view=view)
            return
        except (discord.NotFound, discord.HTTPException):
            pass

        try:
            channel = bot.get_channel(settings_message.channel.id)
            if channel is not None:
                settings_message = await channel.fetch_message(settings_message.id)
                await settings_message.edit(view=view)
                return
        except Exception:
            pass

        try:
            await interaction.followup.edit_message(message_id=settings_message.id, view=view)
            return
        except Exception:
            pass

        try:
            await interaction.edit_original_response(view=view)
        except Exception:
            pass

    async def get_settings_message(self, channel_id: int, message_id: int) -> discord.Message | None:
        channel = bot.get_channel(channel_id)
        if channel is None:
            return None

        try:
            return await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def handle_auto_reply_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message or await interaction.original_response()
        if settings_message is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Unable to determine the settings message.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Auto-reply triggers?",
            view=AutoReplyChoiceView(
                self.user_id,
                self.open_auto_reply_add,
                self.open_auto_reply_remove,
                settings_message,
            ),
            ephemeral=True,
        )

    async def handle_join_roles_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message or await interaction.original_response()
        if settings_message is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Unable to determine the settings message.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Join roles?",
            view=JoinRoleChoiceView(
                self.user_id,
                self.open_join_role_add,
                self.open_join_role_remove,
                settings_message,
            ),
            ephemeral=True,
        )

    async def open_auto_reply_add(self, interaction: discord.Interaction, settings_message: discord.Message | None):
        await interaction.response.send_modal(AutoReplyAddModal(self.add_auto_reply, self.guild_id, settings_message))

    async def open_auto_reply_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None):
        await interaction.response.send_modal(AutoReplyRemoveModal(self.remove_auto_reply, self.guild_id, settings_message))

    async def open_join_role_add(self, interaction: discord.Interaction, settings_message: discord.Message | None):
        if not interaction.guild:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action needs a guild context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select a role to add as a join role.",
            view=JoinRoleSelectionView(self.user_id, interaction.guild, "Choose a role to add", self.add_join_role, settings_message),
            ephemeral=True,
        )

    async def open_join_role_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None):
        if not interaction.guild:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action needs a guild context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select a role to remove from the join roles.",
            view=JoinRoleSelectionView(self.user_id, interaction.guild, "Choose a role to remove", self.remove_join_role, settings_message),
            ephemeral=True,
        )

    async def add_join_role(self, interaction: discord.Interaction, role_id: int, settings_message: discord.Message | None):
        guild_config, data = get_guild_config(self.guild_id)
        existing_role_ids = list(guild_config.get("join_role_ids", []))
        if role_id not in existing_role_ids:
            existing_role_ids.append(role_id)
            guild_config["join_role_ids"] = existing_role_ids
            save_guild_data(data)
            self.join_role_ids = existing_role_ids
            await interaction.followup.send("<:approve:1517452125687513158> Join role added.", ephemeral=True)
        else:
            await interaction.followup.send("<:disapprove:1517452151012589662> That role is already configured as a join role.", ephemeral=True)

        await self.refresh_settings_message(
            interaction,
            GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page),
            settings_message,
        )

    async def remove_join_role(self, interaction: discord.Interaction, role_id: int, settings_message: discord.Message | None):
        guild_config, data = get_guild_config(self.guild_id)
        existing_role_ids = list(guild_config.get("join_role_ids", []))
        updated_role_ids = [existing_id for existing_id in existing_role_ids if existing_id != role_id]
        if updated_role_ids != existing_role_ids:
            guild_config["join_role_ids"] = updated_role_ids
            save_guild_data(data)
            self.join_role_ids = updated_role_ids
            await interaction.followup.send("<:trash:1517497581058527404> Join role removed.", ephemeral=True)
        else:
            await interaction.followup.send("<:disapprove:1517452151012589662> That role was not configured as a join role.", ephemeral=True)

        await self.refresh_settings_message(
            interaction,
            GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page),
            settings_message,
        )

    async def add_auto_reply(self, interaction: discord.Interaction, word: str, replies: list[str], settings_message: discord.Message | None):
        fun_data = load_fun_data()
        if self.guild_id not in fun_data:
            fun_data[self.guild_id] = {}
        fun_data[self.guild_id][word.lower()] = replies
        save_fun_data(fun_data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Auto reply for '{word}' saved.", ephemeral=True)

        await self.refresh_settings_message(
            interaction,
            GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page),
            settings_message,
        )

    async def remove_auto_reply(self, interaction: discord.Interaction, word: str, settings_message: discord.Message | None):
        fun_data = load_fun_data()
        if self.guild_id in fun_data and word.lower() in fun_data[self.guild_id]:
            del fun_data[self.guild_id][word.lower()]
            if not fun_data[self.guild_id]:
                del fun_data[self.guild_id]
            save_fun_data(fun_data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Auto reply for '{word}' removed.", ephemeral=True)

            await self.refresh_settings_message(
                interaction,
                GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page),
                settings_message,
            )
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No auto reply found for '{word}'.", ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True


class JoinDMModal(Modal):
    def __init__(self, callback, guild_id: str, current_enabled: bool, current_message: str | None, settings_message: discord.Message | None):
        super().__init__(title="Join DM settings")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.enabled_input = TextInput(
            label="Enabled (enable/disable)",
            placeholder="Type enable or disable",
            required=True,
            max_length=10,
            default="enable" if current_enabled else "disable",
        )
        self.message_input = TextInput(
            label="Join DM message",
            placeholder="Use {user} for the member mention or {guild} for the server name.\nYou can add new lines here.",
            required=False,
            max_length=4000,
            default=current_message or "",
            style=discord.TextStyle.long,
        )
        self.add_item(self.enabled_input)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        enabled_value = self.enabled_input.value.strip().lower()
        if enabled_value in {"enable", "enabled", "on", "true", "yes", "1"}:
            enabled = True
        elif enabled_value in {"disable", "disabled", "off", "false", "no", "0"}:
            enabled = False
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please enter either enable or disable for the state.", ephemeral=True)
            return
        await self.callback(interaction, enabled, self.message_input.value, self.settings_message)


class ConfirmRemoveView(TimeoutDisabledView):
    def __init__(self, user_id: int, confirm_callback, original_message: discord.Message):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.confirm_callback = confirm_callback
        self.original_message = original_message
        self.confirm_button = Button(label="Confirm", style=discord.ButtonStyle.danger, custom_id="confirm_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_remove")
        self.confirm_button.callback = self.on_confirm
        self.cancel_button.callback = self.on_cancel
        self.add_item(self.confirm_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This confirmation is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_confirm(self, interaction: discord.Interaction):
        self.confirm_button.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
        await self.confirm_callback(interaction, self.original_message)

    async def on_cancel(self, interaction: discord.Interaction):
        self.confirm_button.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class ChannelSelectorView(TimeoutDisabledView):
    def __init__(self, user_id: int, guild: discord.Guild, placeholder: str, callback, settings_message: discord.Message):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild = guild
        self.callback = callback
        self.settings_message = settings_message
        self.channel_select = ChannelSelect(placeholder=placeholder, custom_id="channel_selector", min_values=1, max_values=1)
        self.channel_select.callback = self.on_channel_selected
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="channel_select_cancel")
        self.cancel_button.callback = self.on_cancel
        self.add_item(self.channel_select)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_channel_selected(self, interaction: discord.Interaction):
        if not self.channel_select.values:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No channel was selected.", ephemeral=True)
            return

        channel = self.channel_select.values[0]
        self.channel_select.disabled = True
        self.cancel_button.disabled = True
        await self.callback(interaction, channel, self.settings_message)
        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass

    async def on_cancel(self, interaction: discord.Interaction):
        self.channel_select.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(content="Channel selection cancelled.", view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class YesNoView(TimeoutDisabledView):
    def __init__(self, user_id: int, yes_callback, no_callback):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.yes_callback = yes_callback
        self.no_callback = no_callback
        self.yes_button = Button(label="Yes", style=discord.ButtonStyle.success, custom_id="yes_option")
        self.no_button = Button(label="No", style=discord.ButtonStyle.danger, custom_id="no_option")
        self.yes_button.callback = self.on_yes
        self.no_button.callback = self.on_no
        self.add_item(self.yes_button)
        self.add_item(self.no_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_yes(self, interaction: discord.Interaction):
        self.yes_button.disabled = True
        self.no_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
        await self.yes_callback(interaction)

    async def on_no(self, interaction: discord.Interaction):
        self.yes_button.disabled = True
        self.no_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
        await self.no_callback(interaction)


class BoardCountPromptView(TimeoutDisabledView):
    def __init__(self, user_id: int, channel: discord.abc.GuildChannel, emoji: str, settings_message: discord.Message, callback):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.channel = channel
        self.emoji = emoji
        self.settings_message = settings_message
        self.callback = callback
        self.count_button = Button(label="Set required count", style=discord.ButtonStyle.primary, custom_id="board_set_count")
        self.count_button.callback = self.on_set_count
        self.add_item(self.count_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_set_count(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BoardCountModal(self.callback, self.channel, self.emoji, self.settings_message))


class BoardCountModal(Modal):
    def __init__(self, callback, channel: discord.abc.GuildChannel, emoji: str, settings_message: discord.Message):
        super().__init__(title="Board required count")
        self.callback = callback
        self.channel = channel
        self.emoji = emoji
        self.settings_message = settings_message
        self.count_input = TextInput(label="Required count", placeholder="How many reactions are required?", required=True, max_length=10)
        self.add_item(self.count_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            required_count = int(self.count_input.value)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Required count must be a number.", ephemeral=True)
            return
        await self.callback(interaction, self.channel, self.emoji, required_count, self.settings_message)


class AutoReplyAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add auto reply")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.word_input = TextInput(label="Trigger word", placeholder="Enter the trigger word", required=True, max_length=100)
        self.reply1 = TextInput(label="Reply 1", placeholder="First reply", required=True, max_length=200)
        self.reply2 = TextInput(label="Reply 2", placeholder="Second reply (optional)", required=False, max_length=200)
        self.reply3 = TextInput(label="Reply 3", placeholder="Third reply (optional)", required=False, max_length=200)
        self.reply4 = TextInput(label="Reply 4", placeholder="Fourth reply (optional)", required=False, max_length=200)
        self.add_item(self.word_input)
        self.add_item(self.reply1)
        self.add_item(self.reply2)
        self.add_item(self.reply3)
        self.add_item(self.reply4)

    async def on_submit(self, interaction: discord.Interaction):
        replies = [value for value in [self.reply1.value, self.reply2.value, self.reply3.value, self.reply4.value] if value]
        await self.callback(
            interaction,
            self.word_input.value.strip(),
            replies,
            self.settings_message,
        )


class AutoReplyRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove auto reply")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.word_input = TextInput(label="Trigger word to remove", placeholder="Enter the exact trigger word", required=True, max_length=100)
        self.add_item(self.word_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(
            interaction,
            self.word_input.value.strip(),
            self.settings_message,
        )


class AutoReplyChoiceView(TimeoutDisabledView):
    def __init__(self, user_id: int, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="auto_reply_add")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="auto_reply_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="auto_reply_cancel")
        self.add_button.callback = self.add_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class JoinRoleChoiceView(TimeoutDisabledView):
    def __init__(self, user_id: int, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="join_role_add")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="join_role_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="join_role_cancel")
        self.add_button.callback = self.add_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class JoinRoleSelectionView(TimeoutDisabledView):
    def __init__(self, user_id: int, guild: discord.Guild, prompt: str, callback, settings_message: discord.Message | None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild = guild
        self.callback = callback
        self.settings_message = settings_message
        role_options = []
        for role in sorted(guild.roles, key=lambda r: (r.position, r.name), reverse=True):
            if role.is_default():
                continue
            role_options.append(discord.SelectOption(label=role.name[:100], value=str(role.id)))
        self.role_select = discord.ui.Select(
            placeholder=prompt,
            options=role_options[:25],
            min_values=1,
            max_values=1,
            custom_id="join_role_select",
        )
        self.role_select.callback = self.on_role_selected
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="join_role_select_cancel")
        self.cancel_button.callback = self.on_cancel
        self.add_item(self.role_select)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_role_selected(self, interaction: discord.Interaction):
        if not self.role_select.values:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No role was selected.", ephemeral=True)
            return
        role_id = int(self.role_select.values[0])
        self.role_select.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
        await self.callback(interaction, role_id, self.settings_message)

    async def on_cancel(self, interaction: discord.Interaction):
        self.role_select.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(content="Role selection cancelled.", view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class ChannelEditChoiceView(TimeoutDisabledView):
    def __init__(self, user_id: int, setting_name: str, on_add, on_remove, settings_message: discord.Message):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.setting_name = setting_name
        self.on_add = on_add
        self.on_remove = on_remove
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="channel_edit_add")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="channel_edit_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="channel_edit_cancel")
        self.add_button.callback = self.add_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)


class EconomyChoiceView(TimeoutDisabledView):
    def __init__(self, user_id: int, on_add, on_remove, setting_name: str, on_edit=None, settings_message: discord.Message | None = None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.on_edit = on_edit
        self.setting_name = setting_name
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id=f"economy_add_{setting_name}")
        self.edit_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id=f"economy_edit_{setting_name}")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id=f"economy_remove_{setting_name}")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id=f"economy_cancel_{setting_name}")
        self.add_button.callback = self.add_callback
        self.edit_button.callback = self.edit_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.edit_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def edit_callback(self, interaction: discord.Interaction):
        if callable(self.on_edit):
            await self.on_edit(interaction, self.settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Edit is not available for this section.", ephemeral=True)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)


def validate_role_selection(interaction: discord.Interaction, role: discord.Role | None, role_label: str) -> str | None:
    if role is None:
        return None
    if not guild_owner_bypasses_role_checks(interaction) and interaction.user.top_role <= role:
        return f"<:disapprove:1517452151012589662> You cannot configure a {role_label} that is equal or higher than your highest role."
    if interaction.guild.me.top_role <= role:
        return "<:disapprove:1517452151012589662> I cannot assign that role because it is equal or higher than my highest role."
    return None


class EconomyRoleSelectionView(TimeoutDisabledView):
    def __init__(self, user_id: int, guild: discord.Guild, prompt: str, item_name: str, settings_message: discord.Message | None, callback, is_temp_role: bool):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild = guild
        self.item_name = item_name
        self.settings_message = settings_message
        self.callback = callback
        self.is_temp_role = is_temp_role
        self.role_select = None

        role_options = []
        for role in sorted(guild.roles, key=lambda r: (r.position, r.name), reverse=True):
            if role.is_default():
                continue
            role_options.append(discord.SelectOption(label=role.name[:100], value=str(role.id)))

        if role_options:
            self.role_select = discord.ui.Select(
                placeholder=prompt,
                options=role_options[:25],
                min_values=1,
                max_values=1,
                custom_id=f"economy_role_select_{'temp' if is_temp_role else 'normal'}",
            )
            self.role_select.callback = self.on_role_selected
            self.add_item(self.role_select)

        self.no_button = Button(label="No", style=discord.ButtonStyle.secondary, custom_id=f"economy_role_none_{'temp' if is_temp_role else 'normal'}")
        self.no_button.callback = self.on_no_selected
        self.add_item(self.no_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_role_selected(self, interaction: discord.Interaction):
        role_id = int(self.role_select.values[0])
        await self.callback(interaction, role_id, self.item_name, self.settings_message, self.is_temp_role)

    async def on_no_selected(self, interaction: discord.Interaction):
        await self.callback(interaction, None, self.item_name, self.settings_message, self.is_temp_role)


class EconomySettingsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.color = color
        self.build_components()

    def build_components(self):
        self.clear_items()
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        shop_items = guild.get("shop", {})
        uses_items = guild.get("item_uses", {})
        priced_items = guild.get("item_values", {})
        recipes = guild.get("recipes", {})

        self.shop_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="economy_shop_edit")
        self.uses_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="economy_uses_edit")
        self.prices_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="economy_prices_edit")
        self.crafts_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="economy_crafts_edit")

        self.shop_button.callback = self.handle_shop_edit
        self.uses_button.callback = self.handle_uses_edit
        self.prices_button.callback = self.handle_prices_edit
        self.crafts_button.callback = self.handle_crafts_edit

        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="economy_settings_back")
        self.back_button.callback = self.handle_back

        shop_summary = ", ".join(list(shop_items.keys())[:6]) if shop_items else "None"
        uses_summary = ", ".join(list(uses_items.keys())[:6]) if uses_items else "None"
        prices_summary = ", ".join(list(priced_items.keys())[:6]) if priced_items else "None"
        crafts_summary = ", ".join(list(recipes.keys())[:6]) if recipes else "None"

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **Economy settings**"),
            TextDisplay("Configure the economy systems below."),
            Separator(),
            Section(f"<:money:1517580310395486239> Shop items\n{shop_summary}", accessory=self.shop_button),
            Section(f"<:Vial:1517681553377857628> Item uses\n{uses_summary}", accessory=self.uses_button),
            Section(f"<:money:1517580310395486239> Item prices\n{prices_summary}", accessory=self.prices_button),
            Section(f"<:craft:1518348021161660539> Crafting recipes\n{crafts_summary}", accessory=self.crafts_button),
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
        if settings_message is None:
            settings_message = interaction.message
            if settings_message is None:
                try:
                    settings_message = await interaction.original_response()
                except (discord.NotFound, discord.HTTPException):
                    settings_message = None
        if settings_message is None:
            return
        try:
            await settings_message.edit(view=view)
            return
        except (discord.NotFound, discord.HTTPException):
            pass
        try:
            await interaction.followup.edit_message(message_id=settings_message.id, view=view)
            return
        except Exception:
            pass
        try:
            await interaction.edit_original_response(view=view)
        except Exception:
            pass

    async def handle_back(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

    async def handle_shop_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Shop items?",
            view=EconomyChoiceView(self.user_id, self.open_shop_add, self.open_shop_remove, "shop", self.open_shop_edit, settings_message),
            ephemeral=True,
        )

    async def open_shop_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyShopAddModal(self.add_shop_item, self.guild_id, settings_message))

    async def open_shop_edit(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyActionModal(self.open_shop_edit_launch, self.guild_id, "shop", settings_message))

    async def open_shop_edit_launch(self, interaction: discord.Interaction, canonical: str, item_data: dict, settings_message: discord.Message | None = None):
                                                                                               
        view = ShopEditLaunchView(self.user_id, settings_message, canonical, item_data, self)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Item found. Click below to continue editing.", view=view, ephemeral=True)

    async def _apply_shop_edit(self, original_key: str, interaction: discord.Interaction, name: str, desc: str, price: int, settings_message: discord.Message | None = None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("shop", {})
        new_key = normalize_item(name)
                                   
        if new_key != original_key and original_key in guild.get("shop", {}):
            try:
                del guild["shop"][original_key]
            except KeyError:
                pass
        guild["shop"][new_key] = {"desc": desc, "price": price}
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Shop item **{new_key}** updated.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def open_shop_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyShopRemoveModal(self.remove_shop_item, self.guild_id, settings_message))

    async def add_shop_item(self, interaction: discord.Interaction, name: str, desc: str, price: int, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("shop", {})
        guild["shop"][normalize_item(name)] = {"desc": desc, "price": price}
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Shop item **{normalize_item(name)}** saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_shop_item(self, interaction: discord.Interaction, name: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("shop", {})
        canonical = find_item_key(guild.get("shop", {}), name)
        if canonical:
            del guild["shop"][canonical]
            save_data(data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Removed shop item **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No shop item found for **{name}**.", ephemeral=True)

    async def handle_uses_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Item uses?",
            view=EconomyChoiceView(self.user_id, self.open_uses_add, self.open_uses_remove, "uses", self.open_uses_edit, settings_message),
            ephemeral=True,
        )

    async def open_uses_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyUseAddModal(self.add_use_item, self.guild_id, settings_message))

    async def open_uses_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyUseRemoveModal(self.remove_use_item, self.guild_id, settings_message))

    async def open_uses_edit(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyActionModal(self.open_use_edit_launch, self.guild_id, "uses", settings_message))

    async def open_use_edit_launch(self, interaction: discord.Interaction, canonical: str, item_data: dict, settings_message: discord.Message | None = None):
        view = UseEditLaunchView(self.user_id, settings_message, canonical, item_data, self)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Use effect found. Click below to continue editing.", view=view, ephemeral=True)

    async def add_use_item(self, interaction: discord.Interaction, item: str, money: int, xp: int, message: str, give_item: str | None, give_item_amount: int, settings_message: discord.Message | None):
        item_name = normalize_item(item)
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("item_uses", {})
        guild["item_uses"][item_name] = {
            "money": money,
            "xp": xp,
            "message": message or "Used item!",
            "role_id": None,
            "temp_role_id": None,
            "duration": 0,
            "delay": 0,
            "instant_message": None,
            "give_item": normalize_item(give_item) if give_item else None,
            "give_item_amount": give_item_amount,
        }
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:approve:1517452125687513158> Use effect for **{item_name}** saved. Choose a role to grant when it is used. Press No to skip.",
            view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a role", item_name, settings_message, self.handle_use_role_selection, False),
            ephemeral=True,
        )
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def _apply_use_edit(self, original_key: str, interaction: discord.Interaction, item: str, money: int, xp: int, message: str, give_item: str | None, give_item_amount: int, settings_message: discord.Message | None = None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("item_uses", {})
        new_key = normalize_item(item)
                                   
        if new_key != original_key and original_key in guild.get("item_uses", {}):
            try:
                del guild["item_uses"][original_key]
            except Exception:
                pass
        guild["item_uses"][new_key] = {
            "money": money,
            "xp": xp,
            "message": message or "Used item!",
            "role_id": None,
            "temp_role_id": None,
            "duration": 0,
            "delay": 0,
            "instant_message": None,
            "give_item": normalize_item(give_item) if give_item else None,
            "give_item_amount": give_item_amount,
        }
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:approve:1517452125687513158> Use effect for **{new_key}** updated. Choose a role to grant when it is used. Press No to skip.",
            view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a role", new_key, settings_message, self.handle_use_role_selection, False),
            ephemeral=True,
        )
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def handle_use_role_selection(self, interaction: discord.Interaction, role_id: int | None, item_name: str, settings_message: discord.Message | None, is_temp_role: bool):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        effect = guild.get("item_uses", {}).get(item_name)
        if effect is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> That item use entry no longer exists.", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id) if interaction.guild and role_id else None
        if role_id and role is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> The selected role is no longer available.", ephemeral=True)
            return

        role_error = validate_role_selection(interaction, role, "temporary role reward" if is_temp_role else "role reward")
        if role_error:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(role_error, ephemeral=True)
            return

        if is_temp_role:
            effect["temp_role_id"] = role_id
            save_data(data)
            if role_id is None:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    f"<:approve:1517452125687513158> Temp role setup skipped for **{item_name}**.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_modal(
                    EconomyTempRoleDurationModal(self.handle_temp_role_duration_submit, self.guild_id, item_name, settings_message)
                )
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
            return

        effect["role_id"] = role_id
        save_data(data)
        if role_id is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:approve:1517452125687513158> Role setup skipped for **{item_name}**. Choose a temporary role next, or press No to skip.",
                view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a temporary role", item_name, settings_message, self.handle_use_role_selection, True),
                ephemeral=True,
            )
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:approve:1517452125687513158> Role saved for **{item_name}**. Choose a temporary role next, or press No to skip.",
                view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a temporary role", item_name, settings_message, self.handle_use_role_selection, True),
                ephemeral=True,
            )
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def handle_temp_role_duration_submit(self, interaction: discord.Interaction, days: int, hours: int, minutes: int, seconds: int, item_name: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        effect = guild.get("item_uses", {}).get(item_name)
        if effect is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> That item use entry no longer exists.", ephemeral=True)
            return

        effect["duration"] = max(0, days * 86400 + hours * 3600 + minutes * 60 + seconds)
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:approve:1517452125687513158> Temp role duration saved for **{item_name}**.",
            ephemeral=True,
        )
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_use_item(self, interaction: discord.Interaction, item: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        canonical = find_item_key(guild.get("item_uses", {}), item)
        if canonical:
            del guild["item_uses"][canonical]
            save_data(data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Removed use effect for **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No use effect found for **{item}**.", ephemeral=True)

    async def handle_prices_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Item prices?",
            view=EconomyChoiceView(self.user_id, self.open_prices_add, self.open_prices_remove, "prices", self.open_prices_edit, settings_message),
            ephemeral=True,
        )

    async def open_prices_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyPriceSetModal(self.set_price_item, self.guild_id, settings_message))

    async def open_prices_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyPriceRemoveModal(self.remove_price_item, self.guild_id, settings_message))

    async def open_prices_edit(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyActionModal(self.open_price_edit_launch, self.guild_id, "prices", settings_message))

    async def open_price_edit_launch(self, interaction: discord.Interaction, canonical: str, item_data: dict, settings_message: discord.Message | None = None):
        view = PriceEditLaunchView(self.user_id, settings_message, canonical, item_data, self)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Price entry found. Click below to continue editing.", view=view, ephemeral=True)

    async def set_price_item(self, interaction: discord.Interaction, item: str, value: int, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("item_values", {})
        guild["item_values"][normalize_item(item)] = value
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Price for **{normalize_item(item)}** saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def _apply_price_edit(self, original_key: str, interaction: discord.Interaction, item: str, value: int, settings_message: discord.Message | None = None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("item_values", {})
        new_key = normalize_item(item)
                                   
        if new_key != original_key and original_key in guild.get("item_values", {}):
            try:
                del guild["item_values"][original_key]
            except Exception:
                pass
        guild["item_values"][new_key] = value
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Price for **{new_key}** updated.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_price_item(self, interaction: discord.Interaction, item: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        canonical = find_item_key(guild.get("item_values", {}), item)
        if canonical:
            del guild["item_values"][canonical]
            save_data(data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Removed price for **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No price found for **{item}**.", ephemeral=True)

    async def handle_crafts_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Crafting recipes?",
            view=EconomyChoiceView(self.user_id, self.open_craft_add, self.open_craft_remove, "crafts", self.open_craft_edit, settings_message),
            ephemeral=True,
        )

    async def open_craft_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyCraftAddModal(self.add_craft_item, self.guild_id, settings_message))

    async def open_craft_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyCraftRemoveModal(self.remove_craft_item, self.guild_id, settings_message))

    async def open_craft_edit(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyActionModal(self.open_craft_edit_launch, self.guild_id, "crafts", settings_message))

    async def open_craft_edit_launch(self, interaction: discord.Interaction, canonical: str, item_data: dict, settings_message: discord.Message | None = None):
        view = CraftEditLaunchView(self.user_id, settings_message, canonical, item_data, self)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Recipe found. Click below to continue editing.", view=view, ephemeral=True)

    async def _apply_craft_edit(self, original_key: str, interaction: discord.Interaction, item: str, requirements: list[tuple[str, int]], delay: int, settings_message: discord.Message | None = None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("recipes", {})
        new_key = normalize_item(item)
        recipe = {"reqs": {normalize_item(name): count for name, count in requirements}, "delay": delay}
        if new_key != original_key and original_key in guild.get("recipes", {}):
            try:
                del guild["recipes"][original_key]
            except KeyError:
                pass
        guild["recipes"][new_key] = recipe
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Craft recipe for **{new_key}** updated.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def add_craft_item(self, interaction: discord.Interaction, item: str, requirements: list[tuple[str, int]], delay: int, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("recipes", {})
        recipe = {"reqs": {normalize_item(name): count for name, count in requirements}, "delay": delay}
        guild["recipes"][normalize_item(item)] = recipe
        save_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Craft recipe for **{normalize_item(item)}** saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_craft_item(self, interaction: discord.Interaction, item: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild.setdefault("recipes", {})
        canonical = find_item_key(guild.get("recipes", {}), item)
        if canonical:
            del guild["recipes"][canonical]
            save_data(data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Removed craft recipe for **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No craft recipe found for **{item}**.", ephemeral=True)


def parse_item_amount_entry(value: str, default_amount: int = 1):
    text = (value or "").strip()
    if not text:
        return None, default_amount
    if ":" in text:
        name, amount_text = text.rsplit(":", 1)
        try:
            amount = int(amount_text.strip() or default_amount)
        except ValueError:
            amount = default_amount
        return (name.strip() or None), amount
    return text, default_amount


def parse_craft_requirements(value: str) -> list[tuple[str, int]]:
    raw_value = (value or "").strip()
    if not raw_value:
        raise ValueError("At least 1 ingredient is required.")

    parenthesized = [part.strip() for part in re.findall(r"\(([^)]+)\)", raw_value) if part.strip()]
    if parenthesized:
        parts = parenthesized
    else:
        parts = [part.strip() for part in re.split(r"/|\n", raw_value) if part.strip()]

    if len(parts) < 1:
        raise ValueError("At least 1 ingredient is required.")
    if len(parts) > 10:
        raise ValueError("You can set up to 10 ingredients only.")

    requirements: list[tuple[str, int]] = []
    for part in parts:
        name, amount = parse_item_amount_entry(part, default_amount=1)
        if not name:
            raise ValueError("Each ingredient must use the format Item:Amount.")
        requirements.append((name, amount))

    return requirements


def format_recipe_requirements(recipe: dict) -> str:
    reqs = recipe.get("reqs", {}) or {}
    if not reqs:
        return "No ingredients"
    return ", ".join(f"{amount}x {name}" for name, amount in sorted(reqs.items(), key=lambda item: item[0].lower()))


class EconomyTempRoleDurationModal(Modal):
    def __init__(self, callback, guild_id: str, item_name: str, settings_message: discord.Message | None):
        super().__init__(title="Set temp role duration")
        self.callback = callback
        self.guild_id = guild_id
        self.item_name = item_name
        self.settings_message = settings_message
        self.days_input = TextInput(label="Days", placeholder="0", required=True, max_length=10)
        self.hours_input = TextInput(label="Hours", placeholder="0", required=True, max_length=10)
        self.minutes_input = TextInput(label="Minutes", placeholder="0", required=True, max_length=10)
        self.seconds_input = TextInput(label="Seconds", placeholder="0", required=True, max_length=10)
        self.add_item(self.days_input)
        self.add_item(self.hours_input)
        self.add_item(self.minutes_input)
        self.add_item(self.seconds_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            days = int(self.days_input.value or 0)
            hours = int(self.hours_input.value or 0)
            minutes = int(self.minutes_input.value or 0)
            seconds = int(self.seconds_input.value or 0)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Days, hours, minutes, and seconds must be numbers.", ephemeral=True)
            return
        await self.callback(interaction, days, hours, minutes, seconds, self.item_name, self.settings_message)


class EconomyShopAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add shop item")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.name_input = TextInput(label="Item name", placeholder="Name of the shop item", required=True, max_length=100)
        self.desc_input = TextInput(label="Description", placeholder="Short description", required=True, max_length=200)
        self.price_input = TextInput(label="Price", placeholder="Item price", required=True, max_length=10)
        self.add_item(self.name_input)
        self.add_item(self.desc_input)
        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price_input.value)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Price must be a number.", ephemeral=True)
            return
        await self.callback(interaction, self.name_input.value.strip(), self.desc_input.value.strip(), price, self.settings_message)


class EconomyShopRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove shop item")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.name_input = TextInput(label="Item name", placeholder="Item to remove", required=True, max_length=100)
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction, self.name_input.value.strip(), self.settings_message)


class EconomyUseAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add item use")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item", placeholder="Item name", required=True, max_length=100)
        self.money_input = TextInput(label="Money reward", placeholder="0", required=True, max_length=10)
        self.xp_input = TextInput(label="XP reward", placeholder="0", required=True, max_length=10)
        self.message_input = TextInput(label="Response message", placeholder="Used item!", required=False, max_length=200)
        self.give_item_input = TextInput(label="Give item (Item:Amount)", placeholder="Optional item:amount", required=False, max_length=100)
        self.add_item(self.item_input)
        self.add_item(self.money_input)
        self.add_item(self.xp_input)
        self.add_item(self.message_input)
        self.add_item(self.give_item_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            money = int(self.money_input.value or 0)
            xp = int(self.xp_input.value or 0)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Money/XP must be numbers.", ephemeral=True)
            return

        give_item, give_amount = parse_item_amount_entry(self.give_item_input.value, default_amount=1)

        await self.callback(interaction, self.item_input.value.strip(), money, xp, self.message_input.value.strip(), give_item, give_amount, self.settings_message)


class EconomyUseRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove item use")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item", placeholder="Item to remove", required=True, max_length=100)
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction, self.item_input.value.strip(), self.settings_message)


class EconomyPriceSetModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Set item price")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item", placeholder="Item name", required=True, max_length=100)
        self.price_input = TextInput(label="Price", placeholder="Sell price", required=True, max_length=10)
        self.add_item(self.item_input)
        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.price_input.value)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Price must be a number.", ephemeral=True)
            return
        await self.callback(interaction, self.item_input.value.strip(), value, self.settings_message)


class EconomyPriceRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove item price")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item", placeholder="Item to remove", required=True, max_length=100)
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction, self.item_input.value.strip(), self.settings_message)


class EconomyCraftAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add craft recipe")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.item_input = TextInput(label="Crafted item", placeholder="Result item", required=True, max_length=100)
        self.items_input = TextInput(label="Ingredient list", placeholder="(item:amount)(item:amount)", required=True, max_length=1000)
        self.delay_input = TextInput(label="Delay seconds", placeholder="0", required=True, max_length=10)
        self.add_item(self.item_input)
        self.add_item(self.items_input)
        self.add_item(self.delay_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            delay = int(self.delay_input.value or 0)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Delay must be a number.", ephemeral=True)
            return

        try:
            requirements = parse_craft_requirements(self.items_input.value)
        except ValueError as error:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> {error}", ephemeral=True)
            return

        await self.callback(interaction, self.item_input.value.strip(), requirements, delay, self.settings_message)


class EconomyCraftRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove craft recipe")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.item_input = TextInput(label="Crafted item", placeholder="Recipe to remove", required=True, max_length=100)
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction, self.item_input.value.strip(), self.settings_message)


class EconomyActionModal(Modal):
    def __init__(self, callback, guild_id: str, section: str, settings_message: discord.Message | None = None):
        super().__init__(title="Find entry to edit")
        self.callback = callback
        self.guild_id = guild_id
        self.section = section
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item or name", placeholder="Name or number", required=True, max_length=100)
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.item_input.value.strip()
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
                                           
        if self.section == "crafts":
            section_key = "recipes"
        elif self.section == "shop":
            section_key = "shop"
        elif self.section == "prices":
            section_key = "item_values"
        elif self.section == "uses":
            section_key = "item_uses"
        else:
            section_key = self.section
        candidates = guild.get(section_key, {})

                             
        canonical = find_item_key(candidates, raw)

                                                                                          
        if canonical is None and raw.isdigit():
            idx = int(raw) - 1
            keys = list(sorted(candidates.keys()))
            if 0 <= idx < len(keys):
                canonical = keys[idx]

                            
        if canonical is None:
            canonical = find_item_key(candidates, normalize_item(raw))

                                                   
        if canonical is None:
            target = raw.lower()
            for k in candidates:
                if target in k.lower():
                    canonical = k
                    break

        if canonical is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Entry not found.", ephemeral=True)
            return

        item_data = candidates.get(canonical)
        await self.callback(interaction, canonical, item_data, self.settings_message)


class ShopEditLaunchView(TimeoutDisabledView):
    def __init__(self, user_id: int, settings_message: discord.Message | None, canonical: str, item_data: dict, parent_view: EconomySettingsView):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.settings_message = settings_message
        self.canonical = canonical
        self.item_data = item_data or {}
        self.parent = parent_view
        self.open_button = Button(label="Open edit modal", style=discord.ButtonStyle.primary, custom_id="open_shop_edit_modal")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_shop_edit")
        self.open_button.callback = self.open_edit
        self.cancel_button.callback = self.cancel
        self.add_item(self.open_button)
        self.add_item(self.cancel_button)

    async def open_edit(self, interaction: discord.Interaction):
        modal = EconomyShopAddModal(None, self.parent.guild_id, self.settings_message)
        modal.name_input.default = self.canonical
        modal.desc_input.default = self.item_data.get("desc", "")
        modal.price_input.default = str(self.item_data.get("price", 0))

        async def _on_submit(inner_interaction: discord.Interaction, name: str, desc: str, price: int, settings_message_inner: discord.Message | None):
            await self.parent._apply_shop_edit(self.canonical, inner_interaction, name, desc, price, settings_message_inner)

        modal.callback = _on_submit
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Shop edit cancelled.", ephemeral=True)


class CraftEditLaunchView(TimeoutDisabledView):
    def __init__(self, user_id: int, settings_message: discord.Message | None, canonical: str, item_data: dict, parent_view: EconomySettingsView):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.settings_message = settings_message
        self.canonical = canonical
        self.item_data = item_data or {}
        self.parent = parent_view
        self.open_button = Button(label="Open edit modal", style=discord.ButtonStyle.primary, custom_id="open_craft_edit_modal")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_craft_edit")
        self.open_button.callback = self.open_edit
        self.cancel_button.callback = self.cancel
        self.add_item(self.open_button)
        self.add_item(self.cancel_button)

    async def open_edit(self, interaction: discord.Interaction):
        modal = EconomyCraftAddModal(None, self.parent.guild_id, self.settings_message)
        modal.item_input.default = self.canonical
        reqs = self.item_data.get("reqs", {})
        req_items = list(reqs.items())
        modal.items_input.default = "".join(f"({name}:{amount})" for name, amount in req_items)
        modal.delay_input.default = str(self.item_data.get("delay", 0))

        async def _on_submit(inner_interaction: discord.Interaction, item: str, requirements: list[tuple[str, int]], delay: int, settings_message_inner: discord.Message | None):
            await self.parent._apply_craft_edit(self.canonical, inner_interaction, item, requirements, delay, settings_message_inner)

        modal.callback = _on_submit
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Craft edit cancelled.", ephemeral=True)


class UseEditLaunchView(TimeoutDisabledView):
    def __init__(self, user_id: int, settings_message: discord.Message | None, canonical: str, item_data: dict, parent_view: EconomySettingsView):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.settings_message = settings_message
        self.canonical = canonical
        self.item_data = item_data or {}
        self.parent = parent_view
        self.open_button = Button(label="Open edit modal", style=discord.ButtonStyle.primary, custom_id="open_use_edit_modal")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_use_edit")
        self.open_button.callback = self.open_edit
        self.cancel_button.callback = self.cancel
        self.add_item(self.open_button)
        self.add_item(self.cancel_button)

    async def open_edit(self, interaction: discord.Interaction):
        modal = EconomyUseAddModal(None, self.parent.guild_id, self.settings_message)
        modal.item_input.default = self.canonical
        modal.money_input.default = str(self.item_data.get("money", 0))
        modal.xp_input.default = str(self.item_data.get("xp", 0))
        modal.message_input.default = self.item_data.get("message", "")
        give_item = self.item_data.get("give_item")
        if give_item:
            modal.give_item_input.default = f"{give_item}:{self.item_data.get('give_item_amount', 1)}"

        async def _on_submit(inner_interaction: discord.Interaction, item: str, money: int, xp: int, message: str, give_item: str | None, give_item_amount: int, settings_message_inner: discord.Message | None):
            await self.parent._apply_use_edit(self.canonical, inner_interaction, item, money, xp, message, give_item, give_item_amount, settings_message_inner)

        modal.callback = _on_submit
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Use edit cancelled.", ephemeral=True)


class PriceEditLaunchView(TimeoutDisabledView):
    def __init__(self, user_id: int, settings_message: discord.Message | None, canonical: str, item_data: int | None, parent_view: EconomySettingsView):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.settings_message = settings_message
        self.canonical = canonical
        self.item_data = item_data
        self.parent = parent_view
        self.open_button = Button(label="Open edit modal", style=discord.ButtonStyle.primary, custom_id="open_price_edit_modal")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_price_edit")
        self.open_button.callback = self.open_edit
        self.cancel_button.callback = self.cancel
        self.add_item(self.open_button)
        self.add_item(self.cancel_button)

    async def open_edit(self, interaction: discord.Interaction):
        modal = EconomyPriceSetModal(None, self.parent.guild_id, self.settings_message)
        modal.item_input.default = self.canonical
        modal.price_input.default = str(self.item_data or 0)

        async def _on_submit(inner_interaction: discord.Interaction, item: str, value: int, settings_message_inner: discord.Message | None):
            await self.parent._apply_price_edit(self.canonical, inner_interaction, item, value, settings_message_inner)

        modal.callback = _on_submit
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Price edit cancelled.", ephemeral=True)


class LevelRewardActionModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None = None):
        super().__init__(title="Find level reward to edit")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.level_input = TextInput(label="Level number", placeholder="Level (e.g. 5)", required=True, max_length=10)
        self.add_item(self.level_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            level = int(self.level_input.value.strip())
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Level must be a number.", ephemeral=True)
            return
        levels = load_levels()
        rewards = levels.get(self.guild_id, {}).get("config", {}).get("rewards", {})
        reward = rewards.get(str(level))
        if reward is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No reward configured for level {level}.", ephemeral=True)
            return
        await self.callback(interaction, level, reward, self.settings_message)


class LevelRewardEditLaunchView(TimeoutDisabledView):
    def __init__(self, user_id: int, settings_message: discord.Message | None, level: int, reward_data: dict, parent_view: 'LevelSettingsView'):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.settings_message = settings_message
        self.level = level
        self.reward_data = reward_data or {}
        self.parent = parent_view
        self.open_button = Button(label="Open edit modal", style=discord.ButtonStyle.primary, custom_id="open_level_reward_edit")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_level_reward_edit")
        self.open_button.callback = self.open_edit
        self.cancel_button.callback = self.cancel
        self.add_item(self.open_button)
        self.add_item(self.cancel_button)

    async def open_edit(self, interaction: discord.Interaction):
        modal = LevelRewardModal(None, self.parent.guild_id, self.settings_message)
        modal.level_input.default = str(self.level)
        modal.duration_input.default = str(self.reward_data.get("duration", 0))
        modal.money_input.default = str(self.reward_data.get("money", 0))
        modal.xp_input.default = str(self.reward_data.get("xp", 0))
        give_item = self.reward_data.get("give_item")
        if give_item:
            modal.item_input.default = f"{give_item}:{self.reward_data.get('give_item_amount', 1)}"

        async def _on_submit(inner_interaction: discord.Interaction, reward_data: dict, level: int, settings_message_inner: discord.Message | None):
                                                                                       
            save_level_reward_data(str(inner_interaction.guild.id), level, reward_data)
            await inner_interaction.response.defer(ephemeral=True); await inner_interaction.followup.send(f"<:approve:1517452125687513158> Level {level} reward updated.", ephemeral=True)
            try:
                await self.parent.refresh_settings_message(inner_interaction, LevelSettingsView(self.user_id, self.parent.guild_id, self.parent.color, settings_message=self.settings_message))
            except Exception:
                pass

        modal.callback = _on_submit
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Level reward edit cancelled.", ephemeral=True)


class LevelRoleSelectionView(TimeoutDisabledView):
    def __init__(self, user_id: int, guild: discord.Guild, prompt: str, level: int, reward_data: dict, settings_message: discord.Message | None, callback, is_temp_role: bool):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild = guild
        self.level = level
        self.reward_data = reward_data
        self.settings_message = settings_message
        self.callback = callback
        self.is_temp_role = is_temp_role
        self.role_select = None

        role_options = []
        for role in sorted(guild.roles, key=lambda r: (r.position, r.name), reverse=True):
            if role.is_default():
                continue
            role_options.append(discord.SelectOption(label=role.name[:100], value=str(role.id)))

        if role_options:
            self.role_select = discord.ui.Select(
                placeholder=prompt,
                options=role_options[:25],
                min_values=1,
                max_values=1,
                custom_id=f"level_role_select_{'temp' if is_temp_role else 'normal'}",
            )
            self.role_select.callback = self.on_role_selected
            self.add_item(self.role_select)

        self.no_button = Button(label="No", style=discord.ButtonStyle.secondary, custom_id=f"level_role_none_{'temp' if is_temp_role else 'normal'}")
        self.no_button.callback = self.on_no_selected
        self.add_item(self.no_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_role_selected(self, interaction: discord.Interaction):
        role_id = int(self.role_select.values[0])
        if self.is_temp_role:
            self.reward_data["temp_role_id"] = role_id
        else:
            self.reward_data["role_id"] = role_id
        await self.callback(interaction, self.reward_data, self.level, self.settings_message, self.is_temp_role)

    async def on_no_selected(self, interaction: discord.Interaction):
        if self.is_temp_role:
            self.reward_data["temp_role_id"] = None
        else:
            self.reward_data["role_id"] = None
        await self.callback(interaction, self.reward_data, self.level, self.settings_message, self.is_temp_role)


class LevelRewardModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Set level reward")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.level_input = TextInput(label="Level", placeholder="1", required=True, max_length=10)
        self.duration_input = TextInput(label="Temp role duration (seconds)", placeholder="0", required=True, max_length=10)
        self.money_input = TextInput(label="Money reward", placeholder="0", required=True, max_length=10)
        self.xp_input = TextInput(label="XP reward", placeholder="0", required=True, max_length=10)
        self.item_input = TextInput(label="Item (Item:Amount)", placeholder="Optional item:amount", required=False, max_length=100)
        self.add_item(self.level_input)
        self.add_item(self.duration_input)
        self.add_item(self.money_input)
        self.add_item(self.xp_input)
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            level = int(self.level_input.value.strip())
            duration = int(self.duration_input.value.strip() or 0)
            money = int(self.money_input.value.strip() or 0)
            xp = int(self.xp_input.value.strip() or 0)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Level, duration, money, and XP must be numbers.", ephemeral=True)
            return

        give_item, give_amount = parse_item_amount_entry(self.item_input.value, default_amount=1)
        reward_data = {
            "role_id": None,
            "temp_role_id": None,
            "duration": max(0, duration),
            "money": money,
            "xp": xp,
            "give_item": normalize_item(give_item) if give_item else None,
            "give_item_amount": give_amount,
        }
        await self.callback(interaction, reward_data, level, self.settings_message)


class LevelSettingsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color, settings_message: discord.Message | None = None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.color = color
        self.settings_message = settings_message
        self.build_components()

    def build_components(self):
        self.clear_items()
        levels = load_levels()
        rewards = levels.get(self.guild_id, {}).get("config", {}).get("rewards", {})
        guild = bot.get_guild(int(self.guild_id)) if self.guild_id.isdigit() else None

        summary_lines = []
        for level_key, reward_data in sorted(rewards.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 999999)[:6]:
            summary_lines.append(f"Lvl {level_key}: {format_level_reward_summary(guild, level_key, reward_data) if guild else 'Configured'}")

                                                                              
        self.edit_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id=f"level_settings_edit_{self.user_id}")
        self.edit_button.callback = self.handle_edit
        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id=f"level_settings_back_{self.user_id}")
        self.back_button.callback = self.handle_back

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **Level settings**"),
            TextDisplay("Configure level-based rewards below."),
            Separator(),
            Section("<:box:1517581439552585759> Current rewards\n" + ("\n".join(summary_lines) if summary_lines else "None"), accessory=self.edit_button),
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
        if settings_message is None:
            settings_message = self.settings_message
        if settings_message is None:
            settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except (discord.NotFound, discord.HTTPException):
                settings_message = None
        if settings_message is None:
            return
        try:
            await settings_message.edit(view=view)
            return
        except (discord.NotFound, discord.HTTPException):
            pass
        try:
            await interaction.followup.edit_message(message_id=settings_message.id, view=view)
            return
        except Exception:
            pass
        try:
            await interaction.edit_original_response(view=view)
        except Exception:
            pass

    async def handle_back(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

    async def handle_set(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LevelRewardModal(self.handle_reward_submit, self.guild_id, self.settings_message))

    async def handle_edit(self, interaction: discord.Interaction):
                                                                              
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Level rewards?",
            view=EconomyChoiceView(self.user_id, self.open_level_add, self.open_level_remove, "levels", self.open_level_edit, settings_message),
            ephemeral=True,
        )

    async def open_level_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(LevelRewardModal(self.handle_reward_submit, self.guild_id, settings_message))

    async def open_level_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
                                                                      
        await interaction.response.send_modal(LevelRewardActionModal(self._perform_level_remove, self.guild_id, settings_message))

    async def open_level_edit(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
                                                                           
        await interaction.response.send_modal(LevelRewardActionModal(self.open_level_edit_launch, self.guild_id, settings_message))

    async def _perform_level_remove(self, interaction: discord.Interaction, level: int, reward_data: dict, settings_message: discord.Message | None = None):
        levels = load_levels()
        guild_levels = levels.get(self.guild_id, {}).get("config", {}).get("rewards", {})
        if str(level) in guild_levels:
            del guild_levels[str(level)]
                                
            if self.guild_id in levels and "config" in levels[self.guild_id]:
                levels[self.guild_id]["config"]["rewards"] = guild_levels
            else:
                                  
                if self.guild_id not in levels:
                    levels[self.guild_id] = {"config": {"channel_id": None, "rewards": {}}, "users": {}}
                levels[self.guild_id]["config"]["rewards"] = guild_levels
            save_levels(levels)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Level {level} reward removed.", ephemeral=True)
            await self.refresh_settings_message(interaction, LevelSettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Specified level reward was not found.", ephemeral=True)

    async def open_level_edit_launch(self, interaction: discord.Interaction, level: int, reward_data: dict, settings_message: discord.Message | None = None):
        view = LevelRewardEditLaunchView(self.user_id, settings_message, level, reward_data, self)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Reward found. Click below to continue editing.", view=view, ephemeral=True)

    async def handle_reward_submit(self, interaction: discord.Interaction, reward_data: dict, level: int, settings_message: discord.Message | None):
        guild = interaction.guild
        if guild is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This can only be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:approve:1517452125687513158> Level {level} reward details saved. Choose a role to grant when this level is reached. Press No to skip.",
            view=LevelRoleSelectionView(self.user_id, guild, "Choose a role", level, reward_data, settings_message, self.handle_level_role_selection, False),
            ephemeral=True,
        )

    async def handle_level_role_selection(self, interaction: discord.Interaction, reward_data: dict, level: int, settings_message: discord.Message | None, is_temp_role: bool):
        guild = interaction.guild
        if guild is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This can only be used in a server.", ephemeral=True)
            return

        role_id = reward_data.get("temp_role_id" if is_temp_role else "role_id")
        role = guild.get_role(role_id) if role_id else None
        if role_id and role is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> The selected role is no longer available.", ephemeral=True)
            return

        role_error = validate_role_selection(interaction, role, "temporary role reward" if is_temp_role else "role reward")
        if role_error:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(role_error, ephemeral=True)
            return

        if is_temp_role:
            save_level_reward_data(str(guild.id), level, reward_data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Level {level} reward saved.", ephemeral=True)
            await self.refresh_settings_message(interaction, LevelSettingsView(self.user_id, self.guild_id, self.color, settings_message=self.settings_message))
            return

        if role_id is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:approve:1517452125687513158> Role setup skipped for level {level}. Choose a temporary role next, or press No to skip.",
                view=LevelRoleSelectionView(self.user_id, guild, "Choose a temporary role", level, reward_data, settings_message, self.handle_level_role_selection, True),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"<:approve:1517452125687513158> Role saved for level {level}. Choose a temporary role next, or press No to skip.",
            view=LevelRoleSelectionView(self.user_id, guild, "Choose a temporary role", level, reward_data, settings_message, self.handle_level_role_selection, True),
            ephemeral=True,
        )


class AutomodSettingsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.color = color
        self.build_components()

    def build_components(self):
        self.clear_items()
        automod, _ = get_guild_automod_config(self.guild_id)
        blocked_words = automod.get("blocked_words", [])
        warning_sanctions = automod.get("warning_sanctions", [])
        blocked_summary = "\n".join(
            f"- {item.get('phrase', '')}{' (custom regex)' if get_automod_match_mode(item) == 'custom_regex' else ' (regex)' if get_automod_match_mode(item) == 'generated_regex' else ''}"
            for item in blocked_words
        ) or "None"
        sanctions_summary = []
        for item in warning_sanctions:
            action = item.get('action', 'timeout')
            display = f"{item.get('warns')} warns -> {action}"
            if action == 'timeout':
                duration = item.get('duration') or f"{item.get('duration_seconds', 0)}s"
                display += f" ({duration})"
            sanctions_summary.append(display)
        sanctions_summary = "\n".join(sanctions_summary) or "None"

        self.word_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="automod_word_edit")
        self.sanctions_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="automod_sanctions_edit")
        self.word_button.callback = self.handle_word_edit
        self.sanctions_button.callback = self.handle_sanctions_edit

        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="automod_settings_back")
        self.back_button.callback = self.handle_back

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **Automod settings**"),
            TextDisplay("Manage blocked words and warning sanctions below."),
            Separator(),
            Section(f"<:warning:1517452174991556758> Blocked words\n{blocked_summary}", accessory=self.word_button),
            Section(f"<:warning:1517452174991556758> Warning sanctions\n{sanctions_summary}", accessory=self.sanctions_button),
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def handle_back(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

    async def handle_word_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with blocked words?",
            view=AutomodWordChoiceView(self.user_id, self.guild_id, self.open_word_add, self.open_word_remove, settings_message),
            ephemeral=True,
        )

    async def open_word_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(AutomodWordAddModal(self.add_word_block, self.guild_id, settings_message))

    async def open_word_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(AutomodWordRemoveModal(self.remove_word_block, self.guild_id, settings_message))

    async def add_word_block(self, interaction: discord.Interaction, phrase: str, match_mode: str, warn_on_match: bool, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        automod.setdefault("blocked_words", []).append({"phrase": phrase, "match_mode": match_mode, "use_regex": match_mode != "word", "warn_on_match": warn_on_match})
        save_guild_data(data)
        await sync_guild_word_block_rule(self.guild_id)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Blocked phrase saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_word_block(self, interaction: discord.Interaction, phrase: str, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        blocked_words = automod.get("blocked_words", [])
        filtered = [item for item in blocked_words if str(item.get("phrase", "")).strip().lower() != phrase.strip().lower()]
        if len(filtered) != len(blocked_words):
            automod["blocked_words"] = filtered
            save_guild_data(data)
            await sync_guild_word_block_rule(self.guild_id)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Blocked phrase removed.", ephemeral=True)
            await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No matching blocked phrase was found.", ephemeral=True)

    async def handle_sanctions_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with warning sanctions?",
            view=AutomodSanctionChoiceView(self.user_id, self.guild_id, self.open_sanction_add, self.open_sanction_remove, settings_message),
            ephemeral=True,
        )

    async def open_sanction_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(AutomodSanctionAddModal(self.add_sanction_rule, self.guild_id, settings_message))

    async def open_sanction_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(AutomodSanctionRemoveModal(self.remove_sanction_rule, self.guild_id, settings_message))

    async def add_sanction_rule(self, interaction: discord.Interaction, warns: int, action: str, duration_seconds: int, duration_text: str, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        automod.setdefault("warning_sanctions", []).append({"warns": warns, "action": action, "duration_seconds": duration_seconds, "duration": duration_text})
        save_guild_data(data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Warning sanction saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_sanction_rule(self, interaction: discord.Interaction, warns: int, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        sanctions = automod.get("warning_sanctions", [])
        filtered = [item for item in sanctions if int(item.get("warns", 0)) != warns]
        if len(filtered) != len(sanctions):
            automod["warning_sanctions"] = filtered
            save_guild_data(data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Warning sanction removed.", ephemeral=True)
            await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No matching warning sanction was found.", ephemeral=True)

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
        if settings_message is None:
            settings_message = interaction.message
            if settings_message is None:
                try:
                    settings_message = await interaction.original_response()
                except (discord.NotFound, discord.HTTPException):
                    settings_message = None
        if settings_message is None:
            return
        try:
            await settings_message.edit(view=view)
            return
        except (discord.NotFound, discord.HTTPException):
            pass
        try:
            await interaction.followup.edit_message(message_id=settings_message.id, view=view)
            return
        except Exception:
            pass
        try:
            await interaction.edit_original_response(view=view)
        except Exception:
            pass


class AutomodWordChoiceView(TimeoutDisabledView):
    def __init__(self, user_id: int, guild_id: str, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="automod_word_add")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="automod_word_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="automod_word_cancel")
        self.add_button.callback = self.add_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)


class AutomodWordAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add blocked phrase")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.phrase_input = TextInput(label="Word or phrase", placeholder="Enter a word, phrase, or regex", required=True, max_length=200)
        self.regex_input = TextInput(label="Regex? (false/true/is)", placeholder="false", required=True, max_length=10)
        self.warn_input = TextInput(label="Warn on match? (true/false)", placeholder="false", required=True, max_length=5)
        self.add_item(self.phrase_input)
        self.add_item(self.regex_input)
        self.add_item(self.warn_input)

    async def on_submit(self, interaction: discord.Interaction):
        def parse_mode(value: str) -> str:
            normalized = value.strip().lower()
            if normalized in {"is", "custom", "custom_regex", "raw_regex"}:
                return "custom_regex"
            if normalized in {"true", "regex", "generated", "generated_regex", "yes", "y", "1"}:
                return "generated_regex"
            return "word"

        def parse_bool(value: str) -> bool:
            return value.strip().lower() in {"true", "yes", "y", "1"}

        match_mode = parse_mode(self.regex_input.value)
        warn_on_match = parse_bool(self.warn_input.value)
        await self.callback(interaction, self.phrase_input.value.strip(), match_mode, warn_on_match, self.settings_message)


class AutomodWordRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove blocked phrase")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.phrase_input = TextInput(label="Word or phrase", placeholder="Enter the phrase to remove", required=True, max_length=200)
        self.add_item(self.phrase_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction, self.phrase_input.value.strip(), self.settings_message)


class AutomodSanctionChoiceView(TimeoutDisabledView):
    def __init__(self, user_id: int, guild_id: str, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="automod_sanction_add")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="automod_sanction_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="automod_sanction_cancel")
        self.add_button.callback = self.add_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)


class AutomodSanctionAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add warning sanction")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.warns_input = TextInput(label="Warn count", placeholder="5", required=True, max_length=10)
        self.action_input = TextInput(label="Action (timeout/kick/ban)", placeholder="timeout", required=True, max_length=20)
        self.duration_input = TextInput(label="Timeout duration (1d, 10s, 50m)", placeholder="1d", required=False, max_length=20)
        self.add_item(self.warns_input)
        self.add_item(self.action_input)
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            warns = int(self.warns_input.value)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Warn count must be a number.", ephemeral=True)
            return

        action = self.action_input.value.strip().lower()
        if action not in {"timeout", "kick", "ban"}:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Action must be timeout, kick, or ban.", ephemeral=True)
            return

        duration_text = self.duration_input.value.strip() if self.duration_input.value else ""
        duration_seconds = None
        if action == "timeout":
            if not duration_text:
                duration_text = "1d"
            duration_seconds = parse_duration_to_seconds(duration_text)
            if duration_seconds is None or duration_seconds <= 0:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Timeout duration must be a valid value like 1d, 10s, or 50m.", ephemeral=True)
                return
        else:
            duration_seconds = 0
            if duration_text:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Duration is only valid for timeout actions.", ephemeral=True)
                return

        await self.callback(interaction, warns, action, duration_seconds, duration_text, self.settings_message)


class AutomodSanctionRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove warning sanction")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.warns_input = TextInput(label="Warn count", placeholder="5", required=True, max_length=10)
        self.add_item(self.warns_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            warns = int(self.warns_input.value)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Warn count must be a number.", ephemeral=True)
            return
        await self.callback(interaction, warns, self.settings_message)


class HoneypotSanctionModal(Modal):
    def __init__(self, callback, channel: discord.abc.GuildChannel, settings_message: discord.Message | None):
        super().__init__(title="Set honeypot sanction")
        self.callback = callback
        self.channel = channel
        self.settings_message = settings_message
        self.action_input = TextInput(label="Action (timeout/kick/ban)", placeholder="timeout", required=True, max_length=20)
        self.duration_input = TextInput(label="Timeout duration (1d, 10s, 50m)", placeholder="1d", required=False, max_length=20)
        self.add_item(self.action_input)
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        action = self.action_input.value.strip().lower()
        if action not in {"timeout", "kick", "ban"}:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Action must be timeout, kick, or ban.", ephemeral=True)
            return

        duration_text = self.duration_input.value.strip() if self.duration_input.value else ""
        duration_seconds = None
        if action == "timeout":
            if not duration_text:
                duration_text = "1d"
            duration_seconds = parse_duration_to_seconds(duration_text)
            if duration_seconds is None or duration_seconds <= 0:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Timeout duration must be a valid value like 1d, 10s, or 50m.", ephemeral=True)
                return
        else:
            duration_seconds = 0
            if duration_text:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Duration is only valid for timeout actions.", ephemeral=True)
                return

        await self.callback(interaction, self.channel, action, duration_seconds, duration_text, self.settings_message)


class ChannelSettingsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color, page: int = 1):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.page = page
        self.color = color
        self.build_components()

    def build_components(self):
        self.clear_items()
        guild = bot.get_guild(int(self.guild_id))
        guild_config, _ = get_guild_config(self.guild_id)
        welcome_channel = format_channel_reference(guild, guild_config.get("welcome_channel_id")) if guild else "None"
        goodbye_channel = format_channel_reference(guild, guild_config.get("goodbye_channel_id")) if guild else "None"
        level_channel = "None"
        level_id = get_level_channel_id(self.guild_id)
        if level_id:
            level_channel = format_channel_reference(guild, level_id) if guild else "None"
        admin_channels = get_admin_log_channel_mentions(guild) if guild else []
        admin_label = "Remove" if admin_channels else "Set"
        admin_value = "\n".join(admin_channels) if admin_channels else "None"

        board_entries = get_guild_board_entries(self.guild_id)
        counter_entries = get_guild_counter_entries(guild) if guild else []
        honeypot_channel = format_channel_reference(guild, guild_config.get("honeypot_channel_id")) if guild else "None"
        honeypot_sanction = guild_config.get("honeypot_sanction") or {}
        honeypot_action = str(honeypot_sanction.get("action", "timeout")).lower()
        honeypot_duration = str(honeypot_sanction.get("duration", "") or "")
        if honeypot_action == "timeout":
            honeypot_summary = f"Timeout ({honeypot_duration or '1d'})"
        else:
            honeypot_summary = honeypot_action.title() if honeypot_action in {"kick", "ban"} else "None"
        honeypot_value = f"{honeypot_channel}\nSanction: {honeypot_summary}" if guild_config.get("honeypot_channel_id") else f"{honeypot_channel}\nSanction: None"

        if self.page == 1:
            self.welcome_button = Button(label="Remove" if guild_config.get("welcome_channel_id") else "Set", style=discord.ButtonStyle.primary, custom_id="channel_welcome_toggle")
            self.goodbye_button = Button(label="Remove" if guild_config.get("goodbye_channel_id") else "Set", style=discord.ButtonStyle.primary, custom_id="channel_goodbye_toggle")
            self.level_button = Button(label="Remove" if level_id else "Set", style=discord.ButtonStyle.primary, custom_id="channel_level_toggle")
            self.admin_button = Button(label=admin_label, style=discord.ButtonStyle.primary, custom_id="channel_admin_toggle")
            self.honeypot_button = Button(label="Remove" if guild_config.get("honeypot_channel_id") else "Set", style=discord.ButtonStyle.primary, custom_id="channel_honeypot_toggle")

            self.welcome_button.callback = self.handle_welcome_toggle
            self.goodbye_button.callback = self.handle_goodbye_toggle
            self.level_button.callback = self.handle_level_toggle
            self.admin_button.callback = self.handle_admin_toggle
            self.honeypot_button.callback = self.handle_honeypot_toggle

            page_button = Button(label="Page 2", style=discord.ButtonStyle.secondary, custom_id="channel_settings_next")
            page_button.callback = self.open_page_two
        else:
            self.board_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="channel_board_edit")
            self.counter_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="channel_counter_edit")
            self.ticket_config_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="channel_ticket_settings_edit")

            self.board_button.callback = self.handle_board_edit
            self.counter_button.callback = self.handle_counter_edit
            self.ticket_config_button.callback = self.handle_ticket_settings_edit

            page_button = Button(label="Page 1", style=discord.ButtonStyle.secondary, custom_id="channel_settings_prev")
            page_button.callback = self.open_page_one

        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="channel_settings_back")
        self.back_button.callback = self.handle_back

        container_items = [
            TextDisplay("<:gear:1517576939097952496> **Channel settings**"),
            TextDisplay(f"Page {self.page}/2 - Set and remove channel settings below."),
            Separator(),
        ]

        if self.page == 1:
            container_items += [
                Section(f"<:plus:1518348756570079262> Welcome Channel\n{welcome_channel}", accessory=self.welcome_button),
                Section(f"<:minus:1518348754111959150> Goodbye Channel\n{goodbye_channel}", accessory=self.goodbye_button),
                Section(f"<:chalice:1517579767573123092> Level-up and Quest Announce Channel\n{level_channel}", accessory=self.level_button),
                Section(f"<:unlocked:1517574880034558102> Admin Log Channel\n{admin_value}", accessory=self.admin_button),
                Section(f"<:honey:1524116282075512842> Honeypot Channel\n{honeypot_value}", accessory=self.honeypot_button),
            ]
        else:
            board_text = "\n".join(board_entries) if board_entries else "None"
            counter_text = "\n".join(counter_entries) if counter_entries else "None"
            ticket_style = guild_config.get("ticket_style", "button").title()
            ticket_reasons = guild_config.get("ticket_reasons", []) or []
            ticket_channel_ref = format_channel_reference(guild, guild_config.get("ticket_channel_id")) if guild else "None"
            ticket_role_ref = format_role_reference(guild, guild_config.get("ticket_manager_role_id")) if guild else "None"
            ticket_reasons_text = "None" if not ticket_reasons else "\n".join(f"- {reason}" for reason in ticket_reasons[:10])
            ticket_config_text = f"Style: {ticket_style}\nChannel: {ticket_channel_ref}\nManager: {ticket_role_ref}\nReasons:\n{ticket_reasons_text}"
            container_items += [
                Section(f"<:list:1517497572770451567> Board Channels\n{board_text}", accessory=self.board_button),
                Section(f"<:multi:1518348755261460661> Counter Channels\n{counter_text}", accessory=self.counter_button),
                Section(f"<:ticket:1520000000000000000> Ticket Settings\n{ticket_config_text}", accessory=self.ticket_config_button),
            ]

        container = Container(*container_items, accent_color=self.color)
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(page_button, self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
        if settings_message is None:
            settings_message = interaction.message
            if settings_message is None:
                try:
                    settings_message = await interaction.original_response()
                except (discord.NotFound, discord.HTTPException):
                    settings_message = None
        if settings_message is None:
            return
        try:
            await settings_message.edit(view=view)
            return
        except (discord.NotFound, discord.HTTPException):
            pass

        try:
            await interaction.followup.edit_message(message_id=settings_message.id, view=view)
            return
        except Exception:
            pass

        try:
            await interaction.edit_original_response(view=view)
        except Exception:
            pass

    async def handle_back(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

    async def handle_close(self, interaction: discord.Interaction):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(view=self)

    async def open_page_two(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2))

    async def open_page_one(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1))

    async def handle_welcome_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("welcome_channel_id"):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Please confirm removal of the welcome channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_welcome, interaction.message), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the welcome channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select welcome channel", self.set_welcome_channel, interaction.message),
            ephemeral=True,
        )

    async def set_welcome_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["welcome_channel_id"] = channel.id
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Welcome channel set to {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_welcome(self, interaction: discord.Interaction, original_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["welcome_channel_id"] = None
        save_guild_data(data)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Welcome channel has been removed.", ephemeral=True)

    async def handle_goodbye_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("goodbye_channel_id"):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Please confirm removal of the goodbye channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_goodbye, interaction.message), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the goodbye channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select goodbye channel", self.set_goodbye_channel, interaction.message),
            ephemeral=True,
        )

    async def set_goodbye_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["goodbye_channel_id"] = channel.id
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Goodbye channel set to {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_goodbye(self, interaction: discord.Interaction, original_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["goodbye_channel_id"] = None
        save_guild_data(data)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Goodbye channel has been removed.", ephemeral=True)

    async def handle_level_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        level_id = get_level_channel_id(self.guild_id)
        if level_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Please confirm removal of the level-up announce channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_level_channel, interaction.message), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the level-up announce channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select level-up announce channel", self.set_level_channel, interaction.message),
            ephemeral=True,
        )

    async def set_level_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        set_level_channel(self.guild_id, channel.id)
        await safe_send(interaction, f"<:approve:1517452125687513158> Level-up announce channel set to {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_level_channel(self, interaction: discord.Interaction, original_message: discord.Message):
        set_level_channel(self.guild_id, None)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Level-up announce channel has been removed.", ephemeral=True)

    async def handle_admin_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        admin_ids = get_guild_admin_log_channel_ids(guild)
        if admin_ids:
            channel = guild.get_channel(admin_ids[0])
            if channel:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    f"Confirm removing admin logging from {channel.mention}?",
                    view=ConfirmRemoveView(self.user_id, self.confirm_remove_admin_log, interaction.message),
                    ephemeral=True,
                )
                return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the admin log channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select admin log channel", self.add_admin_log_channel, interaction.message),
            ephemeral=True,
        )

    async def add_admin_log_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        admin_log_channels[channel.id] = True
        save_lock_config(locked_channels, admin_log_channels)
        await safe_send(interaction, f"<:approve:1517452125687513158> Admin logging enabled in {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_admin_log(self, interaction: discord.Interaction, original_message: discord.Message):
        admin_ids = get_guild_admin_log_channel_ids(interaction.guild)
        if admin_ids:
            admin_log_channels.pop(admin_ids[0], None)
            save_lock_config(locked_channels, admin_log_channels)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send(f"<:trash:1517497581058527404> Admin logging disabled.", ephemeral=True)

    async def handle_board_edit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Board Channels?",
            view=ChannelEditChoiceView(self.user_id, "Board Channels", self.open_board_add, self.open_board_remove, interaction.message),
            ephemeral=True,
        )

    async def open_board_add(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the board channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select board channel", self.board_channel_selected, settings_message),
            ephemeral=True,
        )

    async def board_channel_selected(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Unable to continue board configuration.", ephemeral=True)
        prompt = await interaction.channel.send(
            f"{interaction.user.mention}, react to this message with the emoji you want to use for the board. You have 60 seconds.",
        )
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("React to the channel prompt to choose the board emoji.", ephemeral=True)

        def check(reaction, user):
            return (
                user.id == interaction.user.id
                and reaction.message.id == prompt.id
            )

        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await prompt.delete()
            return await interaction.followup.send("<:disapprove:1517452151012589662> Emoji selection timed out.", ephemeral=True)

        emoji = str(reaction.emoji)
        await prompt.delete()
        await interaction.followup.send(
            "Emoji received. Set the required reaction count.",
            view=BoardCountPromptView(self.user_id, channel, emoji, settings_message, self.add_board_channel),
            ephemeral=True,
        )

    async def add_board_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, emoji: str, required_count: int, settings_message: discord.Message):
        board_data = load_board_data()
        if self.guild_id not in board_data:
            board_data[self.guild_id] = {}
        board_data[self.guild_id][emoji] = {
            "channel_id": channel.id,
            "required_count": required_count,
            "tracked_messages": {},
        }
        save_board_data(board_data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Board for {emoji} saved to {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def open_board_remove(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the board channel to remove:",
            view=ChannelSelectorView(self.user_id, guild, "Select board channel to remove", self.remove_board_channel, settings_message),
            ephemeral=True,
        )

    async def remove_board_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        board_data = load_board_data()
        if self.guild_id not in board_data:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No board channels are configured.", ephemeral=True)
            return
        removed = False
        for emoji_key, cfg in list(board_data[self.guild_id].items()):
            if cfg.get("channel_id") == channel.id:
                del board_data[self.guild_id][emoji_key]
                removed = True
        if removed:
            if not board_data[self.guild_id]:
                del board_data[self.guild_id]
            save_board_data(board_data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Removed board channel {channel.mention}.", ephemeral=True)
            await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> That channel is not configured as a board channel.", ephemeral=True)

    async def handle_counter_edit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Counter Channels?",
            view=ChannelEditChoiceView(self.user_id, "Counter Channels", self.open_counter_add, self.open_counter_remove, interaction.message),
            ephemeral=True,
        )

    async def open_counter_add(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the counter channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select counter channel", self.counter_channel_selected, settings_message),
            ephemeral=True,
        )

    async def counter_channel_selected(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        async def yes_callback(interact: discord.Interaction):
            await self.add_counter_channel(interact, channel, True, settings_message)

        async def no_callback(interact: discord.Interaction):
            await self.add_counter_channel(interact, channel, False, settings_message)

        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"Should failures reset the counter in {channel.mention}?",
            view=YesNoView(self.user_id, yes_callback, no_callback),
            ephemeral=True,
        )

    async def add_counter_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, reset_on_fail: bool, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config.setdefault("counter_channels", {})[str(channel.id)] = {
            "current_value": 0,
            "last_user_id": None,
            "reset_on_fail": reset_on_fail,
        }
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Counter channel configured for {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def open_counter_remove(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the counter channel to remove:",
            view=ChannelSelectorView(self.user_id, guild, "Select counter channel to remove", self.remove_counter_channel, settings_message),
            ephemeral=True,
        )

    async def remove_counter_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        if str(channel.id) not in guild_config.get("counter_channels", {}):
            await safe_send(interaction, "<:disapprove:1517452151012589662> That channel is not configured as a counter channel.", ephemeral=True)
            return
        del guild_config["counter_channels"][str(channel.id)]
        save_guild_data(data)
        await safe_send(interaction, f"<:trash:1517497581058527404> Removed counter channel {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def handle_ticket_settings_edit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_modal(TicketConfigModal(self.set_ticket_config_flow, self.guild_id, interaction.message))

    async def set_ticket_config_flow(self, interaction: discord.Interaction, style: str, reasons: list[str], settings_message: discord.Message | None):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["ticket_style"] = style
        guild_config["ticket_reasons"] = reasons
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Ticket settings saved. Next, select the ticket channel.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)
        guild = interaction.guild
        if not guild:
            return
        await interaction.followup.send(
            "Select the ticket channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select ticket channel", self.set_ticket_channel_flow, settings_message),
            ephemeral=True,
        )

    async def set_ticket_channel_flow(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message | None):
        if getattr(channel, "type", None) != discord.ChannelType.text:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please select a text channel for the ticket channel.", ephemeral=True)
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["ticket_channel_id"] = channel.id
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Ticket channel set to {channel.mention}. Next, select the ticket manager role.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)
        guild = interaction.guild
        if not guild:
            return
        await interaction.followup.send(
            "Select the ticket manager role:",
            view=RoleSelectorView(self.user_id, guild, "Select ticket manager role", self.set_ticket_role_flow, settings_message),
            ephemeral=True,
        )

    async def set_ticket_role_flow(self, interaction: discord.Interaction, role: discord.Role, settings_message: discord.Message | None):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["ticket_manager_role_id"] = role.id
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Ticket manager role set to {role.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)
        await refresh_ticket_announce_message(self.guild_id)

    async def handle_ticket_channel_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("ticket_channel_id"):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Please confirm removal of the ticket channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_ticket_channel, interaction.message), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the ticket channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select ticket channel", self.set_ticket_channel, interaction.message),
            ephemeral=True,
        )

    async def handle_ticket_role_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("ticket_manager_role_id"):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Please confirm removal of the ticket manager role.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_ticket_role, interaction.message), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the ticket manager role:",
            view=RoleSelectorView(self.user_id, guild, "Select ticket manager role", self.set_ticket_manager_role, interaction.message),
            ephemeral=True,
        )

    async def set_ticket_config(self, interaction: discord.Interaction, style: str, reasons: list[str], settings_message: discord.Message | None):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["ticket_style"] = style
        guild_config["ticket_reasons"] = reasons
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Ticket settings updated.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)
        await refresh_ticket_announce_message(self.guild_id)

    async def set_ticket_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        if getattr(channel, "type", None) != discord.ChannelType.text:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please select a text channel for the ticket channel.", ephemeral=True)
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["ticket_channel_id"] = channel.id
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Ticket channel set to {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)
        await refresh_ticket_announce_message(self.guild_id)

    async def confirm_remove_ticket_channel(self, interaction: discord.Interaction, original_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["ticket_channel_id"] = None
        guild_config["ticket_announce_message_id"] = None
        save_guild_data(data)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Ticket channel has been removed.", ephemeral=True)

    async def set_ticket_manager_role(self, interaction: discord.Interaction, role: discord.Role, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["ticket_manager_role_id"] = role.id
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Ticket manager role set to {role.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def confirm_remove_ticket_role(self, interaction: discord.Interaction, original_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["ticket_manager_role_id"] = None
        save_guild_data(data)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Ticket manager role has been removed.", ephemeral=True)

    async def handle_honeypot_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("honeypot_channel_id"):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Please confirm removal of the honeypot channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_honeypot, interaction.message), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the honeypot channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select honeypot channel", self.open_honeypot_sanction, interaction.message),
            ephemeral=True,
        )

    async def open_honeypot_sanction(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        resolved_channel = channel
        if interaction.guild and getattr(channel, "id", None):
            resolved_channel = interaction.guild.get_channel(channel.id) or await interaction.guild.fetch_channel(channel.id)
        if not resolved_channel or getattr(resolved_channel, "type", None) != discord.ChannelType.text:
            return await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please select a text channel for the honeypot.", ephemeral=True)
        await interaction.response.send_modal(HoneypotSanctionModal(self.set_honeypot_channel, resolved_channel, settings_message))

    async def set_honeypot_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, action: str, duration_seconds: int, duration_text: str, settings_message: discord.Message):
        resolved_channel = channel
        if interaction.guild and getattr(channel, "id", None):
            resolved_channel = interaction.guild.get_channel(channel.id) or await interaction.guild.fetch_channel(channel.id)

        guild_config, data = get_guild_config(self.guild_id)
        guild_config["honeypot_channel_id"] = getattr(resolved_channel, "id", channel.id)
        guild_config["honeypot_sanction"] = {
            "action": action,
            "duration_seconds": duration_seconds,
            "duration": duration_text,
        }
        save_guild_data(data)
        try:
            if resolved_channel and hasattr(resolved_channel, "send"):
                await resolved_channel.send(f"<:honey:1524116282075512842> This channel is a honeypot. Please do not send messages here. Any message sent here will trigger a sanction.")
        except (discord.Forbidden, discord.HTTPException):
            pass
        await safe_send(interaction, f"<:approve:1517452125687513158> Honeypot channel set to {getattr(resolved_channel, 'mention', str(channel.id))}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_honeypot(self, interaction: discord.Interaction, original_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["honeypot_channel_id"] = None
        guild_config["honeypot_sanction"] = {}
        save_guild_data(data)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Honeypot channel has been removed.", ephemeral=True)



@bot.tree.command(name="settings", description="Open a quick settings menu for your personal and guild preferences")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def settings(interaction: discord.Interaction):
    view = SettingsMenuView(
        interaction.user.id,
        interaction.user.display_name,
        get_user_color_value(str(interaction.user.id)),
    )
    await interaction.response.defer(ephemeral=True); await interaction.followup.send(view=view, ephemeral=True)


@bot.tree.command(name="notes-lists-reminders", description="Manage your notes, checklists, and reminders")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def notes(interaction: discord.Interaction):
    view = NotesMenuView(interaction.user.id)
    await interaction.response.defer(ephemeral=True); await interaction.followup.send(view=view, ephemeral=True)




# -------------------------------------------------------------------------------------------------------------
#                                               Backup BECAUSE IT KEEPS RESETTING THE FILES OMFG IM TIRED OF THIS
# -------------------------------------------------------------------------------------------------------------


def create_backup(root_dir: str = BASE_DIR, backup_folder_name: str = 'backups') -> Path:
    root = Path(root_dir)
    backup_dir = root / backup_folder_name
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    now = datetime.now()
    name = now.strftime("%y.%m.%d.h%H.%M")
    zip_path = backup_dir / f"{name}.zip"

    try:
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for p in root.rglob('*.json'):
                if p.is_file():
                    try:
                        arcname = p.relative_to(root).as_posix()
                    except Exception:
                        arcname = p.name
                    zf.write(p, arcname)
        print(f"Created JSON backup: {zip_path}")
    except Exception as e:
        print(f"Failed to create backup {zip_path}: {e}")

    return zip_path


def _backup_worker(interval_seconds: int = 3600, root_dir: str = BASE_DIR):
    while True:
        time.sleep(interval_seconds)
        try:
            create_backup(root_dir)
        except Exception as e:
            print(f"Backup error: {e}")


def start_backup_scheduler(interval_seconds: int = 3600, root_dir: str = BASE_DIR):
    try:
        create_backup(root_dir)
    except Exception as e:
        print(f"Initial backup failed: {e}")

    t = threading.Thread(target=_backup_worker, args=(interval_seconds, root_dir), daemon=True)
    t.start()
    return t


def get_backup_dir() -> Path:
    return Path(BASE_DIR) / 'backups'


def get_backup_files() -> list[Path]:
    backup_dir = get_backup_dir()
    if not backup_dir.exists():
        return []
    return sorted([p for p in backup_dir.iterdir() if p.is_file() and p.suffix == '.zip'], key=lambda p: p.name, reverse=True)


def format_backup_entry(path: Path) -> str:
    modified = datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    size = path.stat().st_size
    return f"{path.name} · {size} bytes · {modified}"


class BackupListView(LayoutView):
    def __init__(self, user_id: int, page: int = 1):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.page = page
        self.message: discord.Message | None = None
        self.backup_files = get_backup_files()
        self.build_components()

    def build_components(self):
        self.clear_items()
        total_backups = len(self.backup_files)
        total_pages = max(1, math.ceil(total_backups / 5))
        current_page = min(max(1, self.page), total_pages)
        start_index = (current_page - 1) * 5
        page_backups = self.backup_files[start_index:start_index + 5]

        title = "Backup files"
        description = f"Page {current_page}/{total_pages} · {total_backups} backup(s) available."
        container_items = [
            TextDisplay(f"<:floppy_disk:1517577943290188033> **{title}**"),
            TextDisplay(description),
            Separator(),
        ]

        if not page_backups:
            container_items.append(TextDisplay("No backups found. Run a backup or wait for the scheduler to create one."))
        else:
            for index, backup_path in enumerate(page_backups, start=start_index + 1):
                file_label = f"{index}. {backup_path.name}"
                backup_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id=f"backup_edit_{current_page}_{index}")

                async def backup_callback(interaction: discord.Interaction, backup_file=backup_path):
                    await self.open_backup_actions(interaction, backup_file)

                backup_button.callback = backup_callback
                container_items.append(Section(f"{file_label}\n{format_backup_entry(backup_path)}", accessory=backup_button))

        self.add_item(Container(*container_items, accent_color=discord.Color.blurple()))

        prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="backup_prev")
        next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="backup_next")
        create_button = Button(label="Create Backup", style=discord.ButtonStyle.success, custom_id="backup_create")
        close_button = Button(label="Close", style=discord.ButtonStyle.danger, custom_id="backup_close")
        prev_button.callback = self.open_previous_page
        next_button.callback = self.open_next_page
        create_button.callback = self.create_backup
        close_button.callback = self.close_view
        prev_button.disabled = current_page <= 1
        next_button.disabled = current_page >= total_pages

        self.add_item(discord.ui.ActionRow(prev_button, next_button, create_button, close_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This backup panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def open_previous_page(self, interaction: discord.Interaction):
        new_view = BackupListView(self.user_id, page=self.page - 1)
        new_view.message = interaction.message
        await interaction.response.edit_message(view=new_view)

    async def open_next_page(self, interaction: discord.Interaction):
        new_view = BackupListView(self.user_id, page=self.page + 1)
        new_view.message = interaction.message
        await interaction.response.edit_message(view=new_view)

    async def create_backup(self, interaction: discord.Interaction):
        backup_path = create_backup(BASE_DIR)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Created backup `{backup_path.name}`.", ephemeral=True)
        if self.message is None and interaction.message is not None:
            self.message = interaction.message
        if self.message:
            refreshed_view = BackupListView(self.user_id, page=self.page)
            refreshed_view.message = self.message
            await self.message.edit(view=refreshed_view)

    async def close_view(self, interaction: discord.Interaction):
        if interaction.message:
            await interaction.message.delete()
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Backup list closed.", ephemeral=True)

    async def open_backup_actions(self, interaction: discord.Interaction, backup_file: Path):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"What would you like to do with `{backup_file.name}`?",
            view=BackupActionView(self.user_id, backup_file, self),
            ephemeral=True,
        )


class BackupActionView(discord.ui.View):
    def __init__(self, user_id: int, backup_file: Path, list_view: BackupListView):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.backup_file = backup_file
        self.list_view = list_view
        self.load_button = Button(label="Load", style=discord.ButtonStyle.success, custom_id="backup_action_load")
        self.delete_button = Button(label="Delete", style=discord.ButtonStyle.danger, custom_id="backup_action_delete")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="backup_action_cancel")
        self.load_button.callback = self.load_callback
        self.delete_button.callback = self.delete_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.load_button)
        self.add_item(self.delete_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def load_callback(self, interaction: discord.Interaction):
        modal = BackupPasswordModal(self.user_id, self.backup_file, "load", self.list_view)
        await interaction.response.send_modal(modal)

    async def delete_callback(self, interaction: discord.Interaction):
        modal = BackupPasswordModal(self.user_id, self.backup_file, "delete", self.list_view)
        await interaction.response.send_modal(modal)

    async def cancel_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Backup action cancelled.", view=None)


class BackupPasswordModal(Modal):
    def __init__(self, user_id: int, backup_file: Path, action: str, list_view: BackupListView):
        super().__init__(title=f"Confirm {action.title()} Backup")
        self.user_id = user_id
        self.backup_file = backup_file
        self.action = action
        self.list_view = list_view
        self.password_input = TextInput(label="Owner password", style=discord.TextStyle.short, placeholder="Enter OWN_PASSWORD from .env", required=True, min_length=1)
        self.add_item(self.password_input)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This password prompt is only for the original user.", ephemeral=True)
            return

        if not OWN_PASSWORD:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> OWN_PASSWORD is not configured in .env.", ephemeral=True)
            return

        if self.password_input.value != OWN_PASSWORD:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Incorrect password.", ephemeral=True)
            return

        if self.action == "load":
            await self.perform_load(interaction)
        elif self.action == "delete":
            await self.perform_delete(interaction)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Unknown action.", ephemeral=True)

    async def perform_load(self, interaction: discord.Interaction):
        if not self.backup_file.exists():
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Backup file no longer exists.", ephemeral=True)
            return

        try:
            backup_before_restore = create_backup(BASE_DIR)
            with zipfile.ZipFile(self.backup_file, 'r') as zf:
                zf.extractall(path=BASE_DIR)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:approve:1517452125687513158> Loaded backup `{self.backup_file.name}` and created current backup `{backup_before_restore.name}`.",
                ephemeral=True,
            )
            if self.list_view.message:
                await self.list_view.message.edit(view=BackupListView(self.user_id, page=self.list_view.page))
        except Exception as e:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> Failed to load backup: {e}", ephemeral=True)

    async def perform_delete(self, interaction: discord.Interaction):
        if not self.backup_file.exists():
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Backup file no longer exists.", ephemeral=True)
            return

        try:
            self.backup_file.unlink()
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:trash:1517497581058527404> Deleted backup `{self.backup_file.name}`.",
                ephemeral=True,
            )
            if self.list_view.message:
                await self.list_view.message.edit(view=BackupListView(self.user_id, page=self.list_view.page))
        except Exception as e:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> Failed to delete backup: {e}", ephemeral=True)


start_backup_scheduler()

bot.run(TOKEN)