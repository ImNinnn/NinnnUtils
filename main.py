import asyncio
import ast
import json
import os
import math
import random
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from collections import Counter
import yt_dlp
import discord
from discord import ComponentType, app_commands, Status
from discord.automod import AutoModRuleAction, AutoModTrigger
from discord.enums import AutoModRuleActionType, AutoModRuleEventType, AutoModRuleTriggerType
from discord.ext import tasks, commands
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence
import io
import unicodedata
from deep_translator import GoogleTranslator
import base64
import queue
import threading
import traceback
import zipfile
from pathlib import Path
from discord.ui import Modal, Separator, TextInput, View, Button, LayoutView, Container, Section, TextDisplay, MediaGallery, ChannelSelect
from pypresence import Presence
from pypresence.types import ActivityType
import aiohttp



# -------------------------------------------------------------------------------------------------------------
#                                               Configuration
# -------------------------------------------------------------------------------------------------------------




load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
VERSION = os.getenv('BOT_VERSION')
VERSION_ALTERNATE = os.getenv('BOT_VERSION_ALTERNATE')
RPC_CLIENT_ID = os.getenv('DISCORD_RPC_CLIENT_ID', '').strip()
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
FFMPEG_PATH = os.path.join(BASE_DIR, "ffmpeg.exe")
LEVEL_FILE = os.path.join(BASE_DIR, 'level.json')
USER_FILE = os.path.join(BASE_DIR, 'user.json')
GIVEAWAY_FILE = os.path.join(BASE_DIR, 'giveaway.json')




# -------------------------------------------------------------------------------------------------------------
#                                               Bot Setup
# -------------------------------------------------------------------------------------------------------------




class MyDiscordApp(commands.AutoShardedBot):
    def __init__(self, intents, shard_count: int = 0):
        super().__init__(
            command_prefix={PREFIX},
            intents=intents,
            shard_count=shard_count or None,
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
intents.presences = True
intents.auto_moderation_execution = True
bot = MyDiscordApp(intents=intents, shard_count=SHARD_COUNT)


YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}


FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

song_queues = {}

def get_song_queue(guild_id: str) -> dict:
    return song_queues.setdefault(guild_id, {
        'tracks': [],
        'current_index': 0,
        'loop': False,
        'stop_action': None,
        'now_playing_message_id': None,
        'now_playing_channel_id': None,
        'now_playing_task': None,
        'track_start_time': None,
        'accumulated_pause': 0.0,
        'pause_started_at': None,
    })


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def build_progress_bar(elapsed: float, duration: float, length: int = 20) -> str:
    if duration <= 0:
        return "<:Square_Brown:1517679892039204955>" * length
    progress = min(max(int((elapsed / duration) * length), 0), length)
    filled = "<:Square_Brown:1517679892039204955>" * progress
    empty = "<:Square_Black:1517679889615032540>" * (length - progress)
    return f"{filled}{empty}"


def get_current_elapsed(queue: dict) -> float:
    if not queue.get('track_start_time'):
        return 0.0
    if queue.get('pause_started_at'):
        return max(0.0, queue['pause_started_at'] - queue['track_start_time'] - queue['accumulated_pause'])
    return max(0.0, time.time() - queue['track_start_time'] - queue['accumulated_pause'])


def build_song_embed(guild_id: str) -> discord.Embed | None:
    queue = get_song_queue(guild_id)
    if not queue['tracks'] or queue['current_index'] >= len(queue['tracks']):
        return None

    track = queue['tracks'][queue['current_index']]
    duration = track.get('duration', 0) or 0
    elapsed = get_current_elapsed(queue)
    elapsed = min(elapsed, duration)
    remaining = max(duration - elapsed, 0)
    progress = build_progress_bar(elapsed, duration)
    index = queue['current_index'] + 1
    total = len(queue['tracks'])


    end_time_unix = int(time.time() + remaining)
    discord_time_remaining = f"<t:{end_time_unix}:R>"
    if queue.get('pause_started_at') or not queue.get('track_start_time'):
        discord_elapsed = format_duration(elapsed)
    else:
        discord_elapsed = f"<t:{int(queue['track_start_time'])}:R>"

    embed = discord.Embed(
        title="<:music:1517575582764765224> Now Playing",
        description=f"**{track.get('title', 'Unknown Title')}**",
        color=discord.Color.from_rgb(130, 84, 54)
    )

    thumbnail = track.get('thumbnail')
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    status = "Paused" if queue.get('pause_started_at') else "Playing"
    embed.add_field(name="<:list:1517497572770451567> Track", value=f"{index} / {total}", inline=True)
    embed.add_field(name="<:gear:1517576939097952496> Status", value=status, inline=True)
    embed.add_field(name="<:hourglass:1517574046252924938> Time Remaining", value=discord_time_remaining, inline=True)
    embed.add_field(name="<:timer:1517996239583576194> Progress", value=f"{discord_elapsed} / {format_duration(duration)}\n{progress}", inline=False)

    next_tracks = []
    for next_index in range(queue['current_index'] + 1, min(len(queue['tracks']), queue['current_index'] + 6)):
        next_track = queue['tracks'][next_index]
        next_tracks.append(f"{next_index + 1}. {next_track.get('title', 'Unknown Title')}")
    next_text = "\n".join(next_tracks) if next_tracks else "No songs queued."
    embed.add_field(name="<:next:1518977801057861643> Up Next", value=next_text, inline=False)

    if track.get('requested_by'):
        embed.set_footer(text=f"Requested by {track['requested_by']}")

    return embed


class NowPlayingControlsView(discord.ui.View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.update_button_states()

    def update_button_states(self):
        queue = get_song_queue(self.guild_id)
        is_paused = bool(queue.get('pause_started_at'))
        self.pause_button.label = "Resume" if is_paused else "Pause"
        self.pause_button.style = discord.ButtonStyle.success if is_paused else discord.ButtonStyle.secondary

        self.loop_button.label = "Loop: On" if queue.get('loop') else "Loop: Off"
        self.loop_button.style = discord.ButtonStyle.success if queue.get('loop') else discord.ButtonStyle.secondary

        self.previous_button.disabled = queue.get('current_index', 0) <= 0
        self.next_button.disabled = queue.get('current_index', 0) + 1 >= len(queue.get('tracks', []))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None and str(interaction.guild.id) == self.guild_id

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="nowplaying_previous")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = self.guild_id
        queue = get_song_queue(guild_id)
        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("<:disapprove:1517452151012589662> I'm not connected to a voice channel.", ephemeral=True)
            return
        if not queue['tracks']:
            await interaction.response.send_message("<:disapprove:1517452151012589662> The queue is empty.", ephemeral=True)
            return

        if queue['current_index'] >= len(queue['tracks']):
            queue['current_index'] = len(queue['tracks']) - 1

        if queue['current_index'] > 0:
            queue['current_index'] -= 1
            queue['stop_action'] = 'manual'
            voice_client.stop()
            self.update_button_states()
            await interaction.response.send_message(f"<:prev:1518977803092234331> Now playing **{queue['tracks'][queue['current_index']]['title']}**.", ephemeral=True)
            await play_guild_song(guild_id, voice_client)
            return

        await interaction.response.send_message("<:disapprove:1517452151012589662> There is no previous song.", ephemeral=True)

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.secondary, custom_id="nowplaying_pause")
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = self.guild_id
        queue = get_song_queue(guild_id)
        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("<:disapprove:1517452151012589662> I'm not connected to a voice channel.", ephemeral=True)
            return

        if voice_client.is_paused():
            voice_client.resume()
            if queue.get('pause_started_at'):
                queue['accumulated_pause'] += time.time() - queue['pause_started_at']
                queue['pause_started_at'] = None
            await self.refresh_message(interaction)
            await interaction.response.send_message("<:play:1517576855965716> Resumed playback.", ephemeral=True)
            return

        if not voice_client.is_playing():
            await interaction.response.send_message("<:disapprove:1517452151012589662> Nothing is playing right now.", ephemeral=True)
            return

        voice_client.pause()
        queue['pause_started_at'] = time.time()
        await self.refresh_message(interaction)
        await interaction.response.send_message("<:pause:1517497575219920986> Paused the song.", ephemeral=True)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="nowplaying_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = self.guild_id
        queue = get_song_queue(guild_id)
        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("<:disapprove:1517452151012589662> I'm not connected to a voice channel.", ephemeral=True)
            return
        if not queue['tracks']:
            await interaction.response.send_message("<:disapprove:1517452151012589662> The queue is empty.", ephemeral=True)
            return

        if queue['current_index'] >= len(queue['tracks']):
            queue['current_index'] = len(queue['tracks']) - 1

        if queue['current_index'] + 1 < len(queue['tracks']):
            queue['current_index'] += 1
            queue['stop_action'] = 'manual'
            voice_client.stop()
            self.update_button_states()
            await interaction.response.send_message(f"<:next:1518977801057865224> Skipped to **{queue['tracks'][queue['current_index']]['title']}**.", ephemeral=True)
            await play_guild_song(guild_id, voice_client)
            return

        queue['current_index'] = len(queue['tracks'])
        queue['stop_action'] = 'manual'
        voice_client.stop()
        await cleanup_now_playing_embed(guild_id)
        await interaction.response.send_message("<:disapprove:1517452151012589662> No more songs in the queue. Playback stopped.", ephemeral=True)

    @discord.ui.button(label="Loop: Off", style=discord.ButtonStyle.secondary, custom_id="nowplaying_loop")
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = self.guild_id
        queue = get_song_queue(guild_id)
        queue['loop'] = not queue.get('loop', False)
        self.update_button_states()
        await self.refresh_message(interaction)
        state = "enabled" if queue['loop'] else "disabled"
        await interaction.response.send_message(f"<:loop:1518977798939742449> Looping is now {state}.", ephemeral=True)

    async def refresh_message(self, interaction: discord.Interaction):
        self.update_button_states()
        queue = get_song_queue(self.guild_id)
        if not queue.get('now_playing_message_id'):
            return
        channel = get_now_playing_channel(queue)
        if not channel:
            return
        embed = build_song_embed(self.guild_id)
        if not embed:
            return
        try:
            message = await channel.fetch_message(queue['now_playing_message_id'])
            await message.edit(embed=embed, view=self)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass


async def cleanup_now_playing_embed(guild_id: str):
    queue = get_song_queue(guild_id)
    task = queue.get('now_playing_task')
    queue['now_playing_task'] = None
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    channel_id = queue.get('now_playing_channel_id')
    message_id = queue.get('now_playing_message_id')
    queue['now_playing_message_id'] = None
    if not channel_id or not message_id:
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        return

    try:
        message = await channel.fetch_message(message_id)
        await message.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


def get_now_playing_channel(queue: dict) -> discord.TextChannel | None:
    if not queue.get('now_playing_channel_id'):
        return None
    return bot.get_channel(queue['now_playing_channel_id'])


async def refresh_now_playing_embed(guild_id: str):
    queue = get_song_queue(guild_id)
    if not queue.get('now_playing_message_id'):
        return
    channel = get_now_playing_channel(queue)
    if not channel:
        return
    embed = build_song_embed(guild_id)
    if not embed:
        return
    try:
        message = await channel.fetch_message(queue['now_playing_message_id'])
        view = queue.get('now_playing_view')
        if view:
            view.update_button_states()
            await message.edit(embed=embed, view=view)
        else:
            await message.edit(embed=embed)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


async def update_now_playing_embed_loop(guild_id: str):
    queue = get_song_queue(guild_id)
    while True:
        await asyncio.sleep(10)
        if not queue.get('now_playing_message_id') or not queue.get('tracks'):
            break
        if queue['current_index'] >= len(queue['tracks']):
            break
        await refresh_now_playing_embed(guild_id)
    queue['now_playing_task'] = None


async def start_now_playing_embed(guild_id: str):
    queue = get_song_queue(guild_id)
    if not queue.get('tracks') or queue['current_index'] >= len(queue['tracks']):
        return
    if not queue.get('now_playing_channel_id'):
        return

    await cleanup_now_playing_embed(guild_id)
    channel = get_now_playing_channel(queue)
    if not channel:
        return

    embed = build_song_embed(guild_id)
    if not embed:
        return

    try:
        view = queue.get('now_playing_view')
        if view is None:
            view = NowPlayingControlsView(guild_id)
            queue['now_playing_view'] = view
        else:
            view.update_button_states()

        message = await channel.send(embed=embed, view=view)
        queue['now_playing_message_id'] = message.id
        queue['now_playing_task'] = asyncio.create_task(update_now_playing_embed_loop(guild_id))
    except Exception:
        queue['now_playing_message_id'] = None
        queue['now_playing_task'] = None


async def play_guild_song(guild_id: str, voice_client: discord.VoiceClient) -> bool:
    queue = get_song_queue(guild_id)
    if not queue['tracks']:
        return False

    if queue['current_index'] >= len(queue['tracks']):
        queue['current_index'] = len(queue['tracks']) - 1

    track = queue['tracks'][queue['current_index']]
    try:
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(track['url'], download=False)
            stream_url = info['url']
            track['duration'] = int(info.get('duration') or 0)
            track['thumbnail'] = info.get('thumbnail')

        audio_source = discord.FFmpegPCMAudio(stream_url, executable=FFMPEG_PATH, **FFMPEG_OPTIONS)

        def after_play(error):
            if error:
                print(f"Playback ended. Error: {error}")
            bot.loop.call_soon_threadsafe(asyncio.create_task, playback_ended(guild_id, error))

        voice_client.play(audio_source, after=after_play)
        queue['track_start_time'] = time.time()
        queue['accumulated_pause'] = 0.0
        queue['pause_started_at'] = None
        await start_now_playing_embed(guild_id)
        return True
    except Exception as e:
        print(f"Failed to start playback: {e}")
        return False

async def playback_ended(guild_id: str, error=None):
    queue = get_song_queue(guild_id)
    if queue.get('stop_action'):
        queue['stop_action'] = None
        return

    if queue['loop'] and queue['tracks']:
        guild = bot.get_guild(int(guild_id))
        voice_client = guild.voice_client if guild else None
        if voice_client and voice_client.is_connected():
            await play_guild_song(guild_id, voice_client)
        return

    is_last_track = queue['current_index'] + 1 >= len(queue['tracks'])
    if is_last_track:
        await refresh_now_playing_embed(guild_id)

    queue['current_index'] += 1
    if queue['current_index'] < len(queue['tracks']):
        guild = bot.get_guild(int(guild_id))
        voice_client = guild.voice_client if guild else None
        if voice_client and voice_client.is_connected():
            await play_guild_song(guild_id, voice_client)
        return

    return





# -------------------------------------------------------------------------------------------------------------
#                                               Message Cache
# -------------------------------------------------------------------------------------------------------------




message_cache = []
deleted_cache = []
edited_cache = []
bot_error_cache = []
active_minigame_users = set()
server_pauses = {}
all_paused_guilds = set()
reaction_xp_cooldowns = {}
local_rpc = None
local_rpc_thread = None
local_rpc_stop_event = threading.Event()
local_rpc_queue = queue.Queue(maxsize=1)




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
    """Unified data loading and saving for all JSON files"""
    _cache = {}
    
    @classmethod
    def load(cls, file_path: str, default=None):
        """Load data from JSON file with optional caching"""
        if default is None:
            default = {}
        return load_json_file(file_path, default)
    
    @classmethod
    def save(cls, file_path: str, data):
        """Save data to JSON file"""
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
    """Build embed for giveaway display."""
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
        super().__init__(timeout=60)
        self.giveaway_id = giveaway_id
        self.original_message = original_message
        self.user_id = user_id

    @discord.ui.button(label="Leave giveaway", style=discord.ButtonStyle.danger)
    async def confirm_leave(self, interaction: discord.Interaction, button: Button):
        data = load_giveaway_data()
        giveaway = data.get(self.giveaway_id)
        if not giveaway or giveaway.get('status') != 'active':
            await interaction.response.send_message("This giveaway is no longer active.", ephemeral=True)
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

        await interaction.response.send_message("You left the giveaway.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_leave(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Okay, you stayed in the giveaway.", ephemeral=True)


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
            label="Join / Leave",
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
            await channel.send(f"<:spark:1517583248421552305> Giveaway **{giveaway['name']}** has ended! Winners: {winner_text}")
        else:
            await channel.send(f"<:spark:1517583248421552305> Giveaway **{giveaway['name']}** has ended with no entries.")

    data = load_giveaway_data()
    if giveaway_id in data:
        del data[giveaway_id]
        save_giveaway_data(data)


@tasks.loop(minutes=1)
async def giveaway_loop():
    data = load_giveaway_data()
    if not data:
        return

    now = int(datetime.now(timezone.utc).timestamp())
    for giveaway_id, giveaway in list(data.items()):
        if giveaway.get('status') != 'active':
            continue
        if int(giveaway.get('end_time', 0)) <= now:
            await finalize_giveaway(giveaway_id, giveaway)


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


def parse_reminder_time(value: str) -> int | None:
    if not value:
        return None
    text = value.strip()
    if text.lower().startswith("in "):
        seconds = parse_duration_to_seconds(text[3:])
        if seconds is None or seconds <= 0:
            return None
        return int(datetime.now(timezone.utc).timestamp()) + seconds

    match = re.fullmatch(r"at\s+(\d{2})/(\d{2})/(\d{2})\s+(\d{1,2}):(\d{2})", text, re.IGNORECASE)
    if match:
        year = 2000 + int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        hour = int(match.group(4))
        minute = int(match.group(5))
        try:
            reminder_dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        except ValueError:
            return None
        if reminder_dt <= datetime.now(timezone.utc):
            return None
        return int(reminder_dt.timestamp())

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


def get_reminder_destination(reminder: dict, guild: discord.Guild | None = None) -> str:
    send_mode = reminder.get("send", "dm")
    if send_mode == "channel":
        channel_id = reminder.get("channel_id")
        if channel_id and guild:
            channel = guild.get_channel(channel_id)
            return channel.mention if channel else f"<#{channel_id}>"
        return "channel"
    if send_mode == "both":
        channel_id = reminder.get("channel_id")
        if channel_id and guild:
            channel = guild.get_channel(channel_id)
            channel_text = channel.mention if channel else f"<#{channel_id}>"
        else:
            channel_text = "channel"
        return f"{channel_text} and DM"
    return "DM"


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
            placeholder="in 1d 30m 10s or at yy/mm/dd hh:mm",
            required=True,
            default=f"at {datetime.utcfromtimestamp(current_time):%y/%m/%d %H:%M}",
        )
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction):
        data = PENDING_POSTPONE_REMINDERS.get(self.postpone_id)
        if not data or str(interaction.user.id) != data["user_id"]:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This postpone link is no longer valid.", ephemeral=True)
            return

        reminder = data["reminder"]
        new_time = parse_reminder_time(self.time_input.value)
        if new_time is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Invalid reminder time. Use in 1h or at 24/12/26 18:00.", ephemeral=True)
            return

        new_reminder = {
            "name": reminder.get("name", "Reminder"),
            "description": reminder.get("description", ""),
            "when": new_time,
            "send": reminder.get("send", "dm"),
        }
        if reminder.get("channel_id"):
            new_reminder["channel_id"] = reminder["channel_id"]

        reminders = get_user_reminders(str(self.user_id))
        if len(reminders) >= MAX_USER_REMINDERS:
            await interaction.response.send_message(
                "<:disapprove:1517452151012589662> You can have up to 7 reminders at once.",
                ephemeral=True,
            )
            return

        reminders.append(new_reminder)
        save_user_reminders(str(self.user_id), reminders)
        PENDING_POSTPONE_REMINDERS.pop(self.postpone_id, None)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Reminder postponed to <t:{new_time}:F>.", ephemeral=True)


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
        ]
        if self.mention_user:
            details.append(TextDisplay(f"<@{self.user_id}>"))

        container = Container(*details, accent_color=get_user_color_value(str(self.user_id)))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("<:disapprove:1517452151012589662> Only the reminder owner can postpone this reminder.", ephemeral=True)
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

    send_mode = reminder.get("send", "dm")
    if send_mode in {"dm", "both"} and user:
        try:
            await user.send(view=ReminderNotificationView(str(user_id), postpone_id, reminder, mention_user=False))
        except Exception:
            pass

    if send_mode in {"channel", "both"}:
        channel_id = reminder.get("channel_id")
        if channel_id:
            channel = bot.get_channel(int(channel_id)) if isinstance(channel_id, int) else None
            if channel:
                try:
                    await channel.send(view=ReminderNotificationView(str(user_id), postpone_id, reminder, mention_user=True))
                except Exception:
                    pass


@tasks.loop(minutes=1)
async def reminder_loop():
    settings = load_user_settings()
    if not settings:
        return

    now = int(datetime.now(timezone.utc).timestamp())
    changed = False

    users = settings.get("users")
    if not isinstance(users, dict):
        return

    for user_id, user_settings in list(users.items()):
        reminders = user_settings.get("reminders")
        if not isinstance(reminders, list):
            continue

        remaining_reminders = []
        for reminder in reminders:
            if not isinstance(reminder, dict):
                continue
            when = reminder.get("when")
            if isinstance(when, int) and when <= now:
                await deliver_reminder(user_id, reminder)
                changed = True
            else:
                remaining_reminders.append(reminder)

        if len(remaining_reminders) != len(reminders):
            user_settings["reminders"] = remaining_reminders

    if changed:
        save_user_settings(settings)


@reminder_loop.before_loop
async def before_reminder_loop():
    await bot.wait_until_ready()


def is_valid_send_mode(value: str) -> bool:
    return str(value).strip().lower() in {"dm", "channel", "both"}


def normalize_send_mode(value: str) -> str:
    return str(value).strip().lower() if is_valid_send_mode(value) else "dm"


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


def get_afk_reason(entry: dict | None) -> str:
    if not entry:
        return "No reason provided."
    reason = entry.get("reason")
    return str(reason or "No reason provided.")


def start_local_rpc_worker():
    global local_rpc_thread
    if not RPC_CLIENT_ID:
        return
    if local_rpc_thread is not None and local_rpc_thread.is_alive():
        return
    local_rpc_thread = None

    def worker():
        global local_rpc, local_rpc_thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = None
        start_timestamp = time.time()

        try:
            client = Presence(RPC_CLIENT_ID, loop=loop)
            client.connect()
            local_rpc = client

            while not local_rpc_stop_event.is_set():
                try:
                    activity_text = local_rpc_queue.get(timeout=1)
                except queue.Empty:
                    continue

                if activity_text is None:
                    break

                try:
                    client.update(activity_type=ActivityType.WATCHING, 
                                  name=f"{bot.user}",
                                  state=activity_text, 
                                  details=f"Running {bot.user.name} bot",
                                  start=start_timestamp,
                                  buttons=[{"label": "Git", "url": "https://github.com/ImNinnn/NinnnUtils"},{"label": "Support Server", "url": "https://discord.gg/FSBPvc9zqY"}]
                    )
                except Exception as e:
                    print(f"Local RPC sync failed: {e}")
                    break
        except Exception as e:
            print(f"Local RPC sync failed: {e}")
        finally:
            try:
                if client is not None:
                    client.close()
            except Exception:
                pass
            local_rpc = None
            local_rpc_thread = None
            loop.close()

    local_rpc_stop_event.clear()
    local_rpc_thread = threading.Thread(target=worker, name="LocalRPC", daemon=True)
    local_rpc_thread.start()


def sync_local_rpc(activity_text: str):
    if not RPC_CLIENT_ID:
        return

    start_local_rpc_worker()

    try:
        while not local_rpc_queue.empty():
            local_rpc_queue.get_nowait()
    except queue.Empty:
        pass

    try:
        local_rpc_queue.put_nowait(activity_text)
    except queue.Full:
        pass


def close_local_rpc():
    global local_rpc_thread

    local_rpc_stop_event.set()
    try:
        while not local_rpc_queue.empty():
            local_rpc_queue.get_nowait()
    except queue.Empty:
        pass

    try:
        local_rpc_queue.put_nowait(None)
    except queue.Full:
        pass

    if local_rpc_thread is not None:
        local_rpc_thread.join(timeout=5)
        local_rpc_thread = None


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


def automod_text_matches(content: str, phrase: str, use_regex: bool = False) -> bool:
    if not content or not phrase:
        return False
    if use_regex:
        try:
            return re.search(phrase, content, re.IGNORECASE) is not None
        except re.error:
            return False
    return phrase.lower() in content.lower()


async def sync_guild_word_block_rule(guild_id: str) -> None:
    guild = bot.get_guild(int(guild_id)) if guild_id.isdigit() else None
    if guild is None:
        return

    automod, data = get_guild_automod_config(guild_id)
    blocked_words = automod.get("blocked_words", [])
    keyword_filter = [entry.get("phrase", "").strip() for entry in blocked_words if not entry.get("use_regex", False) and entry.get("phrase", "").strip()]
    regex_patterns = [entry.get("phrase", "").strip() for entry in blocked_words if entry.get("use_regex", False) and entry.get("phrase", "").strip()]

    try:
        existing_rules = await guild.fetch_automod_rules()
        existing_rule = next((rule for rule in existing_rules if rule.name == "Word Block"), None)

        if not keyword_filter and not regex_patterns:
            if existing_rule is not None:
                await existing_rule.delete(reason="No blocked words configured")
                automod.pop("blocked_rule_id", None)
                save_guild_data(data)
            return

        trigger = AutoModTrigger(
            type=AutoModRuleTriggerType.keyword,
            keyword_filter=keyword_filter or None,
            regex_patterns=regex_patterns or None,
        )
        action = AutoModRuleAction(
            type=AutoModRuleActionType.block_message,
            custom_message="Blocked word or phrase detected.",
        )

        if existing_rule is not None:
            await existing_rule.edit(
                name="Word Block",
                event_type=AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=[action],
                enabled=True,
                reason="Updated blocked word settings",
            )
            automod["blocked_rule_id"] = existing_rule.id
            save_guild_data(data)
        else:
            new_rule = await guild.create_automod_rule(
                name="Word Block",
                event_type=AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=[action],
                enabled=True,
                reason="Configured blocked word settings",
            )
            automod["blocked_rule_id"] = new_rule.id
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

    guild_config, _ = get_guild_config(str(guild.id))
    configured_channel_id = guild_config.get("honeypot_channel_id")
    if not configured_channel_id or int(configured_channel_id) != channel.id:
        return False

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

    for log_id in get_guild_admin_log_channel_ids(guild):
        log_channel = guild.get_channel(log_id)
        if log_channel is None:
            continue
        try:
            await log_channel.send(
                f"**[HONEYPOT]** `{member.display_name}`: {content_preview}\n-# <:honey:1524116282075512842> **Honeypot triggered** | Action: {action.title()}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    try:
        if action == "timeout":
            timed_out_until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            await member.edit(timed_out_until=timed_out_until, reason="Sent a message in the honeypot channel")
        elif action == "kick":
            await member.kick(reason="Sent a message in the honeypot channel")
        elif action == "ban":
            await member.ban(reason="Sent a message in the honeypot channel")
    except (discord.Forbidden, discord.HTTPException):
        return False

    return True


@bot.event
async def on_automod_action(action: discord.AutoModAction) -> None:
    guild = action.guild
    if guild is None:
        return

    automod, data = get_guild_automod_config(str(guild.id))
    blocked_rule_id = automod.get("blocked_rule_id")

    if blocked_rule_id is None or action.rule_id != blocked_rule_id:
        resolved_id = None
        try:
            rule = await action.fetch_rule()
            if rule.name == "Word Block":
                resolved_id = action.rule_id
        except Exception:
            try:
                rules = await guild.fetch_automod_rules()
                matching = next((r for r in rules if r.id == action.rule_id and r.name == "Word Block"), None)
                if matching is not None:
                    resolved_id = action.rule_id
            except Exception:
                resolved_id = None

        if resolved_id is None:

            blocked_rule_id = None
        else:
            blocked_rule_id = resolved_id
            automod["blocked_rule_id"] = resolved_id
            save_guild_data(data)

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
        if automod_text_matches(text, phrase, bool(entry.get("use_regex", False))):
            should_warn = True
            break

    if not should_warn:
        return

    member_id = action.user_id
    warnings, _ = await add_guild_warning(str(guild.id), member_id, f"Discord AutoMod blocked a message via rule {action.rule_id}", moderator_id=None, moderator_name="Discord AutoMod")

    member = action.member or guild.get_member(member_id)
    if member is None:
        try:
            member = await guild.fetch_member(member_id)
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            member = None

    if member is not None and not member.bot:
        sanction_text = await apply_warning_sanctions(member, guild, len(warnings))
        await send_warning_dm(
            member,
            guild,
            f"Discord AutoMod blocked a message via rule {action.rule_id}",
            total_warnings=len(warnings),
            automod_triggered=True,
            sanction=sanction_text
        )

    if member is None:
        return


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


async def safe_edit_message(message: discord.Message, view: discord.ui.View):
    try:
        await message.edit(view=view)
    except (discord.NotFound, discord.HTTPException):
        pass


async def safe_send(interaction: discord.Interaction, content: str, **kwargs):
    try:
        await interaction.response.send_message(content, **kwargs)
    except discord.errors.InteractionResponded:
        try:
            await interaction.followup.send(content, **kwargs)
        except (discord.NotFound, discord.HTTPException):
            pass
    except (discord.NotFound, discord.HTTPException):
        pass


def get_guild_admin_log_channel_ids(guild: discord.Guild) -> list[int]:
    """Get valid admin log channel IDs for this guild"""
    return _get_guild_channel_ids(guild, admin_log_channels)

def get_guild_locked_channel_ids(guild: discord.Guild) -> list[int]:
    """Get valid locked channel IDs for this guild"""
    return _get_guild_channel_ids(guild, locked_channels)

def _get_guild_channel_ids(guild: discord.Guild, channel_dict: dict) -> list[int]:
    """Generic helper to get valid channel IDs from a dictionary"""
    return [cid for cid in channel_dict if guild.get_channel(cid) is not None]

def get_admin_log_channel_mentions(guild: discord.Guild) -> list[str]:
    """Get mentions for admin log channels"""
    return _get_channel_mentions(guild, admin_log_channels)

def get_locked_channel_mentions(guild: discord.Guild) -> list[str]:
    """Get mentions for locked channels"""
    return _get_channel_mentions(guild, locked_channels)

def _get_channel_mentions(guild: discord.Guild, channel_dict: dict) -> list[str]:
    """Generic helper to get channel mentions from a dictionary"""
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


locked_channels, admin_log_channels = load_lock_config()


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


def clean_cache():
    global message_cache, deleted_cache, edited_cache, bot_error_cache
    now = datetime.now(timezone.utc)
    message_cache = [m for m in message_cache if now - m['time'] < timedelta(minutes=120)]
    deleted_cache = [m for m in deleted_cache if now - m['time'] < timedelta(minutes=120)]
    edited_cache = [m for m in edited_cache if now - m['time'] < timedelta(minutes=120)]
    bot_error_cache = [m for m in bot_error_cache if now - m['time'] < timedelta(minutes=120)]


def discord_timestamp(dt: datetime, style: str = "f") -> str:
    if isinstance(dt, datetime):
        return f"<t:{int(dt.timestamp())}:{style}>"
    return str(dt)


def trim_cache(cache: list, max_len: int = 10) -> list:
    return cache[-max_len:]


def add_bot_error(guild_id: int | None, channel_id: int | None, user, command_name: str, error: Exception, interaction: discord.Interaction = None):
    """Unified error logging. If interaction is provided, extracts guild/channel/user/command from it."""
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

    bot_error_cache.append({
        "guild_id": guild_id,
        "channel_id": channel_id,
        "user": user,
        "command_name": command_name,
        "error_type": type(error).__name__,
        "error_message": str(error) or "No error message provided",
        "time": datetime.now(timezone.utc),
    })

    if len(bot_error_cache) > 10:
        bot_error_cache = bot_error_cache[-10:]


def add_bot_error_entry(guild_id: int | None, channel_id: int | None, user, source: str, error: Exception):
    """Backwards compatibility wrapper for add_bot_error"""
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

    embed = discord.Embed(
        description=f"{message.content}" if message.content else None,
        color=discord.Color.gold(),
    )
    embed.set_author(name=f"| {message.author.display_name}", icon_url=message.author.display_avatar.url)
    if message.attachments:
        attachment = message.attachments[0]
        if attachment.content_type and attachment.content_type.startswith("image/"):
            embed.set_image(url=attachment.url)
    embed.timestamp = message.created_at

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




class ShopView(discord.ui.LayoutView):
    def __init__(self, shop_items, guild_id, user_id):
        super().__init__(timeout=180)
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
        close_button = Button(label="Close", style=discord.ButtonStyle.danger, custom_id="shop_close")

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

        async def close_callback(interaction: discord.Interaction):
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)

        prev_button.callback = prev_callback
        next_button.callback = next_callback
        close_button.callback = close_callback
        self.add_item(discord.ui.ActionRow(prev_button, next_button, close_button))


class DeletedMessagesView(LayoutView):
    def __init__(self, full_description: str, media_messages: list, requester):
        super().__init__(timeout=60)
        self.full_description = full_description
        self.messages = media_messages
        self.requester = requester
        self.index = 0
        self.revealed = False
        self.build_components()

    def build_components(self):
        self.clear_items()

        body = self.full_description
        gallery = None

        if self.messages:
            current_msg = self.messages[self.index]
            content_text = current_msg.get('content') or "*[Media only]*"
            media_text = current_msg['media'] if self.revealed else "Media hidden. Press Reveal Media to view."
            body += (
                f"\n\n---\n\n"
                f"**Current media preview ({self.index + 1}/{len(self.messages)})**\n"
                f"**{current_msg['author'].display_name}**: {content_text}\n"
                f"-# Sent at {current_msg['created_at']}\n"
                f"-# {media_text}"
            )

            if self.revealed:
                gallery = MediaGallery()
                gallery.add_item(media=current_msg['media'], description=f"{current_msg['author'].display_name} - deleted at {discord_timestamp(current_msg['created_at'])}")

        container_items = [
            TextDisplay("<:trash:1517497581058527404> Recent deleted messages"),
            Separator(),
            TextDisplay(body),
        ]
        if gallery is not None:
            container_items.extend([Separator(), gallery])

        container = Container(
            *container_items,
            accent_color=discord.Color.red(),
        )
        self.add_item(container)

        if self.messages:
            self.reveal_button = Button(label="Reveal Media", style=discord.ButtonStyle.danger, custom_id="deleted_media_reveal")
            self.prev_button = Button(label="Previous media", style=discord.ButtonStyle.primary, custom_id="deleted_media_prev")
            self.next_button = Button(label="Next media", style=discord.ButtonStyle.primary, custom_id="deleted_media_next")

            async def reveal_callback(interaction: discord.Interaction):
                if interaction.user != self.requester:
                    await interaction.response.send_message("<:disapprove:1517452151012589662> Only the person who ran the command can reveal media!", ephemeral=True)
                    return
                self.revealed = not self.revealed
                self.build_components()
                await interaction.response.edit_message(view=self)

            async def prev_callback(interaction: discord.Interaction):
                if interaction.user != self.requester:
                    await interaction.response.send_message("<:disapprove:1517452151012589662> Only the person who ran the command can flip pages!", ephemeral=True)
                    return
                if self.index > 0:
                    self.index -= 1
                    self.build_components()
                    await interaction.response.edit_message(view=self)

            async def next_callback(interaction: discord.Interaction):
                if interaction.user != self.requester:
                    await interaction.response.send_message("<:disapprove:1517452151012589662> Only the person who ran the command can flip pages!", ephemeral=True)
                    return
                if self.index < len(self.messages) - 1:
                    self.index += 1
                    self.build_components()
                    await interaction.response.edit_message(view=self)

            self.reveal_button.callback = reveal_callback
            self.prev_button.callback = prev_callback
            self.next_button.callback = next_callback
            self.update_button_states()
            self.add_item(discord.ui.ActionRow(self.prev_button, self.reveal_button, self.next_button))

    def update_button_states(self):
        self.prev_button.disabled = (self.index == 0)
        self.next_button.disabled = (self.index == len(self.messages) - 1)
        if self.revealed:
            self.reveal_button.label = "Hide Media"
            self.reveal_button.style = discord.ButtonStyle.secondary
        else:
            self.reveal_button.label = f"Reveal Media ({self.index + 1}/{len(self.messages)})"
            self.reveal_button.style = discord.ButtonStyle.danger

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if hasattr(self, 'message'):
                await self.message.edit(view=self)
        except Exception:
            pass


class V2InfoContainerView(LayoutView):
    def __init__(self, title: str, description: str, accent_color: discord.Color):
        super().__init__(timeout=180)
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
                    await voice_client.disconnect()
                    print(f"Left empty voice channel in {member.guild.name} after 30 seconds.")


@bot.event
async def on_ready():
    shard_info = (
        f"{len(bot.shards)} shard(s), IDs {list(bot.shards.keys())}"
        if bot.shards
        else "single process (no sharding)"
    )
    print(f"Logged in as {bot.user} (ID: {bot.user.id}) - {shard_info}")
    print(f"Serving {len(bot.guilds)} guild(s)")
    if not update_presence.is_running():
        update_presence.start()
    if not voice_xp_tracker.is_running():
        voice_xp_tracker.start()
    if not giveaway_loop.is_running():
        giveaway_loop.start()
    if not giveaway_refresh_loop.is_running():
        giveaway_refresh_loop.start()
    if not reminder_loop.is_running():
        reminder_loop.start()
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
        if await apply_honeypot_sanction(message.author, message.guild, message.channel, message.content):
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

    if message.guild and message.channel.id in locked_channels:
        guild_id = message.guild.id

        for log_id in admin_log_channels:
            log_channel = bot.get_channel(log_id)
            if log_channel and log_channel.guild.id == guild_id:
                try:
                    await log_channel.send(f"**[LOCKED]** `{message.author}`: {message.content}")
                except discord.Forbidden as error:
                    add_bot_error_entry(guild_id, log_id, message.author, "locked channel admin log", error)
                except Exception:
                    pass

        current_pauses = server_pauses.get(guild_id, set())
        if guild_id in all_paused_guilds or message.channel.id in current_pauses:
            return

        dots = "•" * min(max(len(message.content), 1), 200)
        try:
            await message.delete()
            await message.channel.send(f"<:locked:1517574877257924809> {dots}")
        except discord.Forbidden as error:
            add_bot_error_entry(guild_id, message.channel.id, message.author, "locked channel notice", error)
        except Exception:
            pass
        return

    global message_cache
    clean_cache()

    media_url = message.attachments[0].url if message.attachments else None
    now = datetime.now(timezone.utc)
    message_cache.append({
        'id': message.id,
        'channel': message.channel.id,
        'author': message.author,
        'content': message.content,
        'media': media_url,
        'mentions': message.mentions,
        'time': now,
        'created_at': now
    })

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
                deleted_cache = trim_cache(deleted_cache, max_len=10)
            if message.guild and not ghost_enabled:
                break

            if msg['mentions'] and not msg['author'].bot:
                pinged_users = [user for user in msg['mentions'] if user.id != msg['author'].id]
                
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
                edited_cache = trim_cache(edited_cache, max_len=10)
            
            msg['content'] = after.content
            break


@bot.event
async def on_member_join(member):
    guild_config, _ = get_guild_config(str(member.guild.id))
    channel_id = guild_config.get("welcome_channel_id")
    if channel_id:
        channel = member.guild.get_channel(channel_id)
        if channel:
            try:
                welcome_file = await create_welcome_card(member)
                await channel.send(f"Welcome {format_user_reference(member)}!", file=welcome_file)
            except discord.Forbidden as error:
                add_bot_error_entry(member.guild.id, channel.id, member, "welcome banner", error)
            except Exception as e:
                print(f"Error creating welcome card: {e}")


@bot.event
async def on_member_remove(member):
    guild_config, _ = get_guild_config(str(member.guild.id))
    channel_id = guild_config.get("goodbye_channel_id")
    if channel_id:
        channel = member.guild.get_channel(channel_id)
        if channel:
            try:
                goodbye_file = await create_goodbye_card(member)
                await channel.send(f"Goodbye {member.display_name}. We'll miss you!", file=goodbye_file)
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

    embed = discord.Embed(
        description=f"{message.content}" if message.content else None,
        color=discord.Color.gold(),
    )
    embed.set_author(name=f"{message.author.display_name}", icon_url=message.author.display_avatar.url)
    if message.attachments:
        attachment = message.attachments[0]
        if attachment.content_type and attachment.content_type.startswith("image/"):
            embed.set_image(url=attachment.url)
    embed.timestamp = datetime.now(timezone.utc)

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
            embed = discord.Embed(description=f"{message.content}" if message.content else None, color=discord.Color.gold())
            embed.set_author(name=f"{message.author.display_name}", icon_url=message.author.display_avatar.url)
            if message.attachments and message.attachments[0].content_type.startswith("image/"):
                embed.set_image(url=message.attachments[0].url)
            embed.timestamp = datetime.now(timezone.utc)
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
            await interaction.response.send_message(message_text, ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions):
        perms = ", ".join(error.missing_permissions)
        await interaction.response.send_message(f"<:disapprove:1517452151012589662> You lack the required permissions to run this: `{perms}`", ephemeral=True)
    elif bot_missing_permissions_error is not None and isinstance(error, bot_missing_permissions_error):
        perms = ", ".join(error.missing_permissions)
        message_text = f"<:disapprove:1517452151012589662> I am missing the required permissions to run this: `{perms}`"
        if interaction.response.is_done():
            await interaction.followup.send(message_text, ephemeral=True)
        else:
            await interaction.response.send_message(message_text, ephemeral=True)
    elif isinstance(original_error, discord.Forbidden):
        message_text = "<:disapprove:1517452151012589662> I am missing the permissions required to complete that action."
        if interaction.response.is_done():
            await interaction.followup.send(message_text, ephemeral=True)
        else:
            await interaction.response.send_message(message_text, ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> An unexpected error occurred while executing this command.", ephemeral=True)




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


    online_users = sum(
        len([m for m in guild.members if m.status != discord.Status.offline and not m.bot])
        for guild in bot.guilds
    )

    if presence_index == 0:
        activity_text = f"ver{VERSION} ┃ {online_users} online users"
    elif presence_index == 1:
        activity_text = f"ver{VERSION} ┃ {ACTIVITY_TEXT}"
    else:
        activity_text = f"ver{VERSION} ┃ alt{VERSION_ALTERNATE}"

    activity = discord.Activity(type=discord.ActivityType.watching, name=activity_text)

    for shard_id, shard in bot.shards.items():
        await bot.change_presence(
            activity=activity,
            status=discord.Status.online,
            shard_id=shard_id,
        )

    sync_local_rpc(activity_text)

    presence_index = (presence_index + 1) % 3


@update_presence.before_loop
async def before_update_presence():
    await bot.wait_until_ready()
    sync_local_rpc("App just started... .. .")
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
        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message(
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
    await interaction.response.defer(ephemeral=False)
    try:
        translator = GoogleTranslator(source=from_language, target=to_language)
        translated_text = translator.translate(text)
        await interaction.followup.send(content=translated_text)
    except Exception as e:
        await interaction.followup.send(f"<:disapprove:1517452151012589662> Translation failed. Please ensure you used valid ISO language codes! Error: {e}", ephemeral=True)


@bot.tree.command(name="gif", description="Convert an image attachment into a GIF file")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(image="The image to convert to GIF")
async def gif(interaction: discord.Interaction, image: discord.Attachment):
    await interaction.response.defer()

    if not image:
        await interaction.followup.send("<:disapprove:1517452151012589662> Please attach an image to convert.", ephemeral=True)
        return

    try:
        image_bytes = await image.read()
        with Image.open(io.BytesIO(image_bytes)) as img:
            if getattr(img, "is_animated", False):
                frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(img)]
                buffer = io.BytesIO()
                frames[0].save(
                    buffer,
                    format="GIF",
                    save_all=True,
                    append_images=frames[1:],
                    loop=0,
                    duration=img.info.get("duration", 100),
                    disposal=2,
                )
            else:
                converted = img.convert("RGBA")
                buffer = io.BytesIO()
                converted.save(buffer, format="GIF", optimize=True)

            buffer.seek(0)
            await interaction.followup.send(file=discord.File(buffer, filename="converted.gif"))

    except Exception as e:
        await interaction.followup.send(
            f"<:disapprove:1517452151012589662> Failed to convert the image to GIF. Please make sure the file is a valid image. Error: {e}",
            ephemeral=True
        )


@bot.tree.command(name="song", description="Manage song playback and queue")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.describe(
    action="What you want to do with the song queue",
    youtube_url="The YouTube video link (required for add)",
    position="Queue position to remove (required for remove)"
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Skip", value="skip"),
        app_commands.Choice(name="Remove", value="remove"),
    ]
)
async def song(
    interaction: discord.Interaction,
    action: str,
    youtube_url: str = None,
    position: int = None,
):
    guild_id = str(interaction.guild.id)
    queue = get_song_queue(guild_id)

    if action == "add":
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("<:disapprove:1517452151012589662> You must be in a voice channel to add a song!", ephemeral=True)
            return
        if not youtube_url:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Please provide a YouTube link to add.", ephemeral=True)
            return

        await interaction.response.defer()
        voice_channel = interaction.user.voice.channel
        was_empty = len(queue['tracks']) == 0 or queue['current_index'] >= len(queue['tracks'])

        try:
            with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                video_title = info.get('title', 'Unknown Title')

            voice_client = interaction.guild.voice_client
            if voice_client is None:
                voice_client = await voice_channel.connect()
            elif voice_client.channel != voice_channel:
                await voice_client.move_to(voice_channel)

            queue['tracks'].append({
                'url': youtube_url,
                'title': video_title,
                'requested_by': interaction.user.display_name
            })

            if was_empty and not voice_client.is_playing() and not voice_client.is_paused():
                queue['current_index'] = len(queue['tracks']) - 1
                queue['now_playing_channel_id'] = interaction.channel.id
                if await play_guild_song(guild_id, voice_client):
                    await interaction.followup.send(f"<:music:1517575582764765224> Now playing: **{video_title}** in {voice_channel.mention}!")
                    return
                await interaction.followup.send(f"<:disapprove:1517452151012589662> Failed to start playback for **{video_title}**.")
                return

            await interaction.followup.send(f"<:music:1517575582764765224> Added to queue: **{video_title}** (Position {len(queue['tracks'])})")

        except Exception as e:
            await interaction.followup.send(f"<:disapprove:1517452151012589662> Failed to add song. Error: {e}")
        return

    if action == "skip":
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("<:disapprove:1517452151012589662> I'm not connected to a voice channel.", ephemeral=True)
            return
        if not queue['tracks']:
            await interaction.response.send_message("<:disapprove:1517452151012589662> The queue is empty.", ephemeral=True)
            return

        if queue['current_index'] >= len(queue['tracks']):
            queue['current_index'] = len(queue['tracks']) - 1

        if queue['current_index'] + 1 < len(queue['tracks']):
            queue['current_index'] += 1
            queue['stop_action'] = 'manual'
            voice_client.stop()
            await interaction.response.send_message(f"<:next:1518977801057865224> Skipped to **{queue['tracks'][queue['current_index']]['title']}**.")
            await play_guild_song(guild_id, voice_client)
            return

        queue['current_index'] = len(queue['tracks'])
        queue['stop_action'] = 'manual'
        voice_client.stop()
        await cleanup_now_playing_embed(guild_id)
        await interaction.response.send_message("<:disapprove:1517452151012589662> No more songs in the queue. Playback stopped.")
        return

    if action == "remove":
        if position is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Please provide the queue position to remove.", ephemeral=True)
            return
        if not queue['tracks']:
            await interaction.response.send_message("<:disapprove:1517452151012589662> The queue is empty.", ephemeral=True)
            return
        if position < 1 or position > len(queue['tracks']):
            await interaction.response.send_message("<:disapprove:1517452151012589662> Invalid queue position.", ephemeral=True)
            return

        song_index = position - 1
        removed = queue['tracks'].pop(song_index)
        if song_index < queue['current_index']:
            queue['current_index'] -= 1
        elif song_index == queue['current_index']:
            voice_client = interaction.guild.voice_client
            if voice_client and voice_client.is_connected() and (voice_client.is_playing() or voice_client.is_paused()):
                queue['stop_action'] = 'manual'
                voice_client.stop()
                if queue['current_index'] >= len(queue['tracks']):
                    await cleanup_now_playing_embed(guild_id)
                    await interaction.response.send_message(f"Removed **{removed['title']}** and stopped playback because the queue is now empty.")
                    return
                await interaction.response.send_message(f"Removed **{removed['title']}**. Now playing **{queue['tracks'][queue['current_index']]['title']}**.")
                await play_guild_song(guild_id, voice_client)
                return

        await interaction.response.send_message(f"Removed **{removed['title']}** from the queue.")
        return

    await interaction.response.send_message("<:disapprove:1517452151012589662> Invalid song action.", ephemeral=True)


@bot.tree.command(name="voice-leave", description="Disconnect the bot from the voice channel")
@app_commands.allowed_installs(guilds=True, users=False)
async def voice_leave(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client:
        guild_id = str(interaction.guild.id)
        queue = get_song_queue(guild_id)
        queue['tracks'].clear()
        queue['current_index'] = 0
        queue['loop'] = False
        queue['stop_action'] = None
        await cleanup_now_playing_embed(guild_id)
        await voice_client.disconnect()
        await interaction.response.send_message("<:wave:1517576345603936296> Disconnected from the voice channel and cleared the queue.")
    else:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I'm not connected to a voice channel!", ephemeral=True)


@bot.tree.command(name="afk", description="Set yourself as AFK with a reason")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@app_commands.describe(reason="Why you're going AFK")
async def afk_command(interaction: discord.Interaction, reason: str = None):
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    member = interaction.user
    if not isinstance(member, discord.Member):
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    reason_text = (reason or "No reason provided.").strip() or "No reason provided."
    already_afk = await set_afk_status(member, reason_text)
    if already_afk:
        await interaction.response.send_message(f"<:afk:1525440143245180970> {member.mention} is now AFK. Reason: {reason_text}")
    else:
        current_reason = get_afk_reason(afk_status.get(get_afk_status_key(member.guild.id, member.id)))
        await interaction.response.send_message(f"<:warning:1517452174991556758> You are already AFK. Reason: {current_reason}", ephemeral=True)


@bot.tree.command(name="roll", description="Roll a 6-sided die")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def roll(interaction: discord.Interaction):
    result = random.randint(1, 6)
    await interaction.response.send_message(f"🎲 You rolled a **{result}**!")


@bot.tree.command(name="random", description="Pick a random number between two values")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(min_value="The lowest number", max_value="The highest number")
async def random_cmd(interaction: discord.Interaction, min_value: int, max_value: int):
    low, high = min(min_value, max_value), max(min_value, max_value)
    result = random.randint(low, high)
    await interaction.response.send_message(f"<:list:1517497572770451567> Your random number between **{low}** and **{high}** is: **{result}**")


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
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="channelinfo", description="Show configured channels from the bot's JSON settings for this server")
@app_commands.allowed_installs(guilds=True, users=False)
async def channelinfo(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("<:disapprove:1517452151012589662> This command must be used in a server.", ephemeral=True)
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

    locked_channels_list = []
    if isinstance(locked, dict):
        for ch_key in locked.keys():
            try:
                ch = guild.get_channel(int(ch_key))
                if ch:
                    locked_channels_list.append(ch.mention)
            except Exception:
                continue
    locked_channels = "\n".join(locked_channels_list) if locked_channels_list else "None"

    honeypot_channel = fmt_channel(guild_config.get("honeypot_channel_id"))

    embed = discord.Embed(title=f"<:drawer:1517497564189036574> Configured Channels for {guild.name}", color=discord.Color.blurple())
    embed.add_field(name="<:plus:1518348756570079262> Welcome Channel", value=welcome, inline=False)
    embed.add_field(name="<:minus:1518348754111959150> Goodbye Channel", value=goodbye, inline=False)
    embed.add_field(name="<:chalice:1517579767573123092> Level-up Announce Channel", value=lvl_channel, inline=False)
    embed.add_field(name="<:graph:1517584522877866065> Board Channels", value=board_channels, inline=False)
    embed.add_field(name="<:list:1517497572770451567> Counter Channels", value=counter_channels, inline=False)
    embed.add_field(name="<:unlocked:1517574880034558102> Admin Log Channel", value=admin_log_channel, inline=False)
    embed.add_field(name="<:locked:1517574877257924809> Locked Channels", value=locked_channels, inline=False)
    embed.add_field(name="<:honey:1524116282075512842> Honeypot Channel", value=honeypot_channel, inline=False)
    embed.set_footer(text=f"Run /settings and go to channel settings to change these settings.")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="say", description="Make the bot say something")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)

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

        await interaction.response.send_message(embed=embed)


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
    await interaction.response.send_message(f"> This message has **{percentage}%** Rizz.\n-# **{message.author.display_name}:** {original_text}")


@bot.tree.context_menu(name="Cringe Meter")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def cringe_menu(interaction: discord.Interaction, message: discord.Message):
    percentage = random.randint(0, 100)
    original_text = message.content if message.content else "*[Media or Embed]*"
    await interaction.response.send_message(f"> This message is **{percentage}%** Cringe.\n-# **{message.author.display_name}:** {original_text}")


@bot.tree.context_menu(name="Stupid Meter")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def stupid_menu(interaction: discord.Interaction, message: discord.Message):
    percentage = random.randint(0, 100)
    original_text = message.content if message.content else "*[Media or Embed]*"
    await interaction.response.send_message(f"> This message is **{percentage}%** Stupid.\n-# **{message.author.display_name}:** {original_text}")


@bot.tree.context_menu(name="Lie Meter")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def lie_menu(interaction: discord.Interaction, message: discord.Message):
    percentage = random.randint(0, 100)
    original_text = message.content if message.content else "*[Media or Embed]*"
    await interaction.response.send_message(f"> This message is **{percentage}%** a Lie.\n-# **{message.author.display_name}:** {original_text}")


@bot.tree.context_menu(name="Quote")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def quote_menu(interaction: discord.Interaction, message: discord.Message):
    quote_file = await create_quote_card(message)
    if quote_file is None:
        await interaction.response.send_message("Unable to create quote image right now.", ephemeral=True)
        return
    await interaction.response.send_message(file=quote_file)


@bot.tree.command(name="love", description="Check the compatibility between two things or users")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(item1="The first person or thing", item2="The second person or thing")
async def love(interaction: discord.Interaction, item1: str, item2: str):
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
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rate-cool", description="Rate how cool someone is")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(username="The person or thing to rate")
async def rate_cool(interaction: discord.Interaction, username: str):
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
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rate-gay", description="Rate how gay someone is")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(username="The person or thing to rate")
async def rate_gay(interaction: discord.Interaction, username: str):
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
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="stats", description="Show bot statistics and status")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def stats(interaction: discord.Interaction):
    load_dotenv(override=True)
    VERSION = os.getenv('BOT_VERSION')
    VERSION_ALTERNATE = os.getenv('BOT_VERSION_ALTERNATE')
    ACTIVITY_TEXT = os.getenv('ACTIVITY')
    total_guilds = len(bot.guilds)
    embed = discord.Embed(
        title="<:gear:1517576939097952496> Bot Statistics",
        color=discord.Color.gold(),
        description="Current status and technical details of the bot."
    )
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else bot.user.default_avatar.url)
    embed.add_field(name="<:internet:1518376144246804672> Servers", value=str(total_guilds), inline=True)
    embed.add_field(name="<:graph:1517584522877866065> Total Users", value=str(len(bot.users)), inline=True)
    embed.add_field(name="<:hourglass:1517574046252924938> Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.add_field(name="<:python:1518376147413635154> Library", value=f"discord.py {discord.__version__}", inline=True)
    embed.add_field(name="<:gear:1517576939097952496> Version", value=f"ver{VERSION} | alt{VERSION_ALTERNATE} | {ACTIVITY_TEXT}", inline=True)
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
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="slot-classic", description="Spin the slot machine!")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def slot(interaction: discord.Interaction):
    emojis = ['🍒', '🍎', '🍇', '💎', '<:bell:1517497562184024275>', '🍋']
    await interaction.response.send_message("🎰 **Spinning...**")
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
    await interaction.response.send_message(f"<:coin:1518351100783231138> The coin landed on: **{result}**!")


@bot.tree.command(name="avatar", description="Get the profile picture of a user")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@app_commands.describe(user="The user to get the avatar from")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user.name}'s Avatar", color=discord.Color.blue())
    embed.set_image(url=user.display_avatar.url)
    embed.set_footer(text="I wont be able to show the avatar if it is animated")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="banner", description="Get the profile banner of a user")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@app_commands.describe(user="The user to get the banner from")
async def banner(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    full_user = await bot.fetch_user(user.id)
    if full_user.banner:
        embed = discord.Embed(title=f"{user.name}'s Banner", color=discord.Color.blue())
        embed.set_image(url=full_user.banner.url)
        embed.set_footer(text="I wont be able to show the banner if it is animated")
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"{user.name} does not have a banner.", ephemeral=True)


@bot.tree.command(name="emoji", description="Get the image for a custom emoji")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(emoji="The custom emoji to get the image from")
async def emoji(interaction: discord.Interaction, emoji: str):
    if not emoji:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> Please provide a valid custom emoji.", ephemeral=True)
    try:
        emoji_obj = discord.PartialEmoji.from_str(emoji)
    except Exception:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> Please provide a valid custom emoji.", ephemeral=True)
    if not emoji_obj.id:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> Please provide a valid custom emoji.", ephemeral=True)
    embed = discord.Embed(title=f"Emoji: {emoji_obj.name}", color=discord.Color.blue())
    embed.set_image(url=emoji_obj.url)
    await interaction.response.send_message(embed=embed)




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
        await interaction.response.send_message("<:disapprove:1517452151012589662> You must be connected to a voice channel to use this command.", ephemeral=True)
        return

    source_channel = member.voice.channel
    if source_channel.id == channel.id:
        await interaction.response.send_message("<:approve:1517452125687513158> You are already in the target voice channel.", ephemeral=True)
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

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rename_adm", description="Rename a user or reset their nickname")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_nicknames=True)
@app_commands.describe(
    user="The member you want to rename",
    name="The new nickname (leave empty to reset to original name)"
)
async def rename(interaction: discord.Interaction, user: discord.Member, name: str = None):
    if interaction.guild.me.top_role <= user.top_role:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I cannot rename this user. Their role is higher than or equal to mine!", ephemeral=True)
        return
    try:
        old_name = user.display_name
        await user.edit(nick=name)
        if name:
            await interaction.response.send_message(f"<:approve:1517452125687513158> Changed **{old_name}**'s nickname to **{name}**.")
        else:
            await interaction.response.send_message(f"<:approve:1517452125687513158> Reset **{old_name}**'s nickname to their original username.")
    except discord.Forbidden:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I don't have the 'Manage Nicknames' permission or the user is the Server Owner.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)


@bot.tree.command(name="purge-nuke_adm", description="Fully clear a channel")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_channels=True)
async def nuke(interaction: discord.Interaction, archive: bool = False):
    try:
        channel = await interaction.guild.fetch_channel(interaction.channel_id)
    except discord.Forbidden:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I cannot 'see' this channel. Please check my permissions in this specific channel's settings.", ephemeral=True)
        return

    GIF_URL = "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExN2x1ZW82ZGdlZzV1MTFzNGF6ajJzZ3Bmc3I2MDlxaXp0cWpkcTY4YyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/fXhYwggfsp3yHBsdlr/giphy.gif"

    await interaction.response.send_message("<:explosive:1517578642723573880> Target locked. Nuking...", ephemeral=False)
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
        await interaction.response.send_message("<:disapprove:1517452151012589662> Please specify a number greater than 0.", ephemeral=True)
        return
    if amount > 100:
        await interaction.response.send_message("<:warning:1517452174991556758> For safety, you can only purge up to 100 messages at a time.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    def is_user(m):
        return m.author == user if user else True

    try:
        deleted = await interaction.channel.purge(limit=amount, check=is_user, before=interaction.created_at)
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
        await interaction.response.send_message("<:disapprove:1517452151012589662> You must specify a duration greater than 0!", ephemeral=True)
        return
    if duration.total_seconds() > 2419200:
        await interaction.response.send_message("<:disapprove:1517452151012589662> Timeout cannot exceed 28 days.", ephemeral=True)
        return

    target_member = resolve_member_from_input(interaction.guild, member)
    if target_member is None:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I couldn't find that user in this server.", ephemeral=True)
        return

    if target_member == interaction.user:
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot timeout yourself.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and interaction.user != target_member and target_member.top_role >= interaction.user.top_role:
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot timeout someone with an equal or higher role than yours.", ephemeral=True)
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
        await interaction.response.send_message(embed=confirm_embed)
    except discord.Forbidden:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I don't have permission to timeout this user (Hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)


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
        await interaction.response.send_message("<:disapprove:1517452151012589662> I couldn't find that user in this server.", ephemeral=True)
        return

    if target_member == interaction.user:
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot kick yourself.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and interaction.user != target_member and target_member.top_role >= interaction.user.top_role:
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot kick someone with an equal or higher role than yours.", ephemeral=True)
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
        await interaction.response.send_message(embed=confirm_embed)
    except discord.Forbidden:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I don't have permission to kick this user (Hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)


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
        await interaction.response.send_message("<:disapprove:1517452151012589662> Delete days must be between 0 and 7.", ephemeral=True)
        return

    target_member = resolve_member_from_input(interaction.guild, member)
    if target_member is None:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I couldn't find that user in this server.", ephemeral=True)
        return

    if target_member == interaction.user:
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot ban yourself.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and interaction.user != target_member and target_member.top_role >= interaction.user.top_role:
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot ban someone with an equal or higher role than yours.", ephemeral=True)
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
        await interaction.response.send_message(embed=confirm_embed)
    except discord.Forbidden:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I don't have permission to ban this user (Hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)


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
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot warn yourself.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and member.top_role >= interaction.user.top_role:
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot manage warnings for someone with an equal or higher role than yours.", ephemeral=True)
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
        await interaction.response.send_message(embed=confirm_embed)
        return

    if action == "remove":
        if not user_warnings:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> **{format_user_reference(member)}** has no warnings to remove.", ephemeral=True)
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
        await interaction.response.send_message(embed=confirm_embed)
        return

    if action == "clear":
        if not user_warnings:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> **{format_user_reference(member)}** has no warnings to clear.", ephemeral=True)
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
        await interaction.response.send_message(embed=confirm_embed)
        return

    await interaction.response.send_message("<:disapprove:1517452151012589662> Invalid action. Choose add, remove, or clear.", ephemeral=True)


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
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot view warnings for yourself with this command.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and member.top_role >= interaction.user.top_role:
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot view warnings for someone with an equal or higher role than yours.", ephemeral=True)
        return

    user_warnings, _ = get_guild_warnings(str(interaction.guild.id), member.id)
    if not user_warnings:
        await interaction.response.send_message(f"<:approve:1517452125687513158> **{format_user_reference(member)}** has no warnings.", ephemeral=False)
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

    await interaction.response.send_message(embed=embed, ephemeral=False)


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
            await interaction.response.send_message("<:disapprove:1517452151012589462> Only the command user can navigate these pages.", ephemeral=True)
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
        await interaction.response.send_message(role_error, ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and interaction.user != member and member.top_role >= interaction.user.top_role:
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot modify the roles of someone with an equal or higher role than yours.", ephemeral=True)
        return

    try:
        if action == "add":
            if role in member.roles:
                await interaction.response.send_message(f"<:warning:1517452174991556758> **{format_user_reference(member)}** already has **{role.name}**.", ephemeral=True)
                return
            await member.add_roles(role, reason=f"Role admin by {interaction.user} - {reason}")
            await interaction.response.send_message(f"<:approve:1517452125687513158> Added **{role.name}** to **{format_user_reference(member)}**.", ephemeral=False)
        else:
            if role not in member.roles:
                await interaction.response.send_message(f"<:warning:1517452174991556758> **{format_user_reference(member)}** does not have **{role.name}**.", ephemeral=True)
                return
            await member.remove_roles(role, reason=f"Role admin by {interaction.user} - {reason}")
            await interaction.response.send_message(f"<:approve:1517452125687513158> Removed **{role.name}** from **{format_user_reference(member)}**.", ephemeral=False)
    except discord.Forbidden:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)


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
        await interaction.response.send_message(role_error, ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and interaction.user != member and member.top_role >= interaction.user.top_role:
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot modify the roles of someone with an equal or higher role than yours.", ephemeral=True)
        return

    if action == "grant":
        if not duration:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Please provide a duration like 30m, 2h, or 1d.", ephemeral=True)
            return

        duration_seconds = parse_duration_to_seconds(duration)
        if duration_seconds is None or duration_seconds <= 0:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Please provide a valid duration like 30m, 2h, or 1d.", ephemeral=True)
            return

        try:
            if role in member.roles:
                await interaction.response.send_message(f"<:warning:1517452174991556758> **{format_user_reference(member)}** already has **{role.name}**.", ephemeral=True)
                return
            await member.add_roles(role, reason=f"Temporary role admin by {interaction.user} - {reason}")
            async def remove_temp_role():
                await asyncio.sleep(duration_seconds)
                try:
                    await member.remove_roles(role, reason=f"Temporary role expired after {duration} (admin command)")
                except (discord.Forbidden, discord.HTTPException):
                    pass

            asyncio.create_task(remove_temp_role())
            await interaction.response.send_message(f"<:approve:1517452125687513158> Granted **{role.name}** to **{format_user_reference(member)}** for {duration}.", ephemeral=False)
        except discord.Forbidden:
            await interaction.response.send_message("<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)
        return

    try:
        if role not in member.roles:
            await interaction.response.send_message(f"<:warning:1517452174991556758> **{format_user_reference(member)}** does not have **{role.name}**.", ephemeral=True)
            return
        await member.remove_roles(role, reason=f"Temporary role admin removal by {interaction.user} - {reason}")
        await interaction.response.send_message(f"<:approve:1517452125687513158> Removed **{role.name}** from **{format_user_reference(member)}**.", ephemeral=False)
    except discord.Forbidden:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)


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
        await interaction.response.send_message(role_error, ephemeral=True)
        return

    if role is None or target_role is None:
        await interaction.response.send_message("<:disapprove:1517452151012589662> Both role options are required.", ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    try:
        await interaction.guild.chunk(cache=True)
    except Exception:
        pass

    affected_members = [member for member in interaction.guild.members if target_role in member.roles]
    if not affected_members:
        await interaction.followup.send(f"<:warning:1517452174991556758> No members with the role **{target_role.name}** were found.", ephemeral=False)
        return

    updated = 0
    skipped = 0
    failed = 0
    processed = 0
    stop_progress_updates = asyncio.Event()

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
            except Exception:
                failed += 1
            finally:
                processed += 1
    finally:
        stop_progress_updates.set()
        if progress_task:
            try:
                await progress_task
            except Exception:
                pass

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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Please provide the giveaway name to cancel.", ephemeral=True)
            return

        data = load_giveaway_data()
        matched = None
        for giveaway_id, giveaway in data.items():
            if str(giveaway.get('guild_id')) == str(interaction.guild_id) and giveaway.get('status') == 'active' and str(giveaway.get('name', '')).lower() == name.lower():
                matched = (giveaway_id, giveaway)
                break

        if not matched:
            await interaction.response.send_message("<:disapprove:1517452151012589662> I couldn't find an active giveaway with that name.", ephemeral=True)
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

        await interaction.response.send_message(f"<:approve:1517452125687513158> Cancelled giveaway **{name}**.")
        return

    if not name:
        await interaction.response.send_message("<:disapprove:1517452151012589662> Please provide a giveaway name.", ephemeral=True)
        return
    if winners <= 0:
        await interaction.response.send_message("<:disapprove:1517452151012589662> Winners must be at least 1.", ephemeral=True)
        return
    if temp_role and temp_role_time <= 0:
        await interaction.response.send_message("<:disapprove:1517452151012589662> Temporary role time must be greater than 0 when using a temp role.", ephemeral=True)
        return

    role_error = validate_role_selection(interaction, role, "role")
    if role_error:
        await interaction.response.send_message(role_error, ephemeral=True)
        return

    temp_role_error = validate_role_selection(interaction, temp_role, "temporary role")
    if temp_role_error:
        await interaction.response.send_message(temp_role_error, ephemeral=True)
        return

    duration_seconds = parse_duration_to_seconds(time or "30m")
    if duration_seconds is None or duration_seconds <= 0:
        await interaction.response.send_message("<:disapprove:1517452151012589662> Please provide a valid time like 30m, 1h, or 2d.", ephemeral=True)
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
    await interaction.response.send_message(view=view)
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


# -------------------------------------------------------------------------------------------------------------
#                                               Deleted Edited / Ghost Pings / Error
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="deleted", description="View recently deleted messages and media")
@app_commands.allowed_installs(guilds=True, users=False)
async def deleted(interaction: discord.Interaction, user: discord.Member = None):
    clean_cache()
    guild_config, _ = get_guild_config(str(interaction.guild.id))
    if not guild_config.get("edit_delete_history_enabled", True):
        await interaction.response.send_message("<:disapprove:1517452151012589662> Deleted message history is disabled for this server.")
        return
    channel_msgs = [m for m in deleted_cache if m['channel'] == interaction.channel_id]
    if user:
        channel_msgs = [m for m in channel_msgs if m['author'].id == user.id]
    if not channel_msgs:
        await interaction.response.send_message("No deleted messages found in this channel recently.")
        return

    description_lines = []
    media_only_messages = []

    for m in channel_msgs:
        media_indicator = "<:image:1517497571470348539> " if m['media'] else ""
        if m['media']:
            media_only_messages.append(m)
        content_text = m['content'] if m['content'] else "*[Media or Embed]*"
        description_lines.append(f"{media_indicator}**{m['author'].display_name}**: {content_text}\n-# Sent at {discord_timestamp(m['created_at'])}")

    full_description = "\n\n".join(description_lines)

    if media_only_messages:
        media_only_messages.sort(key=lambda x: x['time'], reverse=True)
        view = DeletedMessagesView(full_description, media_only_messages, interaction.user)
        await interaction.response.send_message(view=view)
        view.message = await interaction.original_response()
    else:
        view = V2InfoContainerView(
            "<:trash:1517497581058527404> Recent deleted messages:",
            full_description,
            discord.Color.red(),
        )
        await interaction.response.send_message(view=view)


@bot.tree.command(name="edited", description="Show recently edited messages in this channel")
@app_commands.describe(user="Optional: Only show edited messages from a specific user")
@app_commands.allowed_installs(guilds=True, users=False)
async def edited_command(interaction: discord.Interaction, user: discord.Member = None):
    global edited_cache
    clean_cache()
    guild_config, _ = get_guild_config(str(interaction.guild.id))
    if not guild_config.get("edit_delete_history_enabled", True):
        await interaction.response.send_message("<:disapprove:1517452151012589662> Edited message history is disabled for this server.")
        return

    channel_edited = [m for m in edited_cache if m['channel'] == interaction.channel_id]

    if user:
        channel_edited = [m for m in channel_edited if m['author_id'] == user.id]

    if not channel_edited:
        await interaction.response.send_message("No messages have been edited in this channel recently.")
        return

    text_layout = ""
    for msg in channel_edited[:7]:
        text_layout += f"**{msg['author'].display_name}**: ~~{msg['old_content']}~~ ➔ {msg['new_content']}\n-# Edited at {discord_timestamp(msg['edited_at'])} | [Jump to Message]({msg['jump_url']})\n\n"

    title_text = "<:edit:1517497568421085256> Recently Edited Messages"

    view = V2InfoContainerView(
        title_text,
        text_layout,
        discord.Color.orange(),
    )
    await interaction.response.send_message(view=view)


@bot.tree.command(name="errors", description="Show recent bot errors in this server")
@app_commands.allowed_installs(guilds=True, users=False)
async def errors(interaction: discord.Interaction):
    clean_cache()

    guild_errors = [entry for entry in bot_error_cache if entry.get("guild_id") == interaction.guild_id]
    if not guild_errors:
        await interaction.response.send_message("No bot errors have been recorded for this server recently.")
        return

    recent_errors = list(reversed(guild_errors[-7:]))
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
    await interaction.response.send_message(view=view)


@bot.tree.command(name="forget", description="Clear your messages from the bot's memory")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
async def forget(interaction: discord.Interaction):
    clean_cache()
    global message_cache, deleted_cache, edited_cache
    
    message_cache = [m for m in message_cache if m['author'].id != interaction.user.id]
    deleted_cache = [m for m in deleted_cache if m['author'].id != interaction.user.id]
    edited_cache = [m for m in edited_cache if m['author'].id != interaction.user.id]
    
    await interaction.response.send_message("I've wiped your messages, edits, and media from my memory!", ephemeral=True)


@bot.tree.command(name="forget_adm", description="Clear edited and deleted history of a chosen user")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@app_commands.default_permissions(manage_messages=True)
async def adm_forget(interaction: discord.Interaction, user: discord.Member):
    clean_cache()
    global message_cache, deleted_cache, edited_cache
    message_cache = [m for m in message_cache if m['author'].id != user.id]
    deleted_cache = [m for m in deleted_cache if m['author'].id != user.id]
    edited_cache = [m for m in edited_cache if m['author'].id != user.id]
    await interaction.response.send_message(
        f"Cleared deleted and edited history for {user.display_name}."
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
        await interaction.response.send_message(f"<:approve:1517452125687513158> Counter in {channel.mention} is now set to {value}.", ephemeral=False)
    else:
        await interaction.response.send_message(f"<:warning:1517452174991556758> That channel does not have an active counter.", ephemeral=True)




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


@bot.tree.command(name="add_lock", description="Lock this channel - messages will be logged and deleted.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def lock_command(interaction: discord.Interaction):
    locked_channels[interaction.channel_id] = True
    save_lock_config(locked_channels, admin_log_channels)
    await interaction.response.send_message(f"<:locked:1517574877257924809> Channel locked.")


@bot.tree.command(name="remove_lock", description="Unlock this channel.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def unlock_command(interaction: discord.Interaction):
    if interaction.channel_id in locked_channels:
        locked_channels.pop(interaction.channel_id)
        save_lock_config(locked_channels, admin_log_channels)
        await interaction.response.send_message("<:unlocked:1517574880034558102> Channel unlocked.")
    else:
        await interaction.response.send_message("<:warning:1517452174991556758> This channel is not currently locked.", ephemeral=True)


@bot.tree.command(name="pause_lock", description="Pause message deletion for this channel or all locked channels.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def pause_command(interaction: discord.Interaction, channel: discord.TextChannel = None):
    guild_id = interaction.guild_id
    if channel is None:
        all_paused_guilds.add(guild_id)
        await interaction.response.send_message("<:pause:1517497575219920986> Message deletion paused for all locked channels in this server.")
        return
    if guild_id not in server_pauses:
        server_pauses[guild_id] = set()
    server_pauses[guild_id].add(channel.id)
    await interaction.response.send_message(f"<:pause:1517497575219920986> Message deletion paused for {channel.mention}.")


@bot.tree.command(name="resume_lock", description="Resume message deletion for this channel or all locked channels.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def resume_command(interaction: discord.Interaction, channel: discord.TextChannel = None):
    guild_id = interaction.guild_id
    if channel is None:
        all_paused_guilds.discard(guild_id)
        await interaction.response.send_message("<:play:1517497576855965716> Message deletion resumed for all locked channels in this server.")
        return
    if guild_id not in server_pauses:
        server_pauses[guild_id] = set()
    server_pauses[guild_id].discard(channel.id)
    await interaction.response.send_message(f"<:play:1517497576855965716> Message deletion resumed for {channel.mention}.")




# -------------------------------------------------------------------------------------------------------------
#                                               Welcome/Goodbye Commands
# -------------------------------------------------------------------------------------------------------------




async def create_welcome_card(member):
    base_path = os.path.dirname(__file__)
    style = get_user_banner_style(str(member.id))
    alt_bg = os.path.join(base_path, "welcome_bg_alt.png")
    default_bg = os.path.join(base_path, "welcome_bg.png")
    bg_path = alt_bg if style == "alt" and os.path.exists(alt_bg) else default_bg
    font_path = os.path.join(base_path, "Minecraft.ttf")

    if not os.path.exists(bg_path):
        print(f"Background not found at: {bg_path}")
        return None

    background = Image.open(bg_path).convert("RGBA")
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

    draw.text((35, 30), f"Welcome", fill=(255, 255, 255), font=font_big)
    draw.text((35, 80), format_banner_username(get_banner_name(member), 25), fill=(255, 255, 255), font=font_medium)
    draw.text((35, 140), f"to the {member.guild.name} server", fill=(200, 200, 200), font=font_small)

    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="welcome.png")


async def create_goodbye_card(member):
    base_path = os.path.dirname(__file__)
    goodbye_bg_path = os.path.join(base_path, "goodbye_bg.png")
    bg_path = goodbye_bg_path if os.path.exists(goodbye_bg_path) else os.path.join(base_path, "welcome_bg.png")
    font_path = os.path.join(base_path, "Minecraft.ttf")

    if not os.path.exists(bg_path):
        print(f"Goodbye background not found at: {bg_path}")
        return None

    background = Image.open(bg_path).convert("RGBA")
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

    draw.text((35, 30), "Goodbye", fill=(255, 255, 255), font=font_big)
    draw.text((35, 80), format_banner_username(get_banner_name(member), 25), fill=(255, 255, 255), font=font_medium)
    draw.text((35, 140), f"from {member.guild.name}", fill=(200, 200, 200), font=font_small)
    draw.text((35, 170), "We hope to see you again soon!", fill=(200, 200, 200), font=font_small)

    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="goodbye.png")

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


def format_quote_content(message: discord.Message) -> str:
    content = message.content.strip() or "[Embed or media content]"
    if not content:
        return content

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
            user = message.guild.get_member(user_id) or message.guild.get_user(user_id)
        if user is None:
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
            channel = message.guild.get_channel(channel_id)
        if channel is None:
            continue

        channel_name = getattr(channel, "name", None) or str(channel_id)
        replacements.append((f"<# {channel_id}>", f"#{channel_name}"))
        replacements.append((f"<#{channel_id}>", f"#{channel_name}"))

    if getattr(message, "guild", None):
        for role in getattr(message, "role_mentions", []) or []:
            role_name = getattr(role, "name", None) or str(getattr(role, "id", ""))
            replacements.append((f"<@&{role.id}>", f"@&{role_name}"))

    for old, new in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        content = content.replace(old, new)

    return content.replace('\n', ' ')


async def create_quote_card(message: discord.Message):
    base_path = os.path.dirname(__file__)
    bg_path = os.path.join(base_path, "Quote_bg.png")
    fg_path = os.path.join(base_path, "Quote_fg.png")
    font_path = os.path.join(base_path, "Minecraft.ttf")

    if not os.path.exists(bg_path) or not os.path.exists(fg_path):
        print(f"Quote background or foreground not found at: {bg_path}, {fg_path}")
        return None

    background = Image.open(bg_path).convert("RGBA")
    foreground = Image.open(fg_path).convert("RGBA")
    avatar_bytes = await message.author.display_avatar.with_format("png").read()

    with Image.open(io.BytesIO(avatar_bytes)) as avatar:
        avatar = avatar.convert("RGBA").resize((200, 200))
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
    if len(display_name_value) > 15:
        display_name_value = display_name_value[:14] + "..."
    display_name_text = f"- {display_name_value}"

    username_value = message.author.name
    if len(username_value) > 12:
        username_value = username_value[:11] + "..."
    username_text = f"@{username_value}"
    show_username = display_name_is_ascii

    original_content = format_quote_content(message)
    content_text = original_content
    has_emoji = any(is_emoji_character(char) for char in original_content)
    had_non_ascii = any(ord(char) > 127 and not is_emoji_character(char) for char in original_content)
    use_local_font = had_non_ascii or has_emoji
    quote_font_path = find_font_file(base_path, text=content_text) if use_local_font else font_path
    content_text = f'"{content_text}"'

    bg_width, bg_height = background.size
    text_x = 250
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
        quote_font_size = max(12, 24 - 4 * (len(lines) - 4))
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
            quote_font_size = max(12, 24 - 4 * (len(lines) - 4))
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

    display_bbox = draw.textbbox((0, 0), display_name_text, font=font_display)
    footer_y = bg_height - 44
    username_y = footer_y - 4
    display_y = username_y

    draw.text((text_x, display_y), display_name_text, fill=(255, 255, 255), font=font_display)
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
    if limit <= 0:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> Limit must be greater than 0.", ephemeral=True)

    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    users = guild.get("users", {})
    if not users:
        return await interaction.response.send_message("No economy data for this server.", ephemeral=True)

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
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="balance", description="Check your balance or another user's balance")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.describe(user="The user whose balance you want to check")
async def eco_balance(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    data = load_data()
    money = data.get(str(interaction.guild.id), {}).get("users", {}).get(str(target.id), {}).get("balance", 0)
    await interaction.response.send_message(f"<:money:1517580310395486239> {target.display_name}'s balance: **${money}**")


@bot.tree.command(name="daily", description="Claim your daily reward")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.checks.cooldown(1, 86400, key=lambda i: (i.user.id, i.guild.id))
async def eco_daily(interaction: discord.Interaction):
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    earnings = random.randint(150, 200)
    user_data["balance"] += earnings
    save_data(data)
    await interaction.response.send_message(f"<:money:1517580310395486239> You claimed your daily reward and earned **${earnings}**!")


@bot.tree.command(name="pay", description="Pay another user from your balance")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_pay(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> Amount must be greater than 0.", ephemeral=True)
    data = load_data()
    guild_id = str(interaction.guild.id)
    sender_data = get_user_data(data, guild_id, str(interaction.user.id))
    receiver_data = get_user_data(data, guild_id, str(user.id))
    if sender_data["balance"] < amount:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> You don't have enough money!", ephemeral=True)
    sender_data["balance"] -= amount
    receiver_data["balance"] += amount
    save_data(data)
    await interaction.response.send_message(f"<:approve:1517452125687513158> Successfully sent **${amount}** to {format_user_reference(user)}!")


@bot.tree.command(name="shop", description="View the server shop")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_shop(interaction: discord.Interaction):
    data = load_data()
    shop_items = data.get(str(interaction.guild.id), {}).get("shop", {})
    if not shop_items:
        await interaction.response.send_message("The shop is currently empty!")
        return

    view = ShopView(shop_items, str(interaction.guild.id), str(interaction.user.id))
    await interaction.response.send_message(view=view)


@bot.tree.command(name="inventory", description="Check your inventory or another user's inventory")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.describe(user="The user whose inventory you want to check")
async def eco_inventory(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(target.id))
    inv = user_data.get("inventory", {})
    embed = discord.Embed(title=f"<:box:1517581439552585759> {target.display_name}'s Inventory", color=discord.Color.green())
    if not inv:
        embed.description = "This inventory is currently empty."
    else:
        embed.description = "\n".join(f"• {item} ×{count}" for item, count in inv.items())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="inventory-edit", description="Edit a user's inventory (Owner Only)")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_inventory_edit(interaction: discord.Interaction, user: discord.Member, item: str, action: str, amount: int = 1):
    item = normalize_item(item)
    action = action.lower().strip()
    if action not in ("add", "remove"):
        return await interaction.response.send_message("<:disapprove:1517452151012589662> Action must be **add** or **remove**.", ephemeral=True)
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(user.id))
    if action == "add":
        inventory_add(user_data["inventory"], item, amount)
    else:
        removed = inventory_remove(user_data["inventory"], item, amount)
        if removed < amount:
            save_data(data)
            return await interaction.response.send_message(
                f"<:warning:1517452174991556758> Only removed **{removed}x {item}** - {user.display_name} didn't have enough.", ephemeral=True
            )
    save_data(data)
    direction = "to" if action == "add" else "from"
    await interaction.response.send_message(f"<:approve:1517452125687513158> {action.capitalize()}d **{amount}x {item}** {direction} {user.display_name}'s inventory.")


@bot.tree.command(name="balance-edit", description="Set a user's balance (Owner Only)")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_balance_edit(interaction: discord.Interaction, user: discord.Member, amount: int):
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(user.id))
    user_data["balance"] = amount
    save_data(data)
    await interaction.response.send_message(f"<:approve:1517452125687513158> Set {user.display_name}'s balance to **${amount}**.")




# -------------------------------------------------------------------------------------------------------------
#                                               Minigames
# -------------------------------------------------------------------------------------------------------------





@bot.tree.command(name="slot_game", description="Play the economy slot machine and wager money")
@app_commands.allowed_installs(guilds=True, users=False)
async def game_slot(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> Bet amount must be greater than 0.", ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))
    before_balance = user_data["balance"]

    if before_balance < amount:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> You don't have enough money to place that bet.", ephemeral=True)

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
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="coinflip_game", description="Play coinflip and wager money")
@app_commands.allowed_installs(guilds=True, users=False)
async def game_coinflip(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> Bet amount must be greater than 0.", ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))
    before_balance = user_data["balance"]

    if before_balance < amount:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> You don't have enough money to place that bet.", ephemeral=True)

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

    embed = discord.Embed(title="<:coin:1518351100783231138> Coin Flip", description=f"Bet: **${amount}**", color=color)
    embed.add_field(name="Result", value=result_text, inline=False)
    embed.set_footer(text=f"Before: ${before_balance} • After: ${user_data['balance']}")
    await interaction.response.send_message(embed=embed)


class MinesButton(discord.ui.Button):
    def __init__(self, index: int, row: int, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="❓", row=row)
        self.index = index
        self.row_index = row
        self.col_index = col

    async def callback(self, interaction: discord.Interaction):
        view: MinesGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)
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
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)
        if not view.action_taken:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> You must reveal at least one tile before cashing out.", ephemeral=True)

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
        super().__init__(timeout=180)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
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
    if amount <= 0:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> Bet amount must be greater than 0.", ephemeral=True)
    if mines < 3 or mines > 10:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> Number of mines must be between 3 and 10.", ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))
    before_balance = user_data["balance"]

    if interaction.user.id in active_minigame_users:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> You already have an active minigame. Finish or wait for it to time out before starting another.", ephemeral=True)

    if before_balance < amount:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> You don't have enough money to place that bet.", ephemeral=True)

    user_data["balance"] -= amount
    save_data(data)
    view = MinesGameView(amount=amount, mines=mines, guild_id=guild_id, user_id=interaction.user.id, before_balance=before_balance)
    active_minigame_users.add(interaction.user.id)
    await interaction.response.send_message(embed=view.embed, view=view)
    view.message = await interaction.original_response()


class TowerButton(discord.ui.Button):
    def __init__(self, row: int, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="❓", row=row)
        self.row_index = row
        self.col_index = col

    async def callback(self, interaction: discord.Interaction):
        view: TowersGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)
        if self.row_index != view.current_row:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> You must click a button in the current row first.", ephemeral=True)

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
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)
        if not view.action_taken:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> You must pick at least one tile before cashing out.", ephemeral=True)

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
        super().__init__(timeout=180)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
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
    if amount <= 0:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> Bet amount must be greater than 0.", ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))
    before_balance = user_data["balance"]

    if interaction.user.id in active_minigame_users:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> You already have an active minigame. Finish or wait for it to time out before starting another.", ephemeral=True)

    if before_balance < amount:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> You don't have enough money to place that bet.", ephemeral=True)

    user_data["balance"] -= amount
    save_data(data)
    view = TowersGameView(amount=amount, guild_id=guild_id, user_id=interaction.user.id, before_balance=before_balance)
    active_minigame_users.add(interaction.user.id)
    await interaction.response.send_message(embed=view.embed, view=view)
    view.message = await interaction.original_response()

class DeveloperCodeSelect(discord.ui.Select):
    def __init__(self, correct_index: int):
        self.correct_index = correct_index
        options = [discord.SelectOption(label=f"Code {i+1}", value=str(i)) for i in range(10)]
        super().__init__(placeholder="Choose the different code...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        view: WorkGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)

        selected_index = int(self.values[0])
        
        if selected_index == self.correct_index:
            view.finished = True
            view.disable_all_items()
            payout = get_work_payout(view.difficulty)
            data = load_data()
            user_data = get_user_data(data, view.guild_id, view.user_id)
            user_data["balance"] += payout
            save_data(data)
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
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)

        if self.is_odd:
            view.finished = True
            view.disable_all_items()
            payout = get_work_payout(view.difficulty)
            data = load_data()
            user_data = get_user_data(data, view.guild_id, view.user_id)
            user_data["balance"] += payout
            save_data(data)
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
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)

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
                    return await modal_interaction.response.send_message("<:multi:1518348755261460661> This is not for you.", ephemeral=True)
                if self.view.finished:
                    return await modal_interaction.response.send_message("<:disapprove:1517452151012589662> Game already finished.", ephemeral=True)
                
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
                        await self.view.message.edit(embed=self.view.embed, view=self.view)
                    else:
                        self.view.finished = True
                        self.view.disable_all_items()
                        self.view.embed.title = "<:minus:1518348754111959150> Math Teacher Job - Failed!"
                        self.view.embed.description = f"Wrong! The correct answer is **{self.view.correct_answer}**. You didn't earn anything this time."
                        await modal_interaction.response.defer()
                        await self.view.message.edit(embed=self.view.embed, view=self.view)
                except ValueError:
                    await modal_interaction.response.send_message("<:disapprove:1517452151012589662> Please enter a valid number.", ephemeral=True)
        
        submit_button = discord.ui.Button(label="Submit Answer", style=discord.ButtonStyle.primary)
        
        async def submit_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
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
            return await interaction.response.send_message(
                f"<:timer:1517996239583576194> You can work again in **{minutes}m {seconds}s**.",
                ephemeral=True
            )
    
    data = load_data()
    user_data = get_user_data(data, guild_id, user_id)
    
    job_type = random.choice(["developer", "farmer", "math"])
    amount = 0
    
    work_cooldowns[cooldown_key] = now
    
    view = WorkGameView(job_type, guild_id, interaction.user.id, amount, difficulty)
    await interaction.response.send_message(embed=view.embed, view=view)
    view.message = await interaction.original_response()




# -------------------------------------------------------------------------------------------------------------
#                                               Crafting Commands
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="craft", description="Craft an item")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_craft(interaction: discord.Interaction, item: str, amount: int = 1):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    canonical_item = find_item_key(guild["recipes"], item)
    if not canonical_item:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> This item is not craftable.", ephemeral=True)
    recipe = guild["recipes"][canonical_item]
    delay = recipe.get("delay", 0)
    for req_item, count in recipe["reqs"].items():
        if inventory_count(user_data["inventory"], req_item) < (count * amount):
            return await interaction.response.send_message(f"<:disapprove:1517452151012589662> You don't have enough **{req_item}**.", ephemeral=True)
    await interaction.response.send_message(f"🔨 Starting to craft {amount}x **{canonical_item}**... (Wait {delay}s)")
    if delay > 0:
        await asyncio.sleep(delay)
        data = load_data()
        guild = get_guild_data(data, str(interaction.guild.id))
        user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
        for req_item, count in recipe["reqs"].items():
            if inventory_count(user_data["inventory"], req_item) < (count * amount):
                return await interaction.followup.send("<:disapprove:1517452151012589662> Crafting failed: You spent your ingredients while waiting!", ephemeral=True)
    for req_item, count in recipe["reqs"].items():
        inventory_remove(user_data["inventory"], req_item, count * amount)
    inventory_add(user_data["inventory"], canonical_item, amount)
    save_data(data)
    await interaction.followup.send(f"<:approve:1517452125687513158> Finished crafting {amount}x **{canonical_item}**!")


@bot.tree.command(name="use", description="Use an item from your inventory")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_use(interaction: discord.Interaction, item: str, number_of_times: int = 1):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    if inventory_count(user_data["inventory"], item) < number_of_times:
        return await interaction.response.send_message(f"<:disapprove:1517452151012589662> You need **{number_of_times}x** of this item to do that.", ephemeral=True)
    canonical_item = find_item_key(guild["item_uses"], item)
    if not canonical_item:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> This item has no special use effect.", ephemeral=True)
    effect = guild["item_uses"][canonical_item]
    if number_of_times > 1 and (effect.get("role_id") or effect.get("temp_role_id")):
        return await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot use role-giving items multiple times at once.", ephemeral=True)
    if effect.get("instant_message"):
        await interaction.response.send_message(effect["instant_message"])
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
        await interaction.response.send_message(final_msg)


@bot.tree.command(name="sell", description="Sell a specific amount of an item from your inventory")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_sell(interaction: discord.Interaction, item: str, amount: int = 1):
    if amount <= 0:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> You must sell at least 1 item.", ephemeral=True)
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    canonical_item = find_item_key(guild.get("item_values", {}), item)
    if canonical_item is None:
        return await interaction.response.send_message(f"<:disapprove:1517452151012589662> **{item}** cannot be sold. No price has been set for it.", ephemeral=True)
    item_price = guild["item_values"][canonical_item]
    user_count = inventory_count(user_data["inventory"], canonical_item)
    if user_count < amount:
        return await interaction.response.send_message(
            f"<:disapprove:1517452151012589662> You don't have enough! You have **{user_count}x {canonical_item}**, but tried to sell **{amount}x**.", ephemeral=True
        )
    inventory_remove(user_data["inventory"], canonical_item, amount)
    total_value = item_price * amount
    user_data["balance"] += total_value
    save_data(data)
    await interaction.response.send_message(
        f"<:money:1517580310395486239> You sold **{amount}x {canonical_item}** for a total of **${total_value}**!\n"
        f"Your new balance is **${user_data['balance']}**."
    )


@bot.tree.command(name="values_info", description="Show all items that can be sold and their prices")
@app_commands.allowed_installs(guilds=True, users=False)
async def info_values(interaction: discord.Interaction):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    prices = guild.get("item_values", {})
    if not prices:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> No items have a selling price set yet.", ephemeral=True)

    embed = discord.Embed(title="<:money:1517580310395486239> Item Market Prices", color=discord.Color.gold())
    for item, price in prices.items():
        embed.add_field(name=item, value=f"Sell Price: **${price}**", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="recipes_info", description="Show all available crafting recipes")
@app_commands.allowed_installs(guilds=True, users=False)
async def info_recipes(interaction: discord.Interaction):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    recipes = guild.get("recipes", {})
    if not recipes:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> No crafting recipes found.", ephemeral=True)

    embed = discord.Embed(title="<:craft:1518348021161660539> Crafting Book", color=discord.Color.blue())
    for result_item, recipe in recipes.items():
        ing_list = ", ".join(f"{amt}x {name}" for name, amt in recipe["reqs"].items())
        delay_str = f"<:timer:1517996239583576194> {recipe.get('delay', 0)}s" if recipe.get("delay", 0) > 0 else ""
        embed.add_field(
            name=result_item,
            value=f"Requires: {ing_list}" + (f"\n{delay_str}" if delay_str else ""),
            inline=False,
        )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="uses_info", description="Show what items do when used")
@app_commands.allowed_installs(guilds=True, users=False)
async def info_uses(interaction: discord.Interaction):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    uses = guild.get("item_uses", {})
    if not uses:
        return await interaction.response.send_message("<:disapprove:1517452151012589662> No item effects have been set up.", ephemeral=True)

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
        return await interaction.response.send_message("<:disapprove:1517452151012589662> No item effects have been set up.", ephemeral=True)

    await interaction.response.send_message(embed=embed)




# -------------------------------------------------------------------------------------------------------------
#                                               Leveling System
# -------------------------------------------------------------------------------------------------------------




async def add_xp(member: discord.Member, guild: discord.Guild, xp_to_add: int, announce_channel=None):
    if member.bot:
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
    
    leveled_up = False
    while user_data["xp"] >= get_xp_needed(user_data["level"]):
        user_data["xp"] -= get_xp_needed(user_data["level"])
        user_data["level"] += 1
        leveled_up = True
        
    has_leveled_up_before = get_user_has_leveled_up_before(user_id)
    first_time_level_up = leveled_up and not has_leveled_up_before

    save_levels(levels)
    
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
                level_up_message = f"{format_user_reference(member)} just reached **Level {current_level}**!"
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
                    level_banner_message = f"{format_user_reference(member)}, you just reached **Level {current_level}**!"
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
    style = get_user_banner_style(str(member.id))
    alt_bg = os.path.join(base_path, "levelup_bg_alt.png")
    default_bg = os.path.join(base_path, "levelup_bg.png")
    bg_path = alt_bg if style == "alt" and os.path.exists(alt_bg) else default_bg
    font_path = os.path.join(base_path, "Minecraft.ttf")
    
    if not os.path.exists(bg_path):
        return None
        
    background = Image.open(bg_path).convert("RGBA")
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
        
    draw.text((center_x, 190), f"{format_banner_username(get_banner_name(member))} you are now Level {level}!", fill="white", font=font, anchor="mm")
    
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

COLOR_EMOJIS = {
    "white": "<:Square_White:1517679898414813427>", "black": "<:Square_Black:1517679889615032540>", "red": "<:Square_Red:1517679897068306522>", "blue": "<:Square_Blue:1517679890932043897>", 
    "green": "<:Square_Green:1517679893234716843>", "yellow": "<:Square_Yellow:1517679899769311302>", "purple": "<:Square_Purple:1517679895738581062>", "orange": "<:Square_Orange:1517679894526562405>", "brown": "<:Square_Brown:1517679892039204955>"
}


@bot.tree.command(name="level", description="View your current server tier standing level rank card")
@app_commands.allowed_installs(guilds=True, users=False)
async def view_level(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    levels = load_levels()
    g_id, u_id = str(interaction.guild_id), str(target.id)
    
    user_data = levels.get(g_id, {}).get("users", {}).get(u_id, {"xp": 0, "level": 0, "color": "white"})
    
    current_xp = user_data["xp"]
    current_lvl = user_data["level"]
    chosen_color = get_user_color(u_id) or user_data.get("color", "white") or "white"
    
    xp_needed = get_xp_needed(current_lvl)
    
    ratio = current_xp / xp_needed if xp_needed > 0 else 0
    filled_blocks = min(max(int(ratio * 10), 0), 10)
    empty_blocks = 10 - filled_blocks
    
    filled_emoji = COLOR_EMOJIS.get(chosen_color, "<:Square_White:1517679898414813427>")
    empty_emoji = COLOR_EMOJIS.get("black", "<:Square_Black:1517679889615032540>")
    
    progress_bar = (filled_emoji * filled_blocks) + (empty_emoji * empty_blocks)
    
    embed = discord.Embed(
        title=f"<:chalice:1517579767573123092> Rank Profile - {target.display_name}",
        color=discord.Color.dark_gray()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Current Tier", value=f"<:spark:1517583248421552305> **Level {current_lvl}**", inline=True)
    embed.add_field(name="Experience Nodes", value=f"<:Vial:1517681553377857628> `{current_xp:,}` / `{xp_needed:,}` XP", inline=True)
    embed.add_field(name="Progress Metrics", value=progress_bar, inline=False)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="level-leaderboard", description="Display the top 10 highest-level users in this guild")
@app_commands.allowed_installs(guilds=True, users=False)
async def level_leaderboard(interaction: discord.Interaction):
    levels = load_levels()
    g_id = str(interaction.guild_id)
    
    users_dict = levels.get(g_id, {}).get("users", {})
    if not users_dict:
        return await interaction.response.send_message("📭 No active XP statistics logged in this server yet.", ephemeral=True)
        
    sorted_users = sorted(users_dict.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)
    
    embed = discord.Embed(title=f"<:graph:1517584522877866065> Level Standings Leaderboard - {interaction.guild.name}", color=discord.Color.gold())
    
    description_text = ""
    for index, (u_id, data) in enumerate(sorted_users[:10], start=1):
        member = interaction.guild.get_member(int(u_id))
        name_str = member.display_name if member else f"User left server (`{u_id}`)"
        description_text += f"`#{index}` **{name_str}** - Lvl {data['level']} ({data['xp']} XP)\n"
        
    embed.description = description_text
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="level-edit", description="(Admin) Manually adjust or set a target user's level and XP indexes")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.checks.has_permissions(manage_guild=True)
async def lvl_edit(interaction: discord.Interaction, user: discord.Member, level: int, xp: int = 0):
    levels = load_levels()
    g_id, u_id = str(interaction.guild_id), str(user.id)
    
    if g_id not in levels: levels[g_id] = {"config": {}, "users": {}}
    
    levels[g_id]["users"][u_id] = {
        "xp": max(0, xp),
        "level": max(0, level),
        "color": levels[g_id]["users"].get(u_id, {}).get("color", "white")
    }
    save_levels(levels)
    await interaction.response.send_message(f"<:gear:1517576939097952496> Action complete. Set {format_user_reference(user)} to **Level {level}** with **{xp} XP**.", ephemeral=True)


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
    levels = load_levels()
    g_id = str(interaction.guild_id)
    guild_data = levels.get(g_id, {})
    rewards = guild_data.get("config", {}).get("rewards", {})

    if not rewards:
        return await interaction.response.send_message("📭 No level rewards are configured for this server yet.", ephemeral=True)

    embed = discord.Embed(
        title=f"<:box:1517581439552585759> Level Rewards - {interaction.guild.name}",
        color=discord.Color.gold()
    )

    if level is not None:
        reward_data = rewards.get(str(level))
        if not reward_data:
            return await interaction.response.send_message(f"<:disapprove:1517452151012589662> No rewards are configured for level {level} in this server.", ephemeral=True)

        embed.description = format_level_reward_summary(interaction.guild, str(level), reward_data)
    else:
        sorted_levels = sorted(rewards.items(), key=lambda item: int(item[0]))
        embed.description = "\n".join(
            format_level_reward_summary(interaction.guild, lvl, reward_data)
            for lvl, reward_data in sorted_levels
        )

    await interaction.response.send_message(embed=embed)




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


@bot.command(name="backups")
async def backups_command(ctx: commands.Context):
    if not await bot.is_owner(ctx.author):
        return await ctx.send(F"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    view = BackupListView(ctx.author.id)
    message = await ctx.send(view=view)
    view.message = message


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
            f"Shutdown notice sent to {channel.mention}. "
            + ("Published to followers." if published else "")
        )

    await ctx.send(response_text)

    shutdown_activity = discord.Activity(type=discord.ActivityType.watching, name="App is shutting down!!! !! !")
    sleep_activity = discord.Activity(type=discord.ActivityType.watching, name="App is sleeping... zZzZzZ")
    for shard_id in bot.shards:
        await bot.change_presence(activity=shutdown_activity, status=discord.Status.dnd, shard_id=shard_id)
    await asyncio.sleep(10)
    for shard_id in bot.shards:
        await bot.change_presence(activity=sleep_activity, status=discord.Status.idle, shard_id=shard_id)
    close_local_rpc()
    await bot.close()


class ServersListView(discord.ui.View):
    def __init__(self, author_id: int, guilds: list[discord.Guild], page: int = 0):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.guilds = guilds
        self.page = page
        self.guilds_per_page = 15

    def get_page_embed(self) -> discord.Embed:
        total_pages = max(1, (len(self.guilds) + self.guilds_per_page - 1) // self.guilds_per_page)
        page = min(max(self.page, 0), total_pages - 1)
        start = page * self.guilds_per_page
        end = start + self.guilds_per_page
        chunk = self.guilds[start:end]

        embed = discord.Embed(
            title="Bot Servers",
            description=f"Showing servers {start + 1}-{min(end, len(self.guilds))} of {len(self.guilds)}",
            color=discord.Color.blue(),
        )

        for guild in chunk:
            embed.add_field(
                name=guild.name,
                value=f"ID: `{guild.id}`\nMembers: {guild.member_count}",
                inline=False,
            )

        embed.set_footer(text=f"Page {page + 1}/{total_pages}")
        return embed

    async def update_message(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command owner can navigate these pages.", ephemeral=True)
            return
        self.page = max(0, self.page - 1)
        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command owner can navigate these pages.", ephemeral=True)
            return
        total_pages = max(1, (len(self.guilds) + self.guilds_per_page - 1) // self.guilds_per_page)
        self.page = min(total_pages - 1, self.page + 1)
        await self.update_message(interaction)


@bot.command(name="servers")
async def list_servers(ctx: commands.Context):
    if not await bot.is_owner(ctx.author):
        return await ctx.send(F"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    guilds = sorted(bot.guilds, key=lambda g: g.name.lower())
    view = ServersListView(ctx.author.id, guilds)
    await ctx.send(embed=view.get_page_embed(), view=view)




# -------------------------------------------------------------------------------------------------------------
#                                               Personalization Commands
# -------------------------------------------------------------------------------------------------------------




USER_COLOR_OPTIONS = [name for name in COLOR_EMOJIS.keys() if name != "black"]


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


class SettingsMenuView(LayoutView):
    def __init__(self, user_id: int, username: str, color: discord.Color):
        super().__init__(timeout=180)
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
            )
            await interaction.response.edit_message(view=new_view)

        async def open_guild(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use guild settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.send_message(
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


class NotesMenuView(LayoutView):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This menu is only for the original user.", ephemeral=True)
            return False
        return True


class NotesView(LayoutView):
    def __init__(self, user_id: int, note_index: int = 0):
        super().__init__(timeout=180)
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
            owner = bot.get_user(self.user_id)
            owner_name = owner.display_name if owner else str(self.user_id)
            await interaction.response.send_message(
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This notes panel is only for the original user.", ephemeral=True)
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


class SharedNoteView(LayoutView):
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


class SharedChecklistView(LayoutView):
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
        self.time_input = TextInput(label="Reminder time", placeholder="in 1d 30m 10s or at yy/mm/dd hh:mm", required=True)
        self.send_input = TextInput(label="Send in channel/dm/both", placeholder="dm, channel, or both", required=True)
        self.add_item(self.name_input)
        self.add_item(self.description_input)
        self.add_item(self.time_input)
        self.add_item(self.send_input)

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip() or "Reminder"
        description = self.description_input.value.strip()
        when = parse_reminder_time(self.time_input.value)
        send = normalize_send_mode(self.send_input.value)

        if when is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Invalid reminder time. Use in 1h or at 24/12/26 18:00.", ephemeral=True)
            return

        reminder = {
            "name": name,
            "description": description,
            "when": when,
            "send": send,
        }

        if self.existing_index is None and not can_add_user_reminder(str(self.user_id)):
            await interaction.response.send_message(
                "<:disapprove:1517452151012589662> You can have up to 7 reminders at once.",
                ephemeral=True,
            )
            return

        if send in {"channel", "both"}:
            guild = interaction.guild
            if not guild:
                await interaction.response.send_message("<:disapprove:1517452151012589662> Channel reminders require server context.", ephemeral=True)
                return

            await interaction.response.send_message(
                "Select the channel for this reminder:",
                view=ChannelSelectorView(self.user_id, guild, "Select reminder channel", self.on_channel_selected, self.settings_message),
                ephemeral=True,
            )
            self.pending_reminder = reminder
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

    async def on_channel_selected(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        reminder = self.pending_reminder
        reminder["channel_id"] = channel.id
        reminders = get_user_reminders(str(self.user_id))
        if self.existing_index is None and len(reminders) >= MAX_USER_REMINDERS:
            await safe_send(
                interaction,
                "<:disapprove:1517452151012589662> You can have up to 7 reminders at once.",
                ephemeral=True,
            )
            return

        if self.existing_index is None:
            reminders.append(reminder)
        else:
            if 0 <= self.existing_index < len(reminders):
                reminders[self.existing_index] = reminder
        save_user_reminders(str(self.user_id), reminders)
        try:
            await interaction.response.edit_message(view=RemindersView(self.user_id))
        except Exception:
            try:
                await self.settings_message.edit(view=RemindersView(self.user_id))
            except Exception:
                pass
        await safe_send(interaction, f"<:approve:1517452125687513158> Reminder saved for <t:{reminder['when']}:F>.", ephemeral=True)


class RemindersView(LayoutView):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> You have no reminders yet.", ephemeral=True)
            return

        index = find_reminder_index(reminders, self.reminder_input.value)
        if index is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Reminder not found. Use number or exact name.", ephemeral=True)
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
        await interaction.response.send_message(
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> You have no reminders yet.", ephemeral=True)
            return

        index = find_reminder_index(reminders, self.reminder_input.value)
        if index is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Reminder not found. Use number or exact name.", ephemeral=True)
            return

        reminder = reminders[index]
        destination = get_reminder_destination(reminder, interaction.guild)
        reminder_text = get_reminder_message_text(reminder)
        reminder_name = reminder.get("name", "Reminder")

        owner = bot.get_user(self.user_id)
        creator_name = owner.display_name if owner else str(self.user_id)
        await interaction.response.send_message(
            view=SharedReminderView(self.user_id, creator_name, reminder),
            ephemeral=False,
        )


class SharedReminderView(LayoutView):
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

        self.add_item(Container(
            TextDisplay(f"<:timer:1517996239583576194> {title}"),
            TextDisplay(description),
            Separator(),
            TextDisplay(f"When: {when}"),
            TextDisplay(f"Sent in: {destination}"),
            TextDisplay(f"Reminder creator: {self.creator_name}"),
            accent_color=get_user_color_value(str(self.owner_id)),
        ))
        self.add_item(discord.ui.ActionRow(self.save_button))

    async def add_reminder(self, interaction: discord.Interaction):
        user_reminders = get_user_reminders(str(interaction.user.id))
        if len(user_reminders) >= MAX_USER_REMINDERS:
            await interaction.response.send_message(
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
            await interaction.response.send_message("<:approve:1517452125687513158> This reminder is already in your personal reminders.", ephemeral=True)
            return

        reminder_copy = self.reminder.copy()
        original_description = reminder_copy.get("description", "").strip()
        if original_description:
            reminder_copy["description"] = f"{original_description} (by {self.creator_name})"
        else:
            reminder_copy["description"] = f"by {self.creator_name}"

        user_reminders.append(reminder_copy)
        save_user_reminders(str(interaction.user.id), user_reminders)
        await interaction.response.send_message("<:approve:1517452125687513158> Reminder added to your personal reminders.", ephemeral=True)


class ReminderEditLaunchView(discord.ui.View):
    def __init__(self, user_id: int, settings_message: discord.Message, index: int, reminder: dict):
        super().__init__(timeout=120)
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
                modal.time_input.default = f"at {datetime.utcfromtimestamp(reminder_when):%y/%m/%d %H:%M}"
            except (OSError, OverflowError, ValueError):
                modal.time_input.default = str(reminder_when)
        else:
            modal.time_input.default = str(reminder_when)
        modal.send_input.default = self.reminder.get("send", "dm")
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.send_message("Reminder edit cancelled.", ephemeral=True)


class RemindersView(LayoutView):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.reminders = get_user_reminders(str(user_id))
        self.build_components()

    def build_components(self):
        self.clear_items()
        reminder_lines = []
        for index, reminder in enumerate(self.reminders):
            destination = get_reminder_destination(reminder, None)
            reminder_lines.append(f"{index + 1}. {reminder.get('name', 'Reminder')} : {get_reminder_display(reminder)} [{destination}]")
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This reminders panel is only for the original user.", ephemeral=True)
            return False
        return True


class ChecklistView(LayoutView):
    def __init__(self, user_id: int, page: int = 0):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.page = max(0, page)
        self.lists = get_user_lists(str(self.user_id))
        self.items = self.lists[0]
        self.build_components()

    def build_components(self):
        self.clear_items()
        page_count = (len(self.items) + CHECKLIST_PAGE_SIZE - 1) // CHECKLIST_PAGE_SIZE
        self.page = min(self.page, max(page_count - 1, 0))
        page_items = self.items[self.page * CHECKLIST_PAGE_SIZE : (self.page + 1) * CHECKLIST_PAGE_SIZE]

        item_lines = [format_checklist_item(item, self.page * CHECKLIST_PAGE_SIZE + idx) for idx, item in enumerate(page_items)]
        if not item_lines:
            item_lines = ["No list items yet."]

        self.edit_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="checklist_edit")
        self.share_button = Button(label="Share", style=discord.ButtonStyle.success, custom_id="checklist_share", disabled=not bool(self.items))
        self.cycle_button = Button(label="Next page", style=discord.ButtonStyle.secondary, custom_id="checklist_cycle", disabled=self.page >= page_count - 1)
        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="checklist_back")

        async def edit_list(interaction: discord.Interaction):
            await interaction.response.send_message(
                view=ChecklistActionView(self.user_id, self.page, interaction.message),
                ephemeral=True,
            )

        async def share_list(interaction: discord.Interaction):
            owner = bot.get_user(self.user_id)
            owner_name = owner.display_name if owner else str(self.user_id)
            await interaction.response.send_message(
                view=SharedChecklistView(self.user_id, owner_name, item_lines),
                ephemeral=False,
            )

        async def cycle_page(interaction: discord.Interaction):
            await interaction.response.edit_message(view=ChecklistView(self.user_id, self.page + 1))

        async def back_to_menu(interaction: discord.Interaction):
            await interaction.response.edit_message(view=NotesMenuView(self.user_id))

        self.edit_button.callback = edit_list
        self.share_button.callback = share_list
        self.cycle_button.callback = cycle_page
        self.back_button.callback = back_to_menu

        header_text = f"<:list:1517497572770451567> Lists for {bot.get_user(self.user_id).display_name if bot.get_user(self.user_id) else str(self.user_id)}"
        self.add_item(Container(
            TextDisplay(header_text),
            Separator(),
            TextDisplay("\n".join(item_lines)),
            accent_color=get_user_color_value(str(self.user_id)),
        ))
        self.add_item(discord.ui.ActionRow(self.edit_button, self.share_button, self.cycle_button, self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This checklist panel is only for the original user.", ephemeral=True)
            return False
        return True


class ChecklistActionView(LayoutView):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(timeout=180)
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
            await interaction.response.send_message(
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This checklist menu is only for the original user.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> You already have the maximum of 30 items.", ephemeral=True)
            return
        color = self.color_input.value.strip().lower()
        if color == "":
            color = "none"
        if color not in {"red", "yellow", "green", "none"}:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Use red, yellow, green, or none.", ephemeral=True)
            return
        item_list.append({"content": self.content_input.value.strip(), "status": color})
        save_user_lists(str(self.user_id), lists)
        await interaction.response.send_message("<:approve:1517452125687513158> Checklist item added.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Item not found.", ephemeral=True)
            return
        new_content = self.content_input.value.strip()
        new_color = self.color_input.value.strip().lower()
        if not new_content and not new_color:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Provide new content, a mark color, or both.", ephemeral=True)
            return
        if new_content:
            item_list[index]["content"] = new_content
        if new_color:
            if new_color not in {"red", "yellow", "green", "remove"}:
                await interaction.response.send_message("<:disapprove:1517452151012589662> Use red, yellow, green, or remove.", ephemeral=True)
                return
            item_list[index]["status"] = "none" if new_color == "remove" else new_color
        save_user_lists(str(self.user_id), lists)
        await interaction.response.send_message("<:approve:1517452125687513158> Checklist item updated.", ephemeral=True)
        await refresh_checklist_message(interaction, ChecklistView(self.user_id, self.page), self.settings_message)


class ChecklistRemoveChoiceView(LayoutView):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(timeout=180)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This checklist action is only for the original user.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Item not found.", ephemeral=True)
            return
        item_list.pop(index)
        save_user_lists(str(self.user_id), lists)
        await interaction.response.send_message("<:trash:1517497581058527404> Checklist item removed.", ephemeral=True)
        await refresh_checklist_message(interaction, ChecklistView(self.user_id, self.page), self.settings_message)


class UserSettingsView(LayoutView):
    def __init__(self, user_id: int, current_color: str, current_pings: bool, current_style: str = "normal"):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.current_color = current_color or "white"
        self.current_pings = current_pings
        self.current_style = current_style if current_style in {"normal", "alt"} else "normal"
        self.build_components()

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
            await interaction.response.edit_message(view=UserSettingsView(self.user_id, self.current_color, self.current_pings, self.current_style))

        self.ping_button.callback = ping_callback

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
            self.current_color = self.color_select.values[0]
            user_settings["color"] = self.current_color
            save_user_settings(settings)
            await interaction.response.edit_message(view=UserSettingsView(self.user_id, self.current_color, self.current_pings, self.current_style))

        self.color_select.callback = color_select_callback

        self.banner_style_button = discord.ui.Button(
            label=f"Switch to {'Alternate' if self.current_style == 'normal' else 'Normal'}",
            style=discord.ButtonStyle.secondary,
            custom_id="user_banner_style_toggle",
        )

        async def banner_style_button_callback(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            self.current_style = "alt" if self.current_style == "normal" else "normal"
            user_settings["banner_style"] = self.current_style
            save_user_settings(settings)
            await interaction.response.edit_message(view=UserSettingsView(self.user_id, self.current_color, self.current_pings, self.current_style))

        self.banner_style_button.callback = banner_style_button_callback

        self.back_button = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="user_settings_back")

        async def back_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

        self.back_button.callback = back_callback

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **User settings**"),
            TextDisplay("Adjust your personal preferences below."),
            Separator(),
            Section(f"<:bell:1517497562184024275> Ping notifications: {'Enabled' if self.current_pings else 'Disabled'}", accessory=self.ping_button),
            Section(
                f"<:frames:1517497568421085256> Banner style: {self.current_style.title()}",
                accessory=self.banner_style_button,
            ),
            TextDisplay(f"<:rainbow:1518708398772846722> User color: {COLOR_EMOJIS.get(self.current_color, self.current_color)} {self.current_color.title()}"),
            accent_color=get_user_color_value(str(self.user_id)),
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.color_select))
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True


class GuildSettingsMenuView(LayoutView):
    def __init__(self, user_id: int, guild_id: str):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.color = get_user_color_value(str(user_id))
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.general_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="guild_settings_menu_general",
        )
        self.channel_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="guild_settings_menu_channel",
        )
        self.economy_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="guild_settings_menu_economy",
        )
        self.level_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="guild_settings_menu_level",
        )
        self.automod_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="guild_settings_menu_automod",
        )

        async def open_general(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use guild settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.send_message(
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
                level_up_enabled=guild_config.get("level_up_message_enabled", False),
            )
            await interaction.response.edit_message(view=new_view)

        async def open_channel_settings(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use channel settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_channels:
                await interaction.response.send_message(
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
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use economy settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.send_message(
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
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use level settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.send_message(
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
                await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> You can't use automod settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.send_message(
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

        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="guild_settings_menu_back")
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
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True


class GuildSettingsView(LayoutView):
    def __init__(self, user_id: int, guild_id: str, ghost_pings: bool, history_enabled: bool, level_up_enabled: bool):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.ghost_pings = ghost_pings
        self.history_enabled = history_enabled
        self.level_up_enabled = level_up_enabled
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
        self.level_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_level_up",
        )
        self.auto_reply_button = discord.ui.Button(
            label="Edit",
            style=discord.ButtonStyle.primary,
            custom_id="guild_auto_reply",
        )

        fun_data = load_fun_data()
        auto_reply_triggers = sorted(fun_data.get(self.guild_id, {}).keys()) if self.guild_id in fun_data else []
        auto_reply_text = "\n".join(auto_reply_triggers) if auto_reply_triggers else "None"

        async def ghost_callback(interaction: discord.Interaction):
            guild_config, data = get_guild_config(self.guild_id)
            self.ghost_pings = not self.ghost_pings
            guild_config["ghost_ping_enabled"] = self.ghost_pings
            save_guild_data(data)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.level_up_enabled))

        async def history_callback(interaction: discord.Interaction):
            guild_config, data = get_guild_config(self.guild_id)
            self.history_enabled = not self.history_enabled
            guild_config["edit_delete_history_enabled"] = self.history_enabled
            save_guild_data(data)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.level_up_enabled))

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
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.level_up_enabled))

        self.ghost_button.callback = ghost_callback
        self.history_button.callback = history_callback
        self.level_button.callback = level_callback
        self.auto_reply_button.callback = self.handle_auto_reply_edit

        self.back_button = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="guild_settings_back")

        async def back_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

        self.back_button.callback = back_callback

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **General settings**"),
            TextDisplay("Adjust general guild-wide behavior below."),
            Separator(),
            Section(f"<:ghost:1517497569939558470> Ghost pings: {'Enabled' if self.ghost_pings else 'Disabled'}", accessory=self.ghost_button),
            Section(f"<:trash:1517497581058527404> Edit/Delete history: {'Enabled' if self.history_enabled else 'Disabled'}", accessory=self.history_button),
            Section(f"<:chalice:1517579767573123092> Level-up messages: {'Enabled' if self.level_up_enabled else 'Disabled'}", accessory=self.level_button),
            Section(f"<:spark:1517583248421552305> Auto-reply triggers\n{auto_reply_text}", accessory=self.auto_reply_button),
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Unable to determine the settings message.", ephemeral=True)
            return

        await interaction.response.send_message(
            "What would you like to do with Auto-reply triggers?",
            view=AutoReplyChoiceView(
                self.user_id,
                self.open_auto_reply_add,
                self.open_auto_reply_remove,
                settings_message,
            ),
            ephemeral=True,
        )

    async def open_auto_reply_add(self, interaction: discord.Interaction, settings_message: discord.Message | None):
        await interaction.response.send_modal(AutoReplyAddModal(self.add_auto_reply, self.guild_id, settings_message))

    async def open_auto_reply_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None):
        await interaction.response.send_modal(AutoReplyRemoveModal(self.remove_auto_reply, self.guild_id, settings_message))

    async def add_auto_reply(self, interaction: discord.Interaction, word: str, replies: list[str], settings_message: discord.Message | None):
        fun_data = load_fun_data()
        if self.guild_id not in fun_data:
            fun_data[self.guild_id] = {}
        fun_data[self.guild_id][word.lower()] = replies
        save_fun_data(fun_data)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Auto reply for '{word}' saved.", ephemeral=True)

        await self.refresh_settings_message(
            interaction,
            GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.level_up_enabled),
            settings_message,
        )

    async def remove_auto_reply(self, interaction: discord.Interaction, word: str, settings_message: discord.Message | None):
        fun_data = load_fun_data()
        if self.guild_id in fun_data and word.lower() in fun_data[self.guild_id]:
            del fun_data[self.guild_id][word.lower()]
            if not fun_data[self.guild_id]:
                del fun_data[self.guild_id]
            save_fun_data(fun_data)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Auto reply for '{word}' removed.", ephemeral=True)

            await self.refresh_settings_message(
                interaction,
                GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.level_up_enabled),
                settings_message,
            )
        else:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> No auto reply found for '{word}'.", ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True


class ConfirmRemoveView(discord.ui.View):
    def __init__(self, user_id: int, confirm_callback, original_message: discord.Message):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This confirmation is only for the original user.", ephemeral=True)
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


class ChannelSelectorView(discord.ui.View):
    def __init__(self, user_id: int, guild: discord.Guild, placeholder: str, callback, settings_message: discord.Message):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_channel_selected(self, interaction: discord.Interaction):
        if not self.channel_select.values:
            await interaction.response.send_message("<:disapprove:1517452151012589662> No channel was selected.", ephemeral=True)
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


class YesNoView(discord.ui.View):
    def __init__(self, user_id: int, yes_callback, no_callback):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
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


class BoardCountPromptView(discord.ui.View):
    def __init__(self, user_id: int, channel: discord.abc.GuildChannel, emoji: str, settings_message: discord.Message, callback):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Required count must be a number.", ephemeral=True)
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


class AutoReplyChoiceView(discord.ui.View):
    def __init__(self, user_id: int, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
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


class ChannelEditChoiceView(discord.ui.View):
    def __init__(self, user_id: int, setting_name: str, on_add, on_remove, settings_message: discord.Message):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
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


class EconomyChoiceView(discord.ui.View):
    def __init__(self, user_id: int, on_add, on_remove, setting_name: str, settings_message: discord.Message | None = None):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.setting_name = setting_name
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id=f"economy_add_{setting_name}")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id=f"economy_remove_{setting_name}")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id=f"economy_cancel_{setting_name}")
        self.add_button.callback = self.add_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
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


def validate_role_selection(interaction: discord.Interaction, role: discord.Role | None, role_label: str) -> str | None:
    if role is None:
        return None
    if not guild_owner_bypasses_role_checks(interaction) and interaction.user.top_role <= role:
        return f"<:disapprove:1517452151012589662> You cannot configure a {role_label} that is equal or higher than your highest role."
    if interaction.guild.me.top_role <= role:
        return "<:disapprove:1517452151012589662> I cannot assign that role because it is equal or higher than my highest role."
    return None


class EconomyRoleSelectionView(discord.ui.View):
    def __init__(self, user_id: int, guild: discord.Guild, prompt: str, item_name: str, settings_message: discord.Message | None, callback, is_temp_role: bool):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_role_selected(self, interaction: discord.Interaction):
        role_id = int(self.role_select.values[0])
        await self.callback(interaction, role_id, self.item_name, self.settings_message, self.is_temp_role)

    async def on_no_selected(self, interaction: discord.Interaction):
        await self.callback(interaction, None, self.item_name, self.settings_message, self.is_temp_role)


class EconomySettingsView(LayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color):
        super().__init__(timeout=180)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
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
        await interaction.response.send_message(
            "What would you like to do with Shop items?",
            view=EconomyChoiceView(self.user_id, self.open_shop_add, self.open_shop_remove, "shop", settings_message),
            ephemeral=True,
        )

    async def open_shop_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyShopAddModal(self.add_shop_item, self.guild_id, settings_message))

    async def open_shop_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyShopRemoveModal(self.remove_shop_item, self.guild_id, settings_message))

    async def add_shop_item(self, interaction: discord.Interaction, name: str, desc: str, price: int, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild["shop"][normalize_item(name)] = {"desc": desc, "price": price}
        save_data(data)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Shop item **{normalize_item(name)}** saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_shop_item(self, interaction: discord.Interaction, name: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        canonical = find_item_key(guild.get("shop", {}), name)
        if canonical:
            del guild["shop"][canonical]
            save_data(data)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Removed shop item **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> No shop item found for **{name}**.", ephemeral=True)

    async def handle_uses_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.send_message(
            "What would you like to do with Item uses?",
            view=EconomyChoiceView(self.user_id, self.open_uses_add, self.open_uses_remove, "uses", settings_message),
            ephemeral=True,
        )

    async def open_uses_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyUseAddModal(self.add_use_item, self.guild_id, settings_message))

    async def open_uses_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyUseRemoveModal(self.remove_use_item, self.guild_id, settings_message))

    async def add_use_item(self, interaction: discord.Interaction, item: str, money: int, xp: int, message: str, give_item: str | None, give_item_amount: int, settings_message: discord.Message | None):
        item_name = normalize_item(item)
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
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
        await interaction.response.send_message(
            f"<:approve:1517452125687513158> Use effect for **{item_name}** saved. Choose a role to grant when it is used. Press No to skip.",
            view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a role", item_name, settings_message, self.handle_use_role_selection, False),
            ephemeral=True,
        )
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def handle_use_role_selection(self, interaction: discord.Interaction, role_id: int | None, item_name: str, settings_message: discord.Message | None, is_temp_role: bool):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        effect = guild.get("item_uses", {}).get(item_name)
        if effect is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> That item use entry no longer exists.", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id) if interaction.guild and role_id else None
        if role_id and role is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> The selected role is no longer available.", ephemeral=True)
            return

        role_error = validate_role_selection(interaction, role, "temporary role reward" if is_temp_role else "role reward")
        if role_error:
            await interaction.response.send_message(role_error, ephemeral=True)
            return

        if is_temp_role:
            effect["temp_role_id"] = role_id
            save_data(data)
            if role_id is None:
                await interaction.response.send_message(
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
            await interaction.response.send_message(
                f"<:approve:1517452125687513158> Role setup skipped for **{item_name}**. Choose a temporary role next, or press No to skip.",
                view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a temporary role", item_name, settings_message, self.handle_use_role_selection, True),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> That item use entry no longer exists.", ephemeral=True)
            return

        effect["duration"] = max(0, days * 86400 + hours * 3600 + minutes * 60 + seconds)
        save_data(data)
        await interaction.response.send_message(
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
            await interaction.response.send_message(f"<:trash:1517497581058527404> Removed use effect for **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> No use effect found for **{item}**.", ephemeral=True)

    async def handle_prices_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.send_message(
            "What would you like to do with Item prices?",
            view=EconomyChoiceView(self.user_id, self.open_prices_add, self.open_prices_remove, "prices", settings_message),
            ephemeral=True,
        )

    async def open_prices_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyPriceSetModal(self.set_price_item, self.guild_id, settings_message))

    async def open_prices_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyPriceRemoveModal(self.remove_price_item, self.guild_id, settings_message))

    async def set_price_item(self, interaction: discord.Interaction, item: str, value: int, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        guild["item_values"][normalize_item(item)] = value
        save_data(data)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Price for **{normalize_item(item)}** saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_price_item(self, interaction: discord.Interaction, item: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        canonical = find_item_key(guild.get("item_values", {}), item)
        if canonical:
            del guild["item_values"][canonical]
            save_data(data)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Removed price for **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> No price found for **{item}**.", ephemeral=True)

    async def handle_crafts_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.send_message(
            "What would you like to do with Crafting recipes?",
            view=EconomyChoiceView(self.user_id, self.open_craft_add, self.open_craft_remove, "crafts", settings_message),
            ephemeral=True,
        )

    async def open_craft_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyCraftAddModal(self.add_craft_item, self.guild_id, settings_message))

    async def open_craft_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(EconomyCraftRemoveModal(self.remove_craft_item, self.guild_id, settings_message))

    async def add_craft_item(self, interaction: discord.Interaction, item: str, req1_name: str, req1_count: int, req2_name: str | None, req2_count: int, delay: int, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        recipe = {"reqs": {normalize_item(req1_name): req1_count}, "delay": delay}
        if req2_name:
            recipe["reqs"][normalize_item(req2_name)] = req2_count
        guild["recipes"][normalize_item(item)] = recipe
        save_data(data)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Craft recipe for **{normalize_item(item)}** saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_craft_item(self, interaction: discord.Interaction, item: str, settings_message: discord.Message | None):
        data = load_data()
        guild = get_guild_data(data, self.guild_id)
        canonical = find_item_key(guild.get("recipes", {}), item)
        if canonical:
            del guild["recipes"][canonical]
            save_data(data)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Removed craft recipe for **{canonical}**.", ephemeral=True)
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> No craft recipe found for **{item}**.", ephemeral=True)


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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Days, hours, minutes, and seconds must be numbers.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Price must be a number.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Money/XP must be numbers.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Price must be a number.", ephemeral=True)
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
        self.req1_input = TextInput(label="Requirement 1 (Item:Amount)", placeholder="Ingredient:amount", required=True, max_length=100)
        self.req2_input = TextInput(label="Requirement 2 (Item:Amount)", placeholder="Optional ingredient:amount", required=False, max_length=100)
        self.delay_input = TextInput(label="Delay seconds", placeholder="0", required=True, max_length=10)
        self.add_item(self.item_input)
        self.add_item(self.req1_input)
        self.add_item(self.req2_input)
        self.add_item(self.delay_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            delay = int(self.delay_input.value or 0)
        except ValueError:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Delay must be a number.", ephemeral=True)
            return

        req1_name, req1_count = parse_item_amount_entry(self.req1_input.value, default_amount=1)
        req2_name, req2_count = (None, 1)
        if self.req2_input.value.strip():
            req2_name, req2_count = parse_item_amount_entry(self.req2_input.value, default_amount=1)

        await self.callback(interaction, self.item_input.value.strip(), req1_name, req1_count, req2_name, req2_count, delay, self.settings_message)


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


class LevelRoleSelectionView(discord.ui.View):
    def __init__(self, user_id: int, guild: discord.Guild, prompt: str, level: int, reward_data: dict, settings_message: discord.Message | None, callback, is_temp_role: bool):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Level, duration, money, and XP must be numbers.", ephemeral=True)
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


class LevelSettingsView(LayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color, settings_message: discord.Message | None = None):
        super().__init__(timeout=180)
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

        self.set_button = Button(label="Set reward", style=discord.ButtonStyle.primary, custom_id="level_settings_set")
        self.set_button.callback = self.handle_set
        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="level_settings_back")
        self.back_button.callback = self.handle_back

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **Level settings**"),
            TextDisplay("Configure level-based rewards below."),
            Separator(),
            Section("<:box:1517581439552585759> Current rewards\n" + ("\n".join(summary_lines) if summary_lines else "None"), accessory=self.set_button),
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View):
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

    async def handle_reward_submit(self, interaction: discord.Interaction, reward_data: dict, level: int, settings_message: discord.Message | None):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This can only be used in a server.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"<:approve:1517452125687513158> Level {level} reward details saved. Choose a role to grant when this level is reached. Press No to skip.",
            view=LevelRoleSelectionView(self.user_id, guild, "Choose a role", level, reward_data, settings_message, self.handle_level_role_selection, False),
            ephemeral=True,
        )

    async def handle_level_role_selection(self, interaction: discord.Interaction, reward_data: dict, level: int, settings_message: discord.Message | None, is_temp_role: bool):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This can only be used in a server.", ephemeral=True)
            return

        role_id = reward_data.get("temp_role_id" if is_temp_role else "role_id")
        role = guild.get_role(role_id) if role_id else None
        if role_id and role is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> The selected role is no longer available.", ephemeral=True)
            return

        role_error = validate_role_selection(interaction, role, "temporary role reward" if is_temp_role else "role reward")
        if role_error:
            await interaction.response.send_message(role_error, ephemeral=True)
            return

        if is_temp_role:
            save_level_reward_data(str(guild.id), level, reward_data)
            await interaction.response.send_message(f"<:approve:1517452125687513158> Level {level} reward saved.", ephemeral=True)
            await self.refresh_settings_message(interaction, LevelSettingsView(self.user_id, self.guild_id, self.color, settings_message=self.settings_message))
            return

        if role_id is None:
            await interaction.response.send_message(
                f"<:approve:1517452125687513158> Role setup skipped for level {level}. Choose a temporary role next, or press No to skip.",
                view=LevelRoleSelectionView(self.user_id, guild, "Choose a temporary role", level, reward_data, settings_message, self.handle_level_role_selection, True),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"<:approve:1517452125687513158> Role saved for level {level}. Choose a temporary role next, or press No to skip.",
            view=LevelRoleSelectionView(self.user_id, guild, "Choose a temporary role", level, reward_data, settings_message, self.handle_level_role_selection, True),
            ephemeral=True,
        )


class AutomodSettingsView(LayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.color = color
        self.build_components()

    def build_components(self):
        self.clear_items()
        automod, _ = get_guild_automod_config(self.guild_id)
        blocked_words = automod.get("blocked_words", [])
        warning_sanctions = automod.get("warning_sanctions", [])
        blocked_summary = "\n".join(f"- {item.get('phrase', '')}{' (regex)' if item.get('use_regex') else ''}" for item in blocked_words[:6]) or "None"
        sanctions_summary = []
        for item in warning_sanctions[:6]:
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
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
        await interaction.response.send_message(
            "What would you like to do with blocked words?",
            view=AutomodWordChoiceView(self.user_id, self.guild_id, self.open_word_add, self.open_word_remove, settings_message),
            ephemeral=True,
        )

    async def open_word_add(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(AutomodWordAddModal(self.add_word_block, self.guild_id, settings_message))

    async def open_word_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None = None):
        await interaction.response.send_modal(AutomodWordRemoveModal(self.remove_word_block, self.guild_id, settings_message))

    async def add_word_block(self, interaction: discord.Interaction, phrase: str, use_regex: bool, warn_on_match: bool, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        automod.setdefault("blocked_words", []).append({"phrase": phrase, "use_regex": use_regex, "warn_on_match": warn_on_match})
        save_guild_data(data)
        await sync_guild_word_block_rule(self.guild_id)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Blocked phrase saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_word_block(self, interaction: discord.Interaction, phrase: str, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        blocked_words = automod.get("blocked_words", [])
        filtered = [item for item in blocked_words if str(item.get("phrase", "")).strip().lower() != phrase.strip().lower()]
        if len(filtered) != len(blocked_words):
            automod["blocked_words"] = filtered
            save_guild_data(data)
            await sync_guild_word_block_rule(self.guild_id)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Blocked phrase removed.", ephemeral=True)
            await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.send_message("<:disapprove:1517452151012589662> No matching blocked phrase was found.", ephemeral=True)

    async def handle_sanctions_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except Exception:
                settings_message = None
        await interaction.response.send_message(
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
        await interaction.response.send_message(f"<:approve:1517452125687513158> Warning sanction saved.", ephemeral=True)
        await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color), settings_message)

    async def remove_sanction_rule(self, interaction: discord.Interaction, warns: int, settings_message: discord.Message | None):
        automod, data = get_guild_automod_config(self.guild_id)
        sanctions = automod.get("warning_sanctions", [])
        filtered = [item for item in sanctions if int(item.get("warns", 0)) != warns]
        if len(filtered) != len(sanctions):
            automod["warning_sanctions"] = filtered
            save_guild_data(data)
            await interaction.response.send_message(f"<:trash:1517497581058527404> Warning sanction removed.", ephemeral=True)
            await self.refresh_settings_message(interaction, AutomodSettingsView(self.user_id, self.guild_id, self.color), settings_message)
        else:
            await interaction.response.send_message("<:disapprove:1517452151012589662> No matching warning sanction was found.", ephemeral=True)

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


class AutomodWordChoiceView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: str, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
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
        self.phrase_input = TextInput(label="Word or phrase", placeholder="Enter a word or phrase", required=True, max_length=200)
        self.regex_input = TextInput(label="Regex? (true/false)", placeholder="false", required=True, max_length=5)
        self.warn_input = TextInput(label="Warn on match? (true/false)", placeholder="false", required=True, max_length=5)
        self.add_item(self.phrase_input)
        self.add_item(self.regex_input)
        self.add_item(self.warn_input)

    async def on_submit(self, interaction: discord.Interaction):
        def parse_bool(value: str) -> bool:
            return value.strip().lower() in {"true", "yes", "y", "1"}

        use_regex = parse_bool(self.regex_input.value)
        warn_on_match = parse_bool(self.warn_input.value)
        await self.callback(interaction, self.phrase_input.value.strip(), use_regex, warn_on_match, self.settings_message)


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


class AutomodSanctionChoiceView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: str, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=120)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Warn count must be a number.", ephemeral=True)
            return

        action = self.action_input.value.strip().lower()
        if action not in {"timeout", "kick", "ban"}:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Action must be timeout, kick, or ban.", ephemeral=True)
            return

        duration_text = self.duration_input.value.strip() if self.duration_input.value else ""
        duration_seconds = None
        if action == "timeout":
            if not duration_text:
                duration_text = "1d"
            duration_seconds = parse_duration_to_seconds(duration_text)
            if duration_seconds is None or duration_seconds <= 0:
                await interaction.response.send_message("<:disapprove:1517452151012589662> Timeout duration must be a valid value like 1d, 10s, or 50m.", ephemeral=True)
                return
        else:
            duration_seconds = 0
            if duration_text:
                await interaction.response.send_message("<:disapprove:1517452151012589662> Duration is only valid for timeout actions.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Warn count must be a number.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Action must be timeout, kick, or ban.", ephemeral=True)
            return

        duration_text = self.duration_input.value.strip() if self.duration_input.value else ""
        duration_seconds = None
        if action == "timeout":
            if not duration_text:
                duration_text = "1d"
            duration_seconds = parse_duration_to_seconds(duration_text)
            if duration_seconds is None or duration_seconds <= 0:
                await interaction.response.send_message("<:disapprove:1517452151012589662> Timeout duration must be a valid value like 1d, 10s, or 50m.", ephemeral=True)
                return
        else:
            duration_seconds = 0
            if duration_text:
                await interaction.response.send_message("<:disapprove:1517452151012589662> Duration is only valid for timeout actions.", ephemeral=True)
                return

        await self.callback(interaction, self.channel, action, duration_seconds, duration_text, self.settings_message)


class ChannelSettingsView(LayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color, page: int = 1):
        super().__init__(timeout=180)
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
        locked_entries = get_locked_channel_mentions(guild) if guild else []
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
            self.locked_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="channel_locked_edit")

            self.board_button.callback = self.handle_board_edit
            self.counter_button.callback = self.handle_counter_edit
            self.locked_button.callback = self.handle_locked_edit

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
                Section(f"<:chalice:1517579767573123092> Level-up Announce Channel\n{level_channel}", accessory=self.level_button),
                Section(f"<:unlocked:1517574880034558102> Admin Log Channel\n{admin_value}", accessory=self.admin_button),
                Section(f"<:honey:1524116282075512842> Honeypot Channel\n{honeypot_value}", accessory=self.honeypot_button),
            ]
        else:
            board_text = "\n".join(board_entries) if board_entries else "None"
            counter_text = "\n".join(counter_entries) if counter_entries else "None"
            locked_text = "\n".join(locked_entries) if locked_entries else "None"
            container_items += [
                Section(f"<:list:1517497572770451567> Board Channels\n{board_text}", accessory=self.board_button),
                Section(f"<:multi:1518348755261460661> Counter Channels\n{counter_text}", accessory=self.counter_button),
                Section(f"<:locked:1517574877257924809> Locked Channels\n{locked_text}", accessory=self.locked_button),
            ]

        container = Container(*container_items, accent_color=self.color)
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(page_button, self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
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
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("welcome_channel_id"):
            await interaction.response.send_message("Please confirm removal of the welcome channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_welcome, interaction.message), ephemeral=True)
            return
        await interaction.response.send_message(
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
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("goodbye_channel_id"):
            await interaction.response.send_message("Please confirm removal of the goodbye channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_goodbye, interaction.message), ephemeral=True)
            return
        await interaction.response.send_message(
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
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        level_id = get_level_channel_id(self.guild_id)
        if level_id:
            await interaction.response.send_message("Please confirm removal of the level-up announce channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_level_channel, interaction.message), ephemeral=True)
            return
        await interaction.response.send_message(
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
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        admin_ids = get_guild_admin_log_channel_ids(guild)
        if admin_ids:
            channel = guild.get_channel(admin_ids[0])
            if channel:
                await interaction.response.send_message(
                    f"Confirm removing admin logging from {channel.mention}?",
                    view=ConfirmRemoveView(self.user_id, self.confirm_remove_admin_log, interaction.message),
                    ephemeral=True,
                )
                return
        await interaction.response.send_message(
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
        await interaction.response.send_message(
            "What would you like to do with Board Channels?",
            view=ChannelEditChoiceView(self.user_id, "Board Channels", self.open_board_add, self.open_board_remove, interaction.message),
            ephemeral=True,
        )

    async def open_board_add(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_message(
            "Select the board channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select board channel", self.board_channel_selected, settings_message),
            ephemeral=True,
        )

    async def board_channel_selected(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> Unable to continue board configuration.", ephemeral=True)
        prompt = await interaction.channel.send(
            f"{interaction.user.mention}, react to this message with the emoji you want to use for the board. You have 60 seconds.",
        )
        await interaction.response.send_message("React to the channel prompt to choose the board emoji.", ephemeral=True)

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
        await interaction.response.send_message(f"<:approve:1517452125687513158> Board for {emoji} saved to {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def open_board_remove(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_message(
            "Select the board channel to remove:",
            view=ChannelSelectorView(self.user_id, guild, "Select board channel to remove", self.remove_board_channel, settings_message),
            ephemeral=True,
        )

    async def remove_board_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        board_data = load_board_data()
        if self.guild_id not in board_data:
            await interaction.response.send_message("<:disapprove:1517452151012589662> No board channels are configured.", ephemeral=True)
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
            await interaction.response.send_message(f"<:trash:1517497581058527404> Removed board channel {channel.mention}.", ephemeral=True)
            await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)
        else:
            await interaction.response.send_message("<:disapprove:1517452151012589662> That channel is not configured as a board channel.", ephemeral=True)

    async def handle_counter_edit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "What would you like to do with Counter Channels?",
            view=ChannelEditChoiceView(self.user_id, "Counter Channels", self.open_counter_add, self.open_counter_remove, interaction.message),
            ephemeral=True,
        )

    async def open_counter_add(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_message(
            "Select the counter channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select counter channel", self.counter_channel_selected, settings_message),
            ephemeral=True,
        )

    async def counter_channel_selected(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        async def yes_callback(interact: discord.Interaction):
            await self.add_counter_channel(interact, channel, True, settings_message)

        async def no_callback(interact: discord.Interaction):
            await self.add_counter_channel(interact, channel, False, settings_message)

        await interaction.response.send_message(
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
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_message(
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

    async def handle_locked_edit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "What would you like to do with Locked Channels?",
            view=ChannelEditChoiceView(self.user_id, "Locked Channels", self.open_locked_add, self.open_locked_remove, interaction.message),
            ephemeral=True,
        )

    async def handle_honeypot_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("honeypot_channel_id"):
            await interaction.response.send_message("Please confirm removal of the honeypot channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_honeypot, interaction.message), ephemeral=True)
            return
        await interaction.response.send_message(
            "Select the honeypot channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select honeypot channel", self.open_honeypot_sanction, interaction.message),
            ephemeral=True,
        )

    async def open_honeypot_sanction(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        resolved_channel = channel
        if interaction.guild and getattr(channel, "id", None):
            resolved_channel = interaction.guild.get_channel(channel.id) or await interaction.guild.fetch_channel(channel.id)
        if not resolved_channel or getattr(resolved_channel, "type", None) != discord.ChannelType.text:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> Please select a text channel for the honeypot.", ephemeral=True)
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

    async def open_locked_add(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_message(
            "Select the locked channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select locked channel", self.add_locked_channel, settings_message),
            ephemeral=True,
        )

    async def add_locked_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        locked_channels[channel.id] = True
        save_lock_config(locked_channels, admin_log_channels)
        await safe_send(interaction, f"<:approve:1517452125687513158> Locked channel enabled for {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def open_locked_remove(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
        await interaction.response.send_message(
            "Select the locked channel to remove:",
            view=ChannelSelectorView(self.user_id, guild, "Select locked channel to remove", self.remove_locked_channel, settings_message),
            ephemeral=True,
        )

    async def remove_locked_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        if channel.id not in locked_channels:
            await interaction.response.send_message("<:disapprove:1517452151012589662> That channel is not configured as locked.", ephemeral=True)
            return
        locked_channels.pop(channel.id, None)
        save_lock_config(locked_channels, admin_log_channels)
        await interaction.response.send_message(f"<:trash:1517497581058527404> Removed locked channel {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)


@bot.tree.command(name="settings", description="Open a quick settings menu for your personal and guild preferences")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def settings(interaction: discord.Interaction):
    view = SettingsMenuView(
        interaction.user.id,
        interaction.user.display_name,
        get_user_color_value(str(interaction.user.id)),
    )
    await interaction.response.send_message(view=view, ephemeral=True)


@bot.tree.command(name="notes-lists-reminders", description="Manage your notes, checklists, and reminders")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def notes(interaction: discord.Interaction):
    view = NotesMenuView(interaction.user.id)
    await interaction.response.send_message(view=view, ephemeral=True)




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
        super().__init__(timeout=180)
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
            container_items.append(Section("No backups found. Run a backup or wait for the scheduler to create one."))
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This backup panel is only for the original user.", ephemeral=True)
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
        await interaction.response.send_message(f"<:approve:1517452125687513158> Created backup `{backup_path.name}`.", ephemeral=True)
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
            await interaction.response.send_message("Backup list closed.", ephemeral=True)

    async def open_backup_actions(self, interaction: discord.Interaction, backup_file: Path):
        await interaction.response.send_message(
            f"What would you like to do with `{backup_file.name}`?",
            view=BackupActionView(self.user_id, backup_file, self),
            ephemeral=True,
        )


class BackupActionView(discord.ui.View):
    def __init__(self, user_id: int, backup_file: Path, list_view: BackupListView):
        super().__init__(timeout=180)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This password prompt is only for the original user.", ephemeral=True)
            return

        if not OWN_PASSWORD:
            await interaction.response.send_message("<:disapprove:1517452151012589662> OWN_PASSWORD is not configured in .env.", ephemeral=True)
            return

        if self.password_input.value != OWN_PASSWORD:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Incorrect password.", ephemeral=True)
            return

        if self.action == "load":
            await self.perform_load(interaction)
        elif self.action == "delete":
            await self.perform_delete(interaction)
        else:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Unknown action.", ephemeral=True)

    async def perform_load(self, interaction: discord.Interaction):
        if not self.backup_file.exists():
            await interaction.response.send_message("<:disapprove:1517452151012589662> Backup file no longer exists.", ephemeral=True)
            return

        try:
            backup_before_restore = create_backup(BASE_DIR)
            with zipfile.ZipFile(self.backup_file, 'r') as zf:
                zf.extractall(path=BASE_DIR)
            await interaction.response.send_message(
                f"<:approve:1517452125687513158> Loaded backup `{self.backup_file.name}` and created current backup `{backup_before_restore.name}`.",
                ephemeral=True,
            )
            if self.list_view.message:
                await self.list_view.message.edit(view=BackupListView(self.user_id, page=self.list_view.page))
        except Exception as e:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> Failed to load backup: {e}", ephemeral=True)

    async def perform_delete(self, interaction: discord.Interaction):
        if not self.backup_file.exists():
            await interaction.response.send_message("<:disapprove:1517452151012589662> Backup file no longer exists.", ephemeral=True)
            return

        try:
            self.backup_file.unlink()
            await interaction.response.send_message(
                f"<:trash:1517497581058527404> Deleted backup `{self.backup_file.name}`.",
                ephemeral=True,
            )
            if self.list_view.message:
                await self.list_view.message.edit(view=BackupListView(self.user_id, page=self.list_view.page))
        except Exception as e:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> Failed to delete backup: {e}", ephemeral=True)


start_backup_scheduler()

bot.run(TOKEN)
