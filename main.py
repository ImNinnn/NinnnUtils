import subprocess
import asyncio
import ast
import json
import os
import random
from datetime import datetime, timedelta
from collections import Counter
import sys
import yt_dlp
import discord
from discord import TextInput, app_commands, Status
from discord.ext import tasks, commands
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from google import genai
import io
import deep_translator
from deep_translator import GoogleTranslator
import g4f
import base64
from discord.ui import Modal, TextInput




# -------------------------------------------------------------------------------------------------------------
#                                               Configuration
# -------------------------------------------------------------------------------------------------------------




load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
VERSION = os.getenv('BOT_VERSION')
raw_blacklist = os.getenv('SERVER_BLACKLIST', '')
BLACKLISTED_GUILDS = [int(sid.strip()) for sid in raw_blacklist.split(',') if sid.strip().isdigit()]
ACTIVITY_TEXT = os.getenv('ACTIVITY')
SHARD_COUNT = int(os.getenv('SHARD_COUNT', '0'))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'economy.json')
LOVE_FILE = os.path.join(BASE_DIR, 'love.json')
FUN_FILE = os.path.join(BASE_DIR, 'fun.json')
BOARD_FILE = os.path.join(BASE_DIR, 'board.json')
GUILD_FILE = os.path.join(BASE_DIR, 'guild.json')
LOCK_CONFIG_FILE = os.path.join(BASE_DIR, 'lock_config.json')
FFMPEG_PATH = os.path.join(BASE_DIR, "ffmpeg.exe")
LEVEL_FILE = os.path.join(BASE_DIR, 'level.json')
USER_FILE = os.path.join(BASE_DIR, 'user.json')




# -------------------------------------------------------------------------------------------------------------
#                                               Bot Setup
# -------------------------------------------------------------------------------------------------------------




class MyDiscordApp(commands.AutoShardedBot):
    def __init__(self, intents, shard_count: int = 0):
        super().__init__(
            command_prefix="/",
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




# -------------------------------------------------------------------------------------------------------------
#                                               Message Cache
# -------------------------------------------------------------------------------------------------------------




message_cache = []
deleted_cache = []
edited_cache = []
active_minigame_users = set()
server_pauses = {}
all_paused_guilds = set()
reaction_xp_cooldowns = {}




# -------------------------------------------------------------------------------------------------------------
#                                               Data Management
# -------------------------------------------------------------------------------------------------------------




def load_levels():
    if not os.path.exists(LEVEL_FILE):
        return {}
    with open(LEVEL_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_levels(data):
    with open(LEVEL_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def get_xp_needed(level: int) -> int:
    return 100 + (level * 10)


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def load_user_settings():
    if not os.path.exists(USER_FILE):
        return {}
    with open(USER_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_user_settings(data):
    with open(USER_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def get_user_color(user_id: str) -> str:
    settings = load_user_settings()
    return settings.get("users", {}).get(str(user_id), {}).get("color", "white")


def load_love_data():
    if not os.path.exists(LOVE_FILE):
        with open(LOVE_FILE, "w") as f:
            json.dump({}, f)
        return {}
    with open(LOVE_FILE, "r") as f:
        return json.load(f)


def save_love_data(data):
    with open(LOVE_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_fun_data():
    if not os.path.exists(FUN_FILE):
        return {}
    with open(FUN_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_fun_data(data):
    with open(FUN_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def load_board_data():
    if not os.path.exists(BOARD_FILE):
        return {}
    with open(BOARD_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_board_data(data):
    with open(BOARD_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def load_guild_data():
    if not os.path.exists(GUILD_FILE):
        return {}
    with open(GUILD_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_guild_data(data):
    with open(GUILD_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def load_lock_config():
    if not os.path.exists(LOCK_CONFIG_FILE):
        return {}, {}
    with open(LOCK_CONFIG_FILE, 'r') as f:
        try:
            data = json.load(f)
            locked = {int(k): v for k, v in data.get("locked_channels", {}).items()}
            admin = {int(k): v for k, v in data.get("admin_log_channels", {}).items()}
            return locked, admin
        except (json.JSONDecodeError, ValueError):
            return {}, {}


def save_lock_config(locked, admin):
    with open(LOCK_CONFIG_FILE, 'w') as f:
        json.dump({"locked_channels": locked, "admin_log_channels": admin}, f, indent=4)


def get_guild_config(guild_id: str) -> dict:
    data = load_guild_data()
    default_config = {
        "welcome_channel_id": None,
        "goodbye_channel_id": None,
        "ghost_ping_enabled": False,
        "edit_delete_history_enabled": True,
        "counter_channels": {}
    }

    if guild_id not in data:
        data[guild_id] = default_config
    else:
        for key, value in default_config.items():
            if key not in data[guild_id]:
                data[guild_id][key] = value
    save_guild_data(data)
    return data[guild_id], data


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
        return "✅"
    if result == "warn":
        return "⚠️"
    if result == "bad":
        if config.get("reset_on_fail"):
            update_counter_state(guild_id, channel_id, 0, None)
        return "❌"
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


def clean_cache():
    global message_cache, deleted_cache, edited_cache
    now = datetime.now()
    message_cache = [m for m in message_cache if now - m['time'] < timedelta(minutes=120)]
    deleted_cache = [m for m in deleted_cache if now - m['time'] < timedelta(minutes=120)]
    edited_cache = [m for m in edited_cache if now - m['time'] < timedelta(minutes=120)]


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
    formatted_time = message.created_at.strftime("%b %d, %Y - %I:%M %p")
    embed.set_footer(text=f"| {formatted_time}")

    content_text = f"{emoji_str} {current_count} in {message.jump_url}"

    if orig_msg_id in config["tracked_messages"]:
        board_msg_id = int(config["tracked_messages"][orig_msg_id])
        try:
            board_message = await board_channel.fetch_message(board_msg_id)
            if current_count >= config["required_count"]:
                await board_message.edit(content=content_text, embed=embed)
            else:
                await board_message.delete()
                del config["tracked_messages"][orig_msg_id]
                save_board_data(board_data)
        except discord.NotFound:
            del config["tracked_messages"][orig_msg_id]
            save_board_data(board_data)

    elif current_count >= config["required_count"] and not remove_mode:
        new_board_msg = await board_channel.send(content=content_text, embed=embed)
        config["tracked_messages"][orig_msg_id] = str(new_board_msg.id)
        save_board_data(board_data)




# -------------------------------------------------------------------------------------------------------------
#                                               UI Views
# -------------------------------------------------------------------------------------------------------------




class ShopView(discord.ui.View):
    def __init__(self, shop_items, guild_id):
        super().__init__(timeout=None)
        self.shop_items = shop_items
        self.guild_id = guild_id
        for item_name, info in shop_items.items():
            self.add_buy_button(item_name, info)

    def add_buy_button(self, name, info):
        button = discord.ui.Button(
            label=f"Buy {name} (${info['price']})",
            style=discord.ButtonStyle.primary,
            custom_id=f"buy_{name}"
        )

        async def button_callback(interaction: discord.Interaction):
            data = load_data()
            user_data = get_user_data(data, self.guild_id, str(interaction.user.id))
            price = info['price']

            if user_data["balance"] < price:
                await interaction.response.send_message("❌ You can't afford this!", ephemeral=True)
                return

            user_data["balance"] -= price
            inventory_add(user_data["inventory"], name)
            save_data(data)
            await interaction.response.send_message(f"✅ You bought **{name}**!", ephemeral=True)

        button.callback = button_callback
        self.add_item(button)


class DeletedMediaView(discord.ui.View):
    def __init__(self, media_messages, user_who_requested):
        super().__init__(timeout=60)
        self.messages = media_messages
        self.index = 0
        self.requester = user_who_requested
        self.revealed = False
        self.update_button_states()

    def update_button_states(self):
        self.prev_button.disabled = (self.index == 0)
        self.next_button.disabled = (self.index == len(self.messages) - 1)
        if self.revealed:
            self.reveal_button.label = "Hide Media"
            self.reveal_button.style = discord.ButtonStyle.secondary
        else:
            self.reveal_button.label = f"Reveal Media ({self.index + 1}/{len(self.messages)})"
            self.reveal_button.style = discord.ButtonStyle.danger

    def build_media_embed(self):
        msg = self.messages[self.index]
        if self.revealed:
            text_content = msg['content'] if msg['content'] else "No text"
            embed = discord.Embed(
                title=f"🗑️ Media sent by {msg['author'].display_name}",
                description=f"**{msg['author'].display_name}**: {text_content}\n-# Sent at {msg['created_at']}",
                color=discord.Color.red()
            )
            embed.set_image(url=msg['media'])
            return embed
        return None

    async def handle_page_update(self, interaction: discord.Interaction):
        self.update_button_states()
        embed = self.build_media_embed()
        if embed:
            await interaction.response.edit_message(content=None, embed=embed, view=self)
        else:
            await interaction.response.edit_message(content=self.main_text_layout, embed=self.main_embed_layout, view=self)

    @discord.ui.button(label="Reveal Media", style=discord.ButtonStyle.danger)
    async def reveal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.requester:
            await interaction.response.send_message("❌ Only the person who ran the command can reveal media!", ephemeral=True)
            return
        self.revealed = not self.revealed
        await self.handle_page_update(interaction)

    @discord.ui.button(label="Previous media", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.requester:
            await interaction.response.send_message("❌ Only the person who ran the command can flip pages!", ephemeral=True)
            return
        if self.index > 0:
            self.index -= 1
            await self.handle_page_update(interaction)

    @discord.ui.button(label="Next media", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.requester:
            await interaction.response.send_message("❌ Only the person who ran the command can flip pages!", ephemeral=True)
            return
        if self.index < len(self.messages) - 1:
            self.index += 1
            await self.handle_page_update(interaction)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if hasattr(self, 'message'):
                await self.message.edit(view=self)
        except Exception:
            pass




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
            print(f"🤫 Voice channel empty in {member.guild.name}. Starting 30s leave timer...")
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
    bot.loop.create_task(blacklist_startup_cleanup())


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.guild and message.channel.id in locked_channels:
        guild_id = message.guild.id

        for log_id in admin_log_channels:
            log_channel = bot.get_channel(log_id)
            if log_channel and log_channel.guild.id == guild_id:
                try:
                    await log_channel.send(f"**[LOCKED]** `{message.author}`: {message.content}")
                except Exception:
                    pass

        current_pauses = server_pauses.get(guild_id, set())
        if guild_id in all_paused_guilds or message.channel.id in current_pauses:
            return

        dots = "•" * min(max(len(message.content), 1), 200)
        try:
            await message.delete()
            await message.channel.send(f"🔒 {dots}")
        except Exception:
            pass
        return

    global message_cache
    clean_cache()

    media_url = message.attachments[0].url if message.attachments else None
    message_cache.append({
        'id': message.id,
        'channel': message.channel.id,
        'author': message.author,
        'content': message.content,
        'media': media_url,
        'mentions': message.mentions,
        'time': datetime.now(),
        'created_at': datetime.now().strftime("%I:%M %p")
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
                    await message.reply(response)
                    break

        if await handle_counter_message(message):
            return

        await add_xp(message.author, message.guild, random.randint(5, 10))

    await bot.process_commands(message)


@bot.event
async def on_message_delete(message):
    global message_cache, deleted_cache
    clean_cache()

    for msg in message_cache:
        if msg['id'] == message.id:
            deleted_msg = msg.copy()
            deleted_msg['deleted_at'] = datetime.now().strftime("%I:%M %p")

            history_enabled = True
            ghost_enabled = False
            if message.guild:
                guild_config, _ = get_guild_config(str(message.guild.id))
                history_enabled = guild_config.get("edit_delete_history_enabled", True)
                ghost_enabled = guild_config.get("ghost_ping_enabled", False)

            if history_enabled:
                deleted_cache.append(deleted_msg)
            if message.guild and not ghost_enabled:
                break

            if msg['mentions'] and not msg['author'].bot:
                pinged_users = [user for user in msg['mentions'] if user.id != msg['author'].id]
                
                if pinged_users:
                    mentions_str = " ".join([user.mention for user in pinged_users])
                    
                    embed = discord.Embed(
                        title="👻 Ghost Ping Detected!",
                        description=f"{mentions_str}, you were pinged by {msg['author'].mention} but the message was deleted.",
                        color=discord.Color.red()
                    )
                    if msg['content']:
                        embed.add_field(name="📋 Deleted Content:", value=msg['content'], inline=False)
                    
                    embed.set_footer(text=f"Sent at {msg['created_at']}")
                    
                    channel = bot.get_channel(msg['channel'])
                    if channel:
                        await channel.send(embed=embed)
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
                edited_msg['edited_at'] = datetime.now().strftime("%I:%M %p")
                
                edited_cache.append(edited_msg)
            
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
                await channel.send(f"Welcome {member.mention}!", file=welcome_file)
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
            await add_xp(reactor, guild, random.randint(1, 3))
        try:
            channel = guild.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            if message.author and not message.author.bot and message.author.id != payload.user_id:
                await add_xp(message.author, guild, random.randint(3, 5))
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
    formatted_time = datetime.now().strftime("%b %d, %Y - %I:%M %p")
    embed.set_footer(text=f"{formatted_time}")

    content_text = f"{emoji_str} {current_count} in {message.jump_url}"

    if message_id_str in config["tracked_messages"]:
        board_msg_id = int(config["tracked_messages"][message_id_str])
        try:
            board_message = await board_channel.fetch_message(board_msg_id)
            await board_message.edit(content=content_text, embed=embed)
        except discord.NotFound:
            del config["tracked_messages"][message_id_str]
            save_board_data(board_data)
    elif current_count >= config["required_count"]:
        new_board_msg = await board_channel.send(content=content_text, embed=embed)
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
            embed.set_footer(text=f"{datetime.now().strftime('%b %d, %Y - %I:%M %p')}")
            await board_message.edit(content=content_text, embed=embed)
        else:
            await board_message.delete()
            del config["tracked_messages"][message_id_str]
            save_board_data(board_data)
    except discord.NotFound:
        del config["tracked_messages"][message_id_str]
        save_board_data(board_data)




# -------------------------------------------------------------------------------------------------------------
#                                               Error Handling
# -------------------------------------------------------------------------------------------------------------




@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        retry_after = error.retry_after
        if retry_after >= 60:
            minutes = int(retry_after // 60)
            seconds = int(retry_after % 60)
            if seconds > 0:
                message_text = f"⏳ This command is on cooldown. Please wait **{minutes}m {seconds}s** before trying again."
            else:
                message_text = f"⏳ This command is on cooldown. Please wait **{minutes}m** before trying again."
        else:
            retry_after = round(retry_after, 1)
            message_text = f"⏳ This command is on cooldown. Please wait **{retry_after}s** before trying again."
        if interaction.response.is_done():
            await interaction.followup.send(message_text, ephemeral=True)
        else:
            await interaction.response.send_message(message_text, ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions):
        perms = ", ".join(error.missing_permissions)
        await interaction.response.send_message(f"❌ You lack the required permissions to run this: `{perms}`", ephemeral=True)
    else:
        print(f"Ignored exception in command tree: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An unexpected error occurred while executing this command.", ephemeral=True)




# -------------------------------------------------------------------------------------------------------------
#                                               Presence Update Loop
# -------------------------------------------------------------------------------------------------------------




presence_toggle = True

@tasks.loop(seconds=15)
async def update_presence():
    global presence_toggle

    load_dotenv(override=True)
    raw_blacklist = os.getenv('SERVER_BLACKLIST', '')
    BLACKLISTED_GUILDS = [int(sid.strip()) for sid in raw_blacklist.split(',') if sid.strip().isdigit()]

    for guild in bot.guilds:
        if guild.id in BLACKLISTED_GUILDS:
            print(f"🚫 Loop Check: Found blacklisted guild: {guild.name} ({guild.id}). Leaving...")
            try:
                await guild.leave()
            except Exception as e:
                print(f"❌ Failed to leave {guild.name}: {e}")

    load_dotenv(override=True)
    VERSION = os.getenv('BOT_VERSION')
    ACTIVITY_TEXT = os.getenv('ACTIVITY')

    if presence_toggle:
        online_users = sum(
            len([m for m in guild.members if m.status != discord.Status.offline and not m.bot])
            for guild in bot.guilds
        )
        activity_text = f"ver{VERSION} ┃ {online_users} online users"
    else:
        activity_text = f"ver{VERSION} ┃ {ACTIVITY_TEXT}"

    activity = discord.Activity(type=discord.ActivityType.watching, name=activity_text)

    for shard_id, shard in bot.shards.items():
        await bot.change_presence(
            activity=activity,
            status=discord.Status.online,
            shard_id=shard_id,
        )

    presence_toggle = not presence_toggle


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
        print(f"🚫 Joined blacklisted guild: {guild.name} ({guild.id}). Leaving immediately...")
        await guild.leave()


async def blacklist_startup_cleanup():
    await bot.wait_until_ready()
    print("🧹 Running startup blacklist check...")
    print('-------------------------------------')
    for guild in bot.guilds:
        if guild.id in BLACKLISTED_GUILDS:
            print(f"🧹 Found blacklisted guild on startup: {guild.name} ({guild.id}). Leaving...")
            try:
                await guild.leave()
            except Exception as e:
                print(f"❌ Failed to leave {guild.name}: {e}")




# -------------------------------------------------------------------------------------------------------------
#                                               User Level Commands
# -------------------------------------------------------------------------------------------------------------




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
            title_text = f"🔒 {encoding_type} Encoding Complete"
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
            title_text = f"🔓 {encoding_type} Decoding Complete"
            field_name = "Decoded Plain Text Result:"
            color_choice = discord.Color.green()

        if len(result) > 1000:
            result = result[:950] + "\n\n*(Truncated due to size limits...)*"

        embed = discord.Embed(title=title_text, color=color_choice)
        embed.add_field(name="Input:", value=f"`{text}`", inline=False)
        embed.add_field(name=field_name, value=f"`{result}`", inline=False)
        embed.set_footer(text=f"Processed for {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)
        print(f"🔑 Cipher Log: \"{interaction.user.name}\" performed {action} using {encoding_type}.")

    except Exception as e:
        await interaction.response.send_message(
            f"❌ Operation failed. Please check that your input perfectly matches the formatting for {encoding_type}! Error: {e}",
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
        print(f"🌐 translation log : \"{interaction.user.name}\" translated \"{text}\" from {from_language} to \"{translated_text}\" in {to_language}")
    except Exception as e:
        await interaction.followup.send(f"❌ Translation failed. Please ensure you used valid ISO language codes! Error: {e}", ephemeral=True)


@bot.tree.command(name="voice-play", description="Connect to your voice channel and play a YouTube audio link")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.describe(youtube_url="The YouTube video link (e.g., https://www.youtube.com/watch?v=...)")
@app_commands.checks.cooldown(1, 30.0, key=lambda i: i.guild_id)
async def voice_play(interaction: discord.Interaction, youtube_url: str):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ You must be in a voice channel to use this command!", ephemeral=True)
        return

    await interaction.response.defer()
    voice_channel = interaction.user.voice.channel

    try:
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            stream_url = info['url']
            video_title = info.get('title', 'Unknown Title')

        voice_client = interaction.guild.voice_client
        if voice_client is None:
            voice_client = await voice_channel.connect()
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        if voice_client.is_playing():
            voice_client.stop()

        audio_source = discord.FFmpegPCMAudio(stream_url, executable=FFMPEG_PATH, **FFMPEG_OPTIONS)
        voice_client.play(audio_source, after=lambda e: print(f"Playback ended. Error: {e}") if e else None)
        await interaction.followup.send(f"🎵 Now playing: **{video_title}** in {voice_channel.mention}!")

    except Exception as e:
        await interaction.followup.send(f"❌ Failed to play audio. Error: {e}")


@bot.tree.command(name="voice-leave", description="Disconnect the bot from the voice channel")
@app_commands.allowed_installs(guilds=True, users=False)
async def voice_leave(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client:
        await voice_client.disconnect()
        await interaction.response.send_message("👋 Disconnected from the voice channel.")
    else:
        await interaction.response.send_message("❌ I'm not connected to a voice channel!", ephemeral=True)


@bot.tree.command(name="version", description="Display the bot's version")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def ver(interaction: discord.Interaction):
    VERSION = os.getenv('BOT_VERSION')
    ACTIVITY_TEXT = os.getenv('ACTIVITY')
    await interaction.response.send_message(f"⚙️ Current version: {VERSION} | {ACTIVITY_TEXT}")


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
    await interaction.response.send_message(f"🔢 Your random number between **{low}** and **{high}** is: **{result}**")


@bot.tree.command(name="serverinfo", description="Display detailed information about this server")
@app_commands.allowed_installs(guilds=True, users=False)
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    created_at = guild.created_at.strftime("%m/%d/%Y %H:%M")
    joined_at = interaction.user.joined_at.strftime("%m/%d/%Y %H:%M") if interaction.user.joined_at else "Unknown"
    total_count = guild.member_count
    bot_count = len([m for m in guild.members if m.bot])
    human_count = total_count - bot_count

    embed = discord.Embed(title=f"Information for {guild.name}", color=discord.Color.blue())
    embed.add_field(name="👤 Server Owner", value=f"{guild.owner.mention}", inline=True)
    embed.add_field(name="📆 Created At", value=created_at, inline=True)
    embed.add_field(name="📥 Joined At (user)", value=joined_at, inline=True)
    vanity = guild.vanity_url_code if guild.vanity_url_code else "-"
    embed.add_field(name="🔗 Vanity Link", value=vanity, inline=True)
    embed.add_field(name="🌍 Preferred Locale", value=f"{guild.preferred_locale}", inline=True)
    embed.add_field(name="🛡️ Verification Level", value=str(guild.verification_level).capitalize(), inline=True)
    boost_info = f"{guild.premium_subscription_count} (Level {guild.premium_tier})"
    embed.add_field(name="💎 Server Boosts", value=boost_info, inline=True)
    embed.add_field(name="📂 Channels", value=f"{len(guild.channels)}", inline=True)
    embed.add_field(name="📜 Roles", value=f"{len(guild.roles)}", inline=True)
    embed.add_field(name="\n👥 Members", value=" ", inline=False)
    embed.add_field(name="😄 Real Accounts", value=str(human_count), inline=True)
    embed.add_field(name="🤖 Bots", value=str(bot_count), inline=True)
    embed.add_field(name="🌠 Total", value=str(total_count), inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
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
        app_commands.Choice(name="✨ Random Color", value="random")
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
    bar = "🟥" * filled + "⬛" * (10 - filled)
    embed = discord.Embed(title="Love Compatibility ❤️", color=discord.Color.red())
    embed.add_field(name="Match", value=f"{item1} & {item2}", inline=False)
    embed.add_field(name="Compatibility", value=f"**{score}%**\n{bar}", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ping", description="Check the bot's latency to Discord")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! Latency is **{latency}ms**")


@bot.tree.command(name="stats", description="Show bot statistics and status")
@app_commands.allowed_installs(guilds=True, users=True)
async def stats(interaction: discord.Interaction):
    load_dotenv(override=True)
    VERSION = os.getenv('BOT_VERSION')
    ACTIVITY_TEXT = os.getenv('ACTIVITY')
    total_members = sum(guild.member_count for guild in bot.guilds)
    total_guilds = len(bot.guilds)
    embed = discord.Embed(
        title="⚙️ Bot Statistics",
        color=discord.Color.gold(),
        description="Current status and technical details of the bot."
    )
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else bot.user.default_avatar.url)
    embed.add_field(name="🌐 Servers", value=str(total_guilds), inline=True)
    embed.add_field(name="👥 Total Users", value=str(total_members), inline=True)
    embed.add_field(name="⏳ Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.add_field(name="🐍 Library", value=f"discord.py {discord.__version__}", inline=True)
    embed.add_field(name="⚙️ Version", value=f"{VERSION} | {ACTIVITY_TEXT}", inline=True)
    guild_shard_id = interaction.guild.shard_id if interaction.guild else 0
    total_shards = len(bot.shards) or 1
    shard_info = f"Shard id: {guild_shard_id} | total: {total_shards}"
    embed.add_field(name="🔮 Shard Info", value=shard_info, inline=True)
    embed.add_field(name="👑 Bot owner", value="-ImNinnn- (imninnn.)", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="slot-classic", description="Spin the slot machine!")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def slot(interaction: discord.Interaction):
    emojis = ['🍒', '🍎', '🍇', '💎', '🔔', '🍋']
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
    await interaction.response.send_message(f"🪙 The coin landed on: **{result}**!")


@bot.tree.command(name="avatar", description="Get the profile picture of a user")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(user="The user to get the avatar from")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user.name}'s Avatar", color=discord.Color.blue())
    embed.set_image(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="banner", description="Get the profile banner of a user")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(user="The user to get the banner from")
async def banner(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    full_user = await bot.fetch_user(user.id)
    if full_user.banner:
        embed = discord.Embed(title=f"{user.name}'s Banner", color=discord.Color.blue())
        embed.set_image(url=full_user.banner.url)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"{user.name} does not have a banner.", ephemeral=True)


@bot.tree.command(name="emoji", description="Get the image for a custom emoji")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(emoji="The custom emoji to get the image from")
async def emoji(interaction: discord.Interaction, emoji: str):
    if not emoji:
        return await interaction.response.send_message("❌ Please provide a valid custom emoji.", ephemeral=True)
    try:
        emoji_obj = discord.PartialEmoji.from_str(emoji)
    except Exception:
        return await interaction.response.send_message("❌ Please provide a valid custom emoji.", ephemeral=True)
    if not emoji_obj.id:
        return await interaction.response.send_message("❌ Please provide a valid custom emoji.", ephemeral=True)
    embed = discord.Embed(title=f"Emoji: {emoji_obj.name}", color=discord.Color.blue())
    embed.set_image(url=emoji_obj.url)
    await interaction.response.send_message(embed=embed)




# -------------------------------------------------------------------------------------------------------------
#                                               Admin Commands
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="adm-voice-move", description="Move everyone in your current voice channel to another voice channel")
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
        await interaction.response.send_message("❌ You must be connected to a voice channel to use this command.", ephemeral=True)
        return

    source_channel = member.voice.channel
    if source_channel.id == channel.id:
        await interaction.response.send_message("✅ You are already in the target voice channel.", ephemeral=True)
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


@bot.tree.command(name="adm-rename", description="Rename a user or reset their nickname")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_nicknames=True)
@app_commands.describe(
    user="The member you want to rename",
    name="The new nickname (leave empty to reset to original name)"
)
async def rename(interaction: discord.Interaction, user: discord.Member, name: str = None):
    if interaction.guild.me.top_role <= user.top_role:
        await interaction.response.send_message("❌ I cannot rename this user. Their role is higher than or equal to mine!", ephemeral=True)
        return
    try:
        old_name = user.display_name
        await user.edit(nick=name)
        if name:
            await interaction.response.send_message(f"✅ Changed **{old_name}**'s nickname to **{name}**.")
        else:
            await interaction.response.send_message(f"✅ Reset **{old_name}**'s nickname to their original username.")
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have the 'Manage Nicknames' permission or the user is the Server Owner.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)


@bot.tree.command(name="adm-purge-nuke", description="Fully clear a channel")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_channels=True)
async def nuke(interaction: discord.Interaction, archive: bool = False):
    try:
        channel = await interaction.guild.fetch_channel(interaction.channel_id)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I cannot 'see' this channel. Please check my permissions in this specific channel's settings.", ephemeral=True)
        return

    GIF_URL = "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExN2x1ZW82ZGdlZzV1MTFzNGF6ajJzZ3Bmc3I2MDlxaXp0cWpkcTY4YyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/fXhYwggfsp3yHBsdlr/giphy.gif"

    await interaction.response.send_message("💣 Target locked. Nuking...", ephemeral=False)
    new_channel = await channel.clone(reason=f"Nuke by {interaction.user}")
    await new_channel.edit(position=channel.position)

    embed = discord.Embed(
        title="☢️ Channel Nuked",
        description=f"This is {interaction.user.mention}'s fault, THEY DID THIS",
        color=discord.Color.red()
    )
    embed.set_image(url=GIF_URL)
    await new_channel.send(embed=embed)

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
        await new_channel.send("⚠️ **Warning:** I couldn't delete or hide the old channel. Check if my role is high enough!")
    except Exception as e:
        print(f"Error during nuke cleanup: {e}")


@bot.tree.command(name="adm-purge", description="Mass delete messages from the channel")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_messages=True)
@app_commands.describe(
    amount="Number of messages to delete",
    user="Optional: Only delete messages from this specific user"
)
async def purge(interaction: discord.Interaction, amount: int, user: discord.Member = None):
    if amount <= 0:
        await interaction.response.send_message("❌ Please specify a number greater than 0.", ephemeral=True)
        return
    if amount > 100:
        await interaction.response.send_message("⚠️ For safety, you can only purge up to 100 messages at a time.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    def is_user(m):
        return m.author == user if user else True

    try:
        deleted = await interaction.channel.purge(limit=amount, check=is_user, before=interaction.created_at)
        user_str = f" from {user.mention}" if user else ""
        await interaction.followup.send(f"💣 Successfully deleted **{len(deleted)}** messages{user_str}.", ephemeral=False)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to purge messages. Error: {e}", ephemeral=True)


@bot.tree.command(name="adm-timeout", description="Timeout a member for a specific duration")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(moderate_members=True)
@app_commands.describe(
    member="The member to timeout",
    days="Number of days",
    hours="Number of hours",
    minutes="Number of minutes",
    seconds="Number of seconds",
    reason="Why is this user being timed out?"
)
async def timeout(interaction: discord.Interaction, member: discord.Member, days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0, reason: str = "No reason provided"):
    duration = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    if duration.total_seconds() <= 0:
        await interaction.response.send_message("❌ You must specify a duration greater than 0!", ephemeral=True)
        return
    if duration.total_seconds() > 2419200:
        await interaction.response.send_message("❌ Timeout cannot exceed 28 days.", ephemeral=True)
        return

    if interaction.user != member and member.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ You cannot timeout someone with an equal or higher role than yours.", ephemeral=True)
        return

    time_str = f"{days}d {hours}h {minutes}m {seconds}s"
    try:
        dm_embed = discord.Embed(
            title="⏳ You have been timed out",
            description=f"**Server:** {interaction.guild.name}\n**Duration:** {time_str}\n**Reason:** {reason}",
            color=discord.Color.orange()
        )
        await member.send(embed=dm_embed)
    except discord.Forbidden:
        pass

    try:
        await member.timeout(duration, reason=reason)
        confirm_embed = discord.Embed(
            title="✅ User Timed Out",
            description=f"**{member.mention}** has been timed out for {time_str}.",
            color=discord.Color.green()
        )
        confirm_embed.add_field(name="Reason", value=reason)
        await interaction.response.send_message(embed=confirm_embed)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to timeout this user (Hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)




# -------------------------------------------------------------------------------------------------------------
#                                               Deleted Edited / Ghost Pings
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="toggle-ghost-pings", description="Enable or disable ghost ping notifications in this guild")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def ghost_toggle(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    guild_config, data = get_guild_config(guild_id)
    
    current_state = guild_config.get("ghost_ping_enabled", False)
    new_state = not current_state
    guild_config["ghost_ping_enabled"] = new_state
    
    save_guild_data(data)
    
    status_text = "✅ **Enabled**" if new_state else "❌ **Disabled**"
    embed = discord.Embed(
        title="👻 Ghost Ping Notifications",
        description=f"Ghost ping notifications are now {status_text}",
        color=discord.Color.green() if new_state else discord.Color.red()
    )
    embed.set_footer(text="When enabled, the bot will notify users if someone pings them and then deletes the message (ghost ping).")
    await interaction.response.send_message(embed=embed, ephemeral=False)
    print(f"👻 Ghost ping notifications {'enabled' if new_state else 'disabled'} in {interaction.guild.name}")


@bot.tree.command(name="toggle-history", description="Enable or disable /edited and /deleted history in this guild")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def history_toggle(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    guild_config, data = get_guild_config(guild_id)

    current_state = guild_config.get("edit_delete_history_enabled", True)
    new_state = not current_state
    guild_config["edit_delete_history_enabled"] = new_state
    save_guild_data(data)

    status_text = "✅ **Enabled**" if new_state else "❌ **Disabled**"
    embed = discord.Embed(
        title="🗄️ Edit/Delete History",
        description=f"Edited and deleted message history is now {status_text} for this server.",
        color=discord.Color.green() if new_state else discord.Color.red()
    )
    embed.set_footer(text="When disabled, /edited and /deleted commands will not show history and deleted/edited events will not be saved.")
    await interaction.response.send_message(embed=embed, ephemeral=False)
    print(f"🗄️ Edit/Delete history {'enabled' if new_state else 'disabled'} in {interaction.guild.name}")


@bot.tree.command(name="deleted", description="View recently deleted messages and media")
@app_commands.allowed_installs(guilds=True, users=False)
async def deleted(interaction: discord.Interaction, user: discord.Member = None):
    clean_cache()
    guild_config, _ = get_guild_config(str(interaction.guild.id))
    if not guild_config.get("edit_delete_history_enabled", True):
        await interaction.response.send_message("❌ Deleted message history is disabled for this server.")
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
        media_indicator = "🖼️ " if m['media'] else ""
        if m['media']:
            media_only_messages.append(m)
        content_text = m['content'] if m['content'] else "*[Media or Embed]*"
        description_lines.append(f"{media_indicator}**{m['author'].display_name}**: {content_text}\n-# Sent at {m['created_at']}")

    full_description = "\n\n".join(description_lines)
    main_embed = discord.Embed(
        title="🗑️ Recent deleted messages:",
        description=full_description,
        color=discord.Color.red()
    )

    if media_only_messages:
        media_only_messages.sort(key=lambda x: x['time'], reverse=True)
        view = DeletedMediaView(media_only_messages, interaction.user)
        view.main_text_layout = "Recent deleted messages:"
        view.main_embed_layout = main_embed
        await interaction.response.send_message(embed=main_embed, view=view)
        view.message = await interaction.original_response()
    else:
        await interaction.response.send_message(embed=main_embed)


@bot.tree.command(name="edited", description="Show recently edited messages in this channel")
@app_commands.describe(user="Optional: Only show edited messages from a specific user")
@app_commands.allowed_installs(guilds=True, users=False)
async def edited_command(interaction: discord.Interaction, user: discord.Member = None):
    global edited_cache
    clean_cache()
    guild_config, _ = get_guild_config(str(interaction.guild.id))
    if not guild_config.get("edit_delete_history_enabled", True):
        await interaction.response.send_message("❌ Edited message history is disabled for this server.")
        return

    channel_edited = [m for m in edited_cache if m['channel'] == interaction.channel_id]

    if user:
        channel_edited = [m for m in channel_edited if m['author_id'] == user.id]

    if not channel_edited:
        await interaction.response.send_message("No messages have been edited in this channel recently.")
        return

    text_layout = ""
    for msg in channel_edited[:7]:
        text_layout += f"**{msg['author'].display_name}**: ~~{msg['old_content']}~~ ➔ {msg['new_content']}\n-# Edited at {msg['edited_at']} | [Jump to Message]({msg['jump_url']})\n\n"

    title_text = "📝 Recently Edited Messages"

    embed_layout = discord.Embed(
        title=title_text,
        description=text_layout,
        color=discord.Color.orange()
    )

    await interaction.response.send_message(embed=embed_layout)


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


@bot.tree.command(name="adm-forget", description="Clear edited and deleted history of a chosen user")
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
#                                               Counter And Reply Commands
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="counter-channel-set", description="Enable counting in a channel and optionally reset on fail")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    channel="The text channel where counting will happen",
    reset_when_fail="If enabled, the current counter resets when someone fails"
)
async def counter_channel_set(interaction: discord.Interaction, channel: discord.TextChannel, reset_when_fail: bool = False):
    set_counter_channel(str(interaction.guild.id), channel.id, reset_when_fail)
    status_text = "resets on fail" if reset_when_fail else "does not reset on fail"
    await interaction.response.send_message(f"✅ Counter enabled in {channel.mention} and {status_text}.", ephemeral=False)


@bot.tree.command(name="counter-del", description="Disable counting in a channel")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    channel="The channel where counting should be disabled"
)
async def counter_del(interaction: discord.Interaction, channel: discord.TextChannel):
    removed = remove_counter_channel(str(interaction.guild.id), channel.id)
    if removed:
        await interaction.response.send_message(f"✅ Counter disabled in {channel.mention}.", ephemeral=False)
    else:
        await interaction.response.send_message(f"⚠️ That channel does not have an active counter.", ephemeral=True)


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
        await interaction.response.send_message(f"✅ Counter in {channel.mention} is now set to {value}.", ephemeral=False)
    else:
        await interaction.response.send_message(f"⚠️ That channel does not have an active counter.", ephemeral=True)


@bot.tree.command(name="auto-reply", description="Add a trigger word and random responses for this server")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    word="The word that triggers the bot",
    reply1="Mandatory first response",
    reply2="Optional second response",
    reply3="Optional third response",
    reply4="Optional fourth response"
)
async def auto_reply(interaction: discord.Interaction, word: str, reply1: str, reply2: str = None, reply3: str = None, reply4: str = None):
    guild_id = str(interaction.guild.id)
    trigger_word = word.lower()
    replies = [r for r in [reply1, reply2, reply3, reply4] if r is not None]
    fun_data = load_fun_data()
    if guild_id not in fun_data:
        fun_data[guild_id] = {}
    fun_data[guild_id][trigger_word] = replies
    save_fun_data(fun_data)
    embed = discord.Embed(
        title="✨ Fun Reply Added!",
        description=f"Whenever someone says **{word}** in this server, I will randomly reply with one of these:",
        color=discord.Color.purple()
    )
    for i, r in enumerate(replies, 1):
        embed.add_field(name=f"Reply {i}", value=r, inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="auto-reply-clear", description="Remove a trigger word from this server's fun system")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(word="The trigger word you want to delete")
async def auto_reply_clear(interaction: discord.Interaction, word: str):
    guild_id = str(interaction.guild.id)
    trigger_word = word.lower()
    fun_data = load_fun_data()
    if guild_id in fun_data and trigger_word in fun_data[guild_id]:
        del fun_data[guild_id][trigger_word]
        if not fun_data[guild_id]:
            del fun_data[guild_id]
        save_fun_data(fun_data)
        embed = discord.Embed(
            title="🗑️ Trigger Cleared",
            description=f"Successfully removed the word **{word}** from this server's auto-reply system.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"❌ '{word}' isn't registered as a fun reply trigger in this server.", ephemeral=True)




# -------------------------------------------------------------------------------------------------------------
#                                               Board Commands
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="board-add", description="Set up a reaction board for an emoji")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    emoji="The emoji to watch for (standard or custom)",
    required_count="Number of reactions needed to post to the board",
    channel="The channel where board messages will be sent"
)
async def board_add(interaction: discord.Interaction, emoji: str, required_count: int, channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    board_data = load_board_data()
    if guild_id not in board_data:
        board_data[guild_id] = {}
    board_data[guild_id][emoji] = {
        "channel_id": channel.id,
        "required_count": required_count,
        "tracked_messages": {}
    }
    save_board_data(board_data)
    embed = discord.Embed(
        title="📋 Board Configured!",
        description=f"When a message gets {required_count} {emoji} reactions, it will be sent to {channel.mention}.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="board-del", description="Delete a reaction board configuration")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(emoji="The emoji board you want to remove")
async def board_del(interaction: discord.Interaction, emoji: str):
    guild_id = str(interaction.guild.id)
    board_data = load_board_data()
    if guild_id in board_data and emoji in board_data[guild_id]:
        del board_data[guild_id][emoji]
        if not board_data[guild_id]:
            del board_data[guild_id]
        save_board_data(board_data)
        await interaction.response.send_message(f"🗑️ Successfully removed the board for {emoji}.")
    else:
        await interaction.response.send_message(f"❌ No board configuration found for {emoji} in this server.", ephemeral=True)




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


@bot.tree.command(name="lock-add", description="Lock this channel - messages will be logged and deleted.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def lock_command(interaction: discord.Interaction):
    locked_channels[interaction.channel_id] = True
    save_lock_config(locked_channels, admin_log_channels)
    await interaction.response.send_message(f"🔒 Channel locked.")


@bot.tree.command(name="lock-remove", description="Unlock this channel.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def unlock_command(interaction: discord.Interaction):
    if interaction.channel_id in locked_channels:
        locked_channels.pop(interaction.channel_id)
        save_lock_config(locked_channels, admin_log_channels)
        await interaction.response.send_message("🔓 Channel unlocked.")
    else:
        await interaction.response.send_message("⚠️ This channel is not currently locked.", ephemeral=True)


@bot.tree.command(name="lock-adminadd", description="Enable admin logging in this channel.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def adminadd_command(interaction: discord.Interaction):
    admin_log_channels[interaction.channel_id] = True
    save_lock_config(locked_channels, admin_log_channels)
    await interaction.response.send_message("📋 Logging enabled in this channel.")


@bot.tree.command(name="lock-adminstop", description="Stop admin logging in this channel.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def adminstop_command(interaction: discord.Interaction):
    if interaction.channel_id in admin_log_channels:
        admin_log_channels.pop(interaction.channel_id)
        save_lock_config(locked_channels, admin_log_channels)
        await interaction.response.send_message("🚫 **Logging stopped.**")
    else:
        await interaction.response.send_message("⚠️ This channel has no active logging.", ephemeral=True)


@bot.tree.command(name="lock-pause", description="Pause message deletion for this channel or all locked channels.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def pause_command(interaction: discord.Interaction, channel: discord.TextChannel = None):
    guild_id = interaction.guild_id
    if channel is None:
        all_paused_guilds.add(guild_id)
        await interaction.response.send_message("⏸️ Message deletion paused for all locked channels in this server.")
        return
    if guild_id not in server_pauses:
        server_pauses[guild_id] = set()
    server_pauses[guild_id].add(channel.id)
    await interaction.response.send_message(f"⏸️ Message deletion paused for {channel.mention}.")


@bot.tree.command(name="lock-resume", description="Resume message deletion for this channel or all locked channels.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def resume_command(interaction: discord.Interaction, channel: discord.TextChannel = None):
    guild_id = interaction.guild_id
    if channel is None:
        all_paused_guilds.discard(guild_id)
        await interaction.response.send_message("▶️ Message deletion resumed for all locked channels in this server.")
        return
    if guild_id not in server_pauses:
        server_pauses[guild_id] = set()
    server_pauses[guild_id].discard(channel.id)
    await interaction.response.send_message(f"▶️ Message deletion resumed for {channel.mention}.")




# -------------------------------------------------------------------------------------------------------------
#                                               Welcome/Goodbye Commands
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="welcome-add", description="Set the channel for welcome images")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def welcome_add(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_config, data = get_guild_config(str(interaction.guild.id))
    guild_config["welcome_channel_id"] = channel.id
    save_guild_data(data)
    await interaction.response.send_message(f"✅ Welcome images will now be sent to {channel.mention}")


@bot.tree.command(name="welcome-del", description="Disable welcome images for this server")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def welcome_del(interaction: discord.Interaction):
    guild_config, data = get_guild_config(str(interaction.guild.id))
    guild_config["welcome_channel_id"] = None
    save_guild_data(data)
    await interaction.response.send_message("✅ Welcome images have been disabled.")


@bot.tree.command(name="goodbye-add", description="Set the channel for goodbye images")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def goodbye_add(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_config, data = get_guild_config(str(interaction.guild.id))
    guild_config["goodbye_channel_id"] = channel.id
    save_guild_data(data)
    await interaction.response.send_message(f"✅ Goodbye images will now be sent to {channel.mention}")


@bot.tree.command(name="goodbye-del", description="Disable goodbye images for this server")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def goodbye_del(interaction: discord.Interaction):
    guild_config, data = get_guild_config(str(interaction.guild.id))
    guild_config["goodbye_channel_id"] = None
    save_guild_data(data)
    await interaction.response.send_message("✅ Goodbye images have been disabled.")


@bot.tree.command(name="test-goodbye", description="Preview the goodbye banner for a specific user")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def test_goodbye(interaction: discord.Interaction, member: discord.Member = None):
    target_member = member or interaction.user
    await interaction.response.defer()
    try:
        goodbye_file = await create_goodbye_card(target_member)
        if goodbye_file:
            await interaction.followup.send(f"🎨 **Goodbye Banner Preview** for {target_member.mention}:", file=goodbye_file)
        else:
            await interaction.followup.send("❌ Failed to generate the image. Check the console for errors.")
    except Exception as e:
        print(f"Error in test-goodbye: {e}")
        await interaction.followup.send(f"⚠️ An error occurred: {e}")


@bot.tree.command(name="test-welcome", description="Preview the welcome banner for a specific user")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def test_welcome(interaction: discord.Interaction, member: discord.Member = None):
    target_member = member or interaction.user
    await interaction.response.defer()
    try:
        welcome_file = await create_welcome_card(target_member)
        if welcome_file:
            await interaction.followup.send(f"🎨 **Welcome Banner Preview** for {target_member.mention}:", file=welcome_file)
        else:
            await interaction.followup.send("❌ Failed to generate the image. Check the console for errors.")
    except Exception as e:
        print(f"Error in test-welcome: {e}")
        await interaction.followup.send(f"⚠️ An error occurred: {e}")


async def create_welcome_card(member):
    base_path = os.path.dirname(__file__)
    bg_path = os.path.join(base_path, "welcome_bg.png")
    font_path = os.path.join(base_path, "Minecraft.ttf")

    if not os.path.exists(bg_path):
        print(f"❌ Background not found at: {bg_path}")
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
        print(f"⚠️ Font error: {e}. Using default.")
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()

    draw.text((35, 30), f"Welcome", fill=(255, 255, 255), font=font_big)
    draw.text((35, 80), f"{member.display_name}", fill=(255, 255, 255), font=font_medium)
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
        print(f"❌ Goodbye background not found at: {bg_path}")
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
        print(f"⚠️ Font error: {e}. Using default.")
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()

    draw.text((35, 30), "Goodbye", fill=(255, 255, 255), font=font_big)
    draw.text((35, 80), f"{member.display_name}", fill=(255, 255, 255), font=font_medium)
    draw.text((35, 140), f"from {member.guild.name}", fill=(200, 200, 200), font=font_small)
    draw.text((35, 170), "We hope to see you again soon!", fill=(200, 200, 200), font=font_small)

    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="goodbye.png")




# -------------------------------------------------------------------------------------------------------------
#                                               Economy Commands
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="eco-leaderboard", description="Show the server economy leaderboard")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_leaderboard(interaction: discord.Interaction, limit: int = 10):
    if limit <= 0:
        return await interaction.response.send_message("❌ Limit must be greater than 0.", ephemeral=True)

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

    embed = discord.Embed(title=f"🏆 Economy Standings Leaderboard - {interaction.guild.name}", color=discord.Color.gold())
    embed.description = "\n".join(description_lines)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="eco-balance", description="Check your balance (or another user's if owner)")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.describe(user="The user you want to check (Owner only)")
async def eco_balance(interaction: discord.Interaction, user: discord.Member = None):
    if user and interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("❌ Only the server owner can check other users' balances!", ephemeral=True)
    target = user or interaction.user
    data = load_data()
    money = data.get(str(interaction.guild.id), {}).get("users", {}).get(str(target.id), {}).get("balance", 0)
    await interaction.response.send_message(f"💰 {target.display_name}'s balance: **${money}**")


@bot.tree.command(name="eco-daily", description="Claim your daily reward")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.checks.cooldown(1, 86400, key=lambda i: (i.user.id, i.guild.id))
async def eco_daily(interaction: discord.Interaction):
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    earnings = random.randint(150, 200)
    user_data["balance"] += earnings
    save_data(data)
    await interaction.response.send_message(f"💵 You claimed your daily reward and earned **${earnings}**!")


@bot.tree.command(name="eco-pay", description="Pay another user from your balance")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_pay(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("❌ Amount must be greater than 0.", ephemeral=True)
    data = load_data()
    guild_id = str(interaction.guild.id)
    sender_data = get_user_data(data, guild_id, str(interaction.user.id))
    receiver_data = get_user_data(data, guild_id, str(user.id))
    if sender_data["balance"] < amount:
        return await interaction.response.send_message("❌ You don't have enough money!", ephemeral=True)
    sender_data["balance"] -= amount
    receiver_data["balance"] += amount
    save_data(data)
    await interaction.response.send_message(f"✅ Successfully sent **${amount}** to {user.mention}!")


@bot.tree.command(name="eco-shop", description="View the server shop")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_shop(interaction: discord.Interaction):
    data = load_data()
    shop_items = data.get(str(interaction.guild.id), {}).get("shop", {})
    if not shop_items:
        await interaction.response.send_message("The shop is currently empty!")
        return
    embed = discord.Embed(title="🛒 Server Shop", color=discord.Color.gold())
    embed.description = "Click a button below to purchase an item! \n ~~───────────────────────────~~"
    for item, info in shop_items.items():
        embed.add_field(name=f"{item} - ${info['price']}", value=info['desc'], inline=False)
    await interaction.response.send_message(embed=embed, view=ShopView(shop_items, str(interaction.guild.id)))


@bot.tree.command(name="eco-shop-add", description="Add an item to the shop")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_shop_add(interaction: discord.Interaction, name: str, desc: str, price: int):
    name = normalize_item(name)
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    guild["shop"][name] = {"desc": desc, "price": price}
    save_data(data)
    await interaction.response.send_message(f"✅ Added **{name}** to the shop!")


@bot.tree.command(name="eco-shop-del", description="Remove an item from the shop")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_shop_del(interaction: discord.Interaction, name: str):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    canonical = find_item_key(guild["shop"], name)
    if canonical:
        del guild["shop"][canonical]
        save_data(data)
        await interaction.response.send_message(f"✅ Removed **{canonical}** from the shop.")
    else:
        await interaction.response.send_message(f"❌ **{name}** was not found in the shop.", ephemeral=True)


@bot.tree.command(name="eco-inventory", description="Check your inventory (or another user's if owner)")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.describe(user="The user you want to check (Owner only)")
async def eco_inventory(interaction: discord.Interaction, user: discord.Member = None):
    if user and interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message("❌ Only the server owner can check others' inventories.", ephemeral=True)
    target = user or interaction.user
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(target.id))
    inv = user_data.get("inventory", {})
    embed = discord.Embed(title=f"📦 {target.display_name}'s Inventory", color=discord.Color.green())
    if not inv:
        embed.description = "This inventory is currently empty."
    else:
        embed.description = "\n".join(f"• {item} ×{count}" for item, count in inv.items())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="eco-inventory-edit", description="Edit a user's inventory (Owner Only)")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_inventory_edit(interaction: discord.Interaction, user: discord.Member, item: str, action: str, amount: int = 1):
    item = normalize_item(item)
    action = action.lower().strip()
    if action not in ("add", "remove"):
        return await interaction.response.send_message("❌ Action must be **add** or **remove**.", ephemeral=True)
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(user.id))
    if action == "add":
        inventory_add(user_data["inventory"], item, amount)
    else:
        removed = inventory_remove(user_data["inventory"], item, amount)
        if removed < amount:
            save_data(data)
            return await interaction.response.send_message(
                f"⚠️ Only removed **{removed}x {item}** - {user.display_name} didn't have enough.", ephemeral=True
            )
    save_data(data)
    direction = "to" if action == "add" else "from"
    await interaction.response.send_message(f"✅ {action.capitalize()}d **{amount}x {item}** {direction} {user.display_name}'s inventory.")


@bot.tree.command(name="eco-balance-edit", description="Set a user's balance (Owner Only)")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_balance_edit(interaction: discord.Interaction, user: discord.Member, amount: int):
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(user.id))
    user_data["balance"] = amount
    save_data(data)
    await interaction.response.send_message(f"✅ Set {user.display_name}'s balance to **${amount}**.")




# -------------------------------------------------------------------------------------------------------------
#                                               Minigames
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="game-slot", description="Play the economy slot machine and wager money")
@app_commands.allowed_installs(guilds=True, users=False)
async def game_slot(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("❌ Bet amount must be greater than 0.", ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))
    before_balance = user_data["balance"]

    if before_balance < amount:
        return await interaction.response.send_message("❌ You don't have enough money to place that bet.", ephemeral=True)

    emojis = ['🍒', '🍎', '🍇', '💎', '🔔', '🍋']
    e1, e2, e3 = (random.choice(emojis) for _ in range(3))

    if e1 == e2 == e3:
        user_data["balance"] += amount*10
        result_text = f"🎉 **JACKPOT!** You won **${amount*10}**!"
        color = discord.Color.green()
    else:
        user_data["balance"] -= amount
        result_text = f"💸 You lost **${amount}**. Better luck next time!"
        color = discord.Color.red()

    save_data(data)

    embed = discord.Embed(title="🎰 Economy Slot Machine", description=f"Bet: **${amount}**", color=color)
    embed.add_field(name="Result", value=f"| {e1} | {e2} | {e3} |", inline=False)
    embed.add_field(name="Outcome", value=result_text, inline=False)
    embed.set_footer(text=f"Before: ${before_balance} • After: ${user_data['balance']}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="game-coinflip", description="Play coinflip and wager money")
@app_commands.allowed_installs(guilds=True, users=False)
async def game_coinflip(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("❌ Bet amount must be greater than 0.", ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))
    before_balance = user_data["balance"]

    if before_balance < amount:
        return await interaction.response.send_message("❌ You don't have enough money to place that bet.", ephemeral=True)

    result = random.choice(["heads", "tails"])
    if result == "heads":
        user_data["balance"] += amount
        result_text = f"🎉 You won **${amount}**! The coin landed on **Heads**."
        color = discord.Color.green()
    else:
        user_data["balance"] -= amount
        result_text = f"💸 You lost **${amount}**. The coin landed on **Tails**."
        color = discord.Color.red()

    save_data(data)

    embed = discord.Embed(title="🪙 Coin Flip", description=f"Bet: **${amount}**", color=color)
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
            return await interaction.response.send_message("❌ This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("❌ This game has already ended.", ephemeral=True)
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
            return await interaction.response.send_message("❌ This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("❌ This game has already ended.", ephemeral=True)
        if not view.action_taken:
            return await interaction.response.send_message("❌ You must reveal at least one tile before cashing out.", ephemeral=True)

        payout = view.calculate_payout()
        data = load_data()
        user_data = get_user_data(data, view.guild_id, view.user_id)
        user_data["balance"] += payout
        save_data(data)
        active_minigame_users.discard(view.user_id)
        view.finished = True
        view.disable_all_items()
        view.embed.title = "💰 Minesweeper - Cash Out"
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
            title="💣 Minesweeper Gamble",
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
        self.embed.title = "💣 Minesweeper Gamble"
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
        self.embed.title = "🏁 Minesweeper - Victory"
        self.embed.description = (
            f"You safely revealed all non-mine tiles and won **${payout}**!\n"
            f"Safe tiles found: **{len(self.revealed_positions)}/{self.total_safe}**"
        )
        self.embed.set_footer(text=f"Before: ${self.before_balance} • After: ${user_data['balance']}")
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This game is not for you.", ephemeral=True)
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
            self.embed.title = "⌛ Minesweeper - Timed Out"
            self.embed.description = (
                f"Time expired and your wager of **${self.amount}** was lost.\n"
                f"Safe tiles found: **{len(self.revealed_positions)}/{self.total_safe}**"
            )
            self.embed.set_footer(text=f"Before: ${self.before_balance}")
            try:
                await self.message.edit(embed=self.embed, view=self)
            except Exception:
                pass


@bot.tree.command(name="game-mines", description="Play minesweeper and wager money")
@app_commands.allowed_installs(guilds=True, users=False)
async def game_mines(interaction: discord.Interaction, amount: int, mines: int):
    if amount <= 0:
        return await interaction.response.send_message("❌ Bet amount must be greater than 0.", ephemeral=True)
    if mines < 3 or mines > 10:
        return await interaction.response.send_message("❌ Number of mines must be between 3 and 10.", ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))
    before_balance = user_data["balance"]

    if interaction.user.id in active_minigame_users:
        return await interaction.response.send_message("❌ You already have an active minigame. Finish or wait for it to time out before starting another.", ephemeral=True)

    if before_balance < amount:
        return await interaction.response.send_message("❌ You don't have enough money to place that bet.", ephemeral=True)

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
            return await interaction.response.send_message("❌ This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("❌ This game has already ended.", ephemeral=True)
        if self.row_index != view.current_row:
            return await interaction.response.send_message("❌ You must click a button in the current row first.", ephemeral=True)

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
            view.embed.title = "🏯 Tower Gamble - Lost"
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
            return await interaction.response.send_message("❌ This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("❌ This game has already ended.", ephemeral=True)
        if not view.action_taken:
            return await interaction.response.send_message("❌ You must pick at least one tile before cashing out.", ephemeral=True)

        payout = view.calculate_payout(view.rows_cleared())
        data = load_data()
        user_data = get_user_data(data, view.guild_id, view.user_id)
        user_data["balance"] += payout
        save_data(data)
        after_balance = user_data["balance"]
        active_minigame_users.discard(view.user_id)
        view.finished = True
        view.disable_all_items()
        view.embed.title = "💰 Tower Gamble - Cash Out"
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
            title="🏯 Tower Gamble",
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
        self.embed.title = "🏯 Tower Gamble"
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
        self.embed.title = "🏁 Tower Gamble - Victory"
        self.embed.description = (
            f"You reached the top and won **${payout}**!\n"
            f"Rows cleared: **5/5**"
        )
        self.embed.set_footer(text=f"Before: ${self.before_balance} • After: ${user_data['balance']}")
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This game is not for you.", ephemeral=True)
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
            self.embed.title = "⌛ Tower Gamble - Timed Out"
            self.embed.description = (
                f"Time expired and your wager of **${self.amount}** was lost.\n"
                f"Rows cleared: **{self.rows_cleared()}/5**"
            )
            self.embed.set_footer(text=f"Before: ${self.before_balance} • After: ${after_balance}")
            try:
                await self.message.edit(embed=self.embed, view=self)
            except Exception:
                pass


@bot.tree.command(name="game-towers", description="Play tower gamble and wager money")
@app_commands.allowed_installs(guilds=True, users=False)
async def game_towers(interaction: discord.Interaction, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("❌ Bet amount must be greater than 0.", ephemeral=True)

    data = load_data()
    guild_id = str(interaction.guild.id)
    user_data = get_user_data(data, guild_id, str(interaction.user.id))
    before_balance = user_data["balance"]

    if interaction.user.id in active_minigame_users:
        return await interaction.response.send_message("❌ You already have an active minigame. Finish or wait for it to time out before starting another.", ephemeral=True)

    if before_balance < amount:
        return await interaction.response.send_message("❌ You don't have enough money to place that bet.", ephemeral=True)

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
            return await interaction.response.send_message("❌ This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("❌ This game has already ended.", ephemeral=True)

        selected_index = int(self.values[0])
        
        if selected_index == self.correct_index:
            view.finished = True
            view.disable_all_items()
            payout = random.randint(450, 550)
            data = load_data()
            user_data = get_user_data(data, view.guild_id, view.user_id)
            user_data["balance"] += payout
            save_data(data)
            view.embed.title = "👨‍💻 Developer Job - Success!"
            view.embed.description = f"You found the odd code string and earned **${payout}**!"
            await interaction.response.edit_message(embed=view.embed, view=view)
        else:
            view.finished = True
            view.disable_all_items()
            view.embed.title = "👨‍💻 Developer Job - Failed!"
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
            return await interaction.response.send_message("❌ This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("❌ This game has already ended.", ephemeral=True)

        if self.is_odd:
            view.finished = True
            view.disable_all_items()
            payout = random.randint(450, 550)
            data = load_data()
            user_data = get_user_data(data, view.guild_id, view.user_id)
            user_data["balance"] += payout
            save_data(data)
            view.embed.title = "👨‍💻 Developer Job - Success!"
            view.embed.description = f"You found the odd code string and earned **${payout}**!"
            await interaction.response.edit_message(embed=view.embed, view=view)
        else:
            self.disabled = True
            self.style = discord.ButtonStyle.danger
            view.finished = True
            view.disable_all_items()
            view.embed.title = "👨‍💻 Developer Job - Failed!"
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
            return await interaction.response.send_message("❌ This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("❌ This game has already ended.", ephemeral=True)

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
                payout = random.randint(450, 550)
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
    def __init__(self, job_type: str, guild_id: str, user_id: int, amount: int):
        super().__init__(timeout=30)
        self.job_type = job_type
        self.guild_id = guild_id
        self.user_id = user_id
        self.amount = amount
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
        code_options = [code_string] * 9
        odd_code = self.mutate_string(code_string)
        code_options.append(odd_code)
        random.shuffle(code_options)
        
        self.embed.title = "👨‍💻 Developer Job"
        self.embed.description = f"Find the code string that is different from the others!\n⏱️ **30 seconds left**"
        
        odd_index = code_options.index(odd_code)
        for i, code in enumerate(code_options):
            is_odd = (i == odd_index)
            button = DeveloperCodeButton(i, code, is_odd, row=i // 5)
            self.add_item(button)

    def setup_farmer_job(self):
        crops = ["🥕", "🥬", "🌾", "🫛", "🥔"]
        target_crop = random.choice(crops)
        wrong_crops = random.sample([c for c in crops if c != target_crop], 2)

        target_positions = set(random.sample(range(8), 2))
        wrong_positions = set(random.sample([i for i in range(8) if i not in target_positions], 2))
        self.target_crop_indices = target_positions

        self.embed.title = "🌱 Farmer Job"
        self.embed.description = (
            f"Collect all **{target_crop}** crops from the farm!\n"
            f"Click the right crops and avoid the others.\n"
            f"⏱️ **30 seconds left**"
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
        self.embed.title = "🧮 Math Teacher Job"
        self.embed.description = f"Solve the equation!\n⏱️ **30 seconds left**"
        
        num1 = random.randint(10, 99)
        num2 = random.randint(1, 50)
        operation = random.choice(["+", "-", "*"])
        
        if operation == "+":
            self.correct_answer = num1 + num2
        elif operation == "-":
            self.correct_answer = num1 - num2
        else:
            self.correct_answer = num1 * num2
        
        self.equation = f"{num1} {operation} {num2} = ?"
        self.embed.description = f"**{self.equation}**\n⏱️ **30 seconds left**"
        
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
                    return await modal_interaction.response.send_message("❌ This is not for you.", ephemeral=True)
                if self.view.finished:
                    return await modal_interaction.response.send_message("❌ Game already finished.", ephemeral=True)
                
                try:
                    user_answer = int(answer_input.value)
                    if user_answer == self.view.correct_answer:
                        self.view.finished = True
                        self.view.disable_all_items()
                        payout = random.randint(450, 550)
                        data = load_data()
                        user_data = get_user_data(data, self.view.guild_id, self.view.user_id)
                        user_data["balance"] += payout
                        save_data(data)
                        self.view.embed.title = "🧮 Math Teacher Job - Success!"
                        self.view.embed.description = f"Correct! The answer is **{self.view.correct_answer}**. You earned **${payout}**!"
                        await modal_interaction.response.defer()
                        await self.view.message.edit(embed=self.view.embed, view=self.view)
                    else:
                        self.view.finished = True
                        self.view.disable_all_items()
                        self.view.embed.title = "🧮 Math Teacher Job - Failed!"
                        self.view.embed.description = f"Wrong! The correct answer is **{self.view.correct_answer}**. You didn't earn anything this time."
                        await modal_interaction.response.defer()
                        await self.view.message.edit(embed=self.view.embed, view=self.view)
                except ValueError:
                    await modal_interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        
        submit_button = discord.ui.Button(label="Submit Answer", style=discord.ButtonStyle.primary)
        
        async def submit_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("❌ This game is not for you.", ephemeral=True)
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
            self.embed.title = "⏰ Work - Timed Out"
            self.embed.description = "Time expired! You didn't earn anything this time."
            try:
                await self.message.edit(embed=self.embed, view=self)
            except Exception:
                pass


work_cooldowns = {}


@bot.tree.command(name="game-work", description="Work to earn money (get 1 of 3 random jobs, 2 hour cooldown)")
@app_commands.allowed_installs(guilds=True, users=False)
async def game_work(interaction: discord.Interaction):
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
                f"⏱️ You can work again in **{minutes}m {seconds}s**.",
                ephemeral=True
            )
    
    data = load_data()
    user_data = get_user_data(data, guild_id, user_id)
    
    job_type = random.choice(["developer", "farmer", "math"])
    amount = 0
    
    work_cooldowns[cooldown_key] = now
    
    view = WorkGameView(job_type, guild_id, interaction.user.id, amount)
    await interaction.response.send_message(embed=view.embed, view=view)
    view.message = await interaction.original_response()




# -------------------------------------------------------------------------------------------------------------
#                                               Crafting Commands
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="eco-craft-add", description="Add a recipe (Owner Only)")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_craft_add(interaction: discord.Interaction, item: str, req1_name: str, req1_count: int, req2_name: str = None, req2_count: int = 0, delay: int = 0):
    item = normalize_item(item)
    req1_name = normalize_item(req1_name)
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    recipe = {"reqs": {req1_name: req1_count}, "delay": delay}
    if req2_name:
        recipe["reqs"][normalize_item(req2_name)] = req2_count
    guild["recipes"][item] = recipe
    save_data(data)
    await interaction.response.send_message(f"✅ Added recipe: **{item}** (Time: {delay}s).")


@bot.tree.command(name="eco-craft", description="Craft an item")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_craft(interaction: discord.Interaction, item: str, amount: int = 1):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    canonical_item = find_item_key(guild["recipes"], item)
    if not canonical_item:
        return await interaction.response.send_message("❌ This item is not craftable.", ephemeral=True)
    recipe = guild["recipes"][canonical_item]
    delay = recipe.get("delay", 0)
    for req_item, count in recipe["reqs"].items():
        if inventory_count(user_data["inventory"], req_item) < (count * amount):
            return await interaction.response.send_message(f"❌ You don't have enough **{req_item}**.", ephemeral=True)
    await interaction.response.send_message(f"🔨 Starting to craft {amount}x **{canonical_item}**... (Wait {delay}s)")
    if delay > 0:
        await asyncio.sleep(delay)
        data = load_data()
        guild = get_guild_data(data, str(interaction.guild.id))
        user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
        for req_item, count in recipe["reqs"].items():
            if inventory_count(user_data["inventory"], req_item) < (count * amount):
                return await interaction.followup.send("❌ Crafting failed: You spent your ingredients while waiting!", ephemeral=True)
    for req_item, count in recipe["reqs"].items():
        inventory_remove(user_data["inventory"], req_item, count * amount)
    inventory_add(user_data["inventory"], canonical_item, amount)
    save_data(data)
    await interaction.followup.send(f"✅ Finished crafting {amount}x **{canonical_item}**!")


@bot.tree.command(name="eco-craft-del", description="Remove a recipe (Owner Only)")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_craft_del(interaction: discord.Interaction, item: str):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    canonical = find_item_key(guild["recipes"], item)
    if canonical:
        del guild["recipes"][canonical]
        save_data(data)
        await interaction.response.send_message(f"🗑️ Removed recipe for **{canonical}**.")
    else:
        await interaction.response.send_message(f"❌ No recipe found for **{item}**.", ephemeral=True)


@bot.tree.command(name="eco-use-add", description="Add usage effect (including giving an item or XP)")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    item="The item whose use effect you want to define",
    money="Money reward granted when the item is used",
    xp="XP reward granted when the item is used",
    message="Custom response message after using the item",
    role="Role to grant when the item is used",
    temp_role="Temporary role to grant when the item is used",
    duration="Length of the temporary role in seconds",
    delay="Delay before the use effect completes",
    instant_message="Message to send immediately before delay",
    give_item="Optional item to grant when used",
    give_item_amount="Quantity of the granted item"
)
async def eco_use_add(interaction: discord.Interaction, item: str, money: int = 0, xp: int = 0, message: str = "Used item!", role: discord.Role = None, temp_role: discord.Role = None, duration: int = 0, delay: int = 0, instant_message: str = None, give_item: str = None, give_item_amount: int = 1):
    item = normalize_item(item)
    if give_item:
        give_item = normalize_item(give_item)

    if role:
        if interaction.user.top_role <= role:
            return await interaction.response.send_message(
                "❌ You cannot configure an item to grant a role that is equal or higher than your highest role.",
                ephemeral=True
            )
        if interaction.guild.me.top_role <= role:
            return await interaction.response.send_message(
                "❌ I cannot assign that role because it is equal or higher than my highest role.",
                ephemeral=True
            )

    if temp_role:
        if interaction.user.top_role <= temp_role:
            return await interaction.response.send_message(
                "❌ You cannot configure an item to grant a temporary role that is equal or higher than your highest role.",
                ephemeral=True
            )
        if interaction.guild.me.top_role <= temp_role:
            return await interaction.response.send_message(
                "❌ I cannot assign that temporary role because it is equal or higher than my highest role.",
                ephemeral=True
            )

    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    guild["item_uses"][item] = {
        "money": money,
        "xp": xp,
        "message": message,
        "role_id": role.id if role else None,
        "temp_role_id": temp_role.id if temp_role else None,
        "duration": duration,
        "delay": delay,
        "instant_message": instant_message,
        "give_item": give_item,
        "give_item_amount": give_item_amount
    }
    save_data(data)
    await interaction.response.send_message(
        f"✅ Effect registered for **{item}**. (Gives: {give_item_amount}x {give_item if give_item else 'None'})"
    )


@bot.tree.command(name="eco-use", description="Use an item from your inventory")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_use(interaction: discord.Interaction, item: str, number_of_times: int = 1):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    if inventory_count(user_data["inventory"], item) < number_of_times:
        return await interaction.response.send_message(f"❌ You need **{number_of_times}x** of this item to do that.", ephemeral=True)
    canonical_item = find_item_key(guild["item_uses"], item)
    if not canonical_item:
        return await interaction.response.send_message("❌ This item has no special use effect.", ephemeral=True)
    effect = guild["item_uses"][canonical_item]
    if number_of_times > 1 and (effect.get("role_id") or effect.get("temp_role_id")):
        return await interaction.response.send_message("❌ You cannot use role-giving items multiple times at once.", ephemeral=True)
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
                    except discord.Forbidden:
                        pass
            if effect.get("temp_role_id"):
                role = interaction.guild.get_role(effect["temp_role_id"])
                if role and interaction.guild.me.top_role > role:
                    try:
                        await interaction.user.add_roles(role)
                    except discord.Forbidden:
                        continue
                    async def remove_role(r):
                        await asyncio.sleep(effect["duration"])
                        await interaction.user.remove_roles(r)
                    bot.loop.create_task(remove_role(role))
    user_data["balance"] += total_money
    save_data(data)
    if total_xp > 0:
        await add_xp(interaction.user, interaction.guild, total_xp)
    final_msg = f"✨ [{number_of_times}x] {effect['message']}"
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


@bot.tree.command(name="eco-use-del", description="Remove usage effect")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_use_del(interaction: discord.Interaction, item: str):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    canonical = find_item_key(guild["item_uses"], item)
    if canonical:
        del guild["item_uses"][canonical]
        save_data(data)
        await interaction.response.send_message(f"🗑️ Removed usage effect for **{canonical}**.")
    else:
        await interaction.response.send_message(f"❌ No usage effect found for **{item}**.", ephemeral=True)


@bot.tree.command(name="eco-value-set", description="Set the selling price for an item")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_value_set(interaction: discord.Interaction, item: str, value: int):
    item = normalize_item(item)
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    guild["item_values"][item] = value
    save_data(data)
    await interaction.response.send_message(f"✅ Users can now sell **{item}** for **${value}**.")


@bot.tree.command(name="eco-value-del", description="Remove the selling price for an item")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def eco_value_del(interaction: discord.Interaction, item: str):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    canonical = find_item_key(guild["item_values"], item)
    if canonical:
        del guild["item_values"][canonical]
        save_data(data)
        await interaction.response.send_message(f"✅ Removed selling price for **{canonical}**. It can no longer be sold.")
    else:
        await interaction.response.send_message(f"❌ **{item}** doesn't have a price set.", ephemeral=True)


@bot.tree.command(name="eco-sell", description="Sell a specific amount of an item from your inventory")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_sell(interaction: discord.Interaction, item: str, amount: int = 1):
    if amount <= 0:
        return await interaction.response.send_message("❌ You must sell at least 1 item.", ephemeral=True)
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    canonical_item = find_item_key(guild.get("item_values", {}), item)
    if canonical_item is None:
        return await interaction.response.send_message(f"❌ **{item}** cannot be sold. No price has been set for it.", ephemeral=True)
    item_price = guild["item_values"][canonical_item]
    user_count = inventory_count(user_data["inventory"], canonical_item)
    if user_count < amount:
        return await interaction.response.send_message(
            f"❌ You don't have enough! You have **{user_count}x {canonical_item}**, but tried to sell **{amount}x**.", ephemeral=True
        )
    inventory_remove(user_data["inventory"], canonical_item, amount)
    total_value = item_price * amount
    user_data["balance"] += total_value
    save_data(data)
    await interaction.response.send_message(
        f"💰 You sold **{amount}x {canonical_item}** for a total of **${total_value}**!\n"
        f"Your new balance is **${user_data['balance']}**."
    )


@bot.tree.command(name="info-values", description="Show all items that can be sold and their prices")
@app_commands.allowed_installs(guilds=True, users=False)
async def info_values(interaction: discord.Interaction):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    prices = guild.get("item_values", {})
    if not prices:
        return await interaction.response.send_message("❌ No items have a selling price set yet.", ephemeral=True)

    embed = discord.Embed(title="💰 Item Market Prices", color=discord.Color.gold())
    for item, price in prices.items():
        embed.add_field(name=item, value=f"Sell Price: **${price}**", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="info-recipes", description="Show all available crafting recipes")
@app_commands.allowed_installs(guilds=True, users=False)
async def info_recipes(interaction: discord.Interaction):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    recipes = guild.get("recipes", {})
    if not recipes:
        return await interaction.response.send_message("❌ No crafting recipes found.", ephemeral=True)

    embed = discord.Embed(title="⚒️ Crafting Book", color=discord.Color.blue())
    for result_item, recipe in recipes.items():
        ing_list = ", ".join(f"{amt}x {name}" for name, amt in recipe["reqs"].items())
        delay_str = f"⏱️ {recipe.get('delay', 0)}s" if recipe.get("delay", 0) > 0 else ""
        embed.add_field(name=result_item, value=f"Requires: {ing_list}{(' \n' + delay_str) if delay_str else ''}", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="info-uses", description="Show what items do when used")
@app_commands.allowed_installs(guilds=True, users=False)
async def info_uses(interaction: discord.Interaction):
    data = load_data()
    guild = get_guild_data(data, str(interaction.guild.id))
    uses = guild.get("item_uses", {})
    if not uses:
        return await interaction.response.send_message("❌ No item effects have been set up.", ephemeral=True)

    embed = discord.Embed(title="🧪 Item Effects Directory", color=discord.Color.green())
    for item, effect in uses.items():
        details = []
        money = effect.get("money", 0)
        if money > 0:
            details.append(f"💰 Gives Money: **${money}**")
        xp_amount = effect.get("xp", 0)
        if xp_amount > 0:
            details.append(f"🧪 Grants XP: **{xp_amount} XP**")
        give_item = effect.get("give_item")
        if give_item:
            amt = effect.get("give_item_amount", 1)
            details.append(f"📦 Gives: **{amt}x {give_item}**")
        if effect.get("role_id"):
            role = interaction.guild.get_role(effect["role_id"])
            if role:
                details.append(f"🛡️ Grants Role: **{role.name}**")
        if effect.get("temp_role_id"):
            role = interaction.guild.get_role(effect["temp_role_id"])
            dur = effect.get("duration", 0)
            if role:
                details.append(f"⏳ Temp Role: **{role.name}** ({dur}s)")
        delay = effect.get("delay", 0)
        if delay > 0:
            details.append(f"⏱️ Delay: {delay}s")
        msg = effect.get("message")
        if msg and msg != "Used item!":
            details.append(f"💬 Message: *{msg}*")
        if details:
            embed.add_field(name=item, value="\n".join(details), inline=False)

    if not embed.fields:
        return await interaction.response.send_message("❌ No item effects have been set up.", ephemeral=True)

    await interaction.response.send_message(embed=embed)




# -------------------------------------------------------------------------------------------------------------
#                                               Leveling System
# -------------------------------------------------------------------------------------------------------------




async def add_xp(member: discord.Member, guild: discord.Guild, xp_to_add: int):
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
        
    save_levels(levels)
    
    if leveled_up:
        rewards = levels[guild_id]["config"].get("rewards", {})
        current_level = user_data["level"]
        reward = rewards.get(str(current_level))
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
                    except discord.Forbidden:
                        print(f"Missing permissions to add role reward {role.name}")

            if reward.get("temp_role_id"):
                role = guild.get_role(int(reward["temp_role_id"]))
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role)
                    except discord.Forbidden:
                        role = None
                if role and reward.get("duration", 0) > 0:
                    async def remove_temp_role(r):
                        await asyncio.sleep(reward.get("duration", 0))
                        await member.remove_roles(r)
                    bot.loop.create_task(remove_temp_role(role))

            if reward.get("xp", 0) > 0:
                await add_xp(member, guild, reward["xp"])

        channel_id = levels[guild_id]["config"].get("channel_id")
        target_channel = guild.get_channel(int(channel_id)) if channel_id else None
        
        if target_channel:
            card_bytes = await create_levelup_card(member, current_level)
            if card_bytes:
                file = discord.File(fp=card_bytes, filename="levelup.png")
                await target_channel.send(
                    content=f"🎉 {member.mention}, you just reached **Level {current_level}**!",
                    file=file
                )


async def create_levelup_card(member: discord.Member, level: int):
    base_path = os.path.dirname(__file__)
    bg_path = os.path.join(base_path, "levelup_bg.png")
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
        
    draw.text((center_x, 190), f"{member.display_name} you are now Level {level}!", fill="white", font=font, anchor="mm")
    
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
    "white": "⬜", "black": "⬛", "red": "🟥", "blue": "🟦", 
    "green": "🟩", "yellow": "🟨", "purple": "🟪", "orange": "🟧", "brown": "🟫"
}


@bot.tree.command(name="color", description="Choose the block color for your /level tracking progress bar")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.choices(color=[app_commands.Choice(name=name.title(), value=name) for name in COLOR_EMOJIS.keys() if name != "black"])
async def set_profile_color(interaction: discord.Interaction, color: str):
    settings = load_user_settings()
    if "users" not in settings:
        settings["users"] = {}
    settings["users"][str(interaction.user.id)] = {"color": color}
    save_user_settings(settings)

    await interaction.response.send_message(
        f"🎨 Clean style! Your profile tracking bar is now set to {COLOR_EMOJIS[color]} **{color}** across all servers.",
        ephemeral=True
    )


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
    
    filled_emoji = COLOR_EMOJIS.get(chosen_color, "⬜")
    empty_emoji = COLOR_EMOJIS.get("black", "⬛")
    
    progress_bar = (filled_emoji * filled_blocks) + (empty_emoji * empty_blocks)
    
    embed = discord.Embed(
        title=f"🏆 Rank Profile - {target.display_name}",
        color=discord.Color.dark_gray()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Current Tier", value=f"✨ **Level {current_lvl}**", inline=True)
    embed.add_field(name="Experience Nodes", value=f"🧪 `{current_xp:,}` / `{xp_needed:,}` XP", inline=True)
    embed.add_field(name="Progress Metrics", value=progress_bar, inline=False)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="lvl-leaderboard", description="Display the top 10 highest-level users in this guild")
@app_commands.allowed_installs(guilds=True, users=False)
async def level_leaderboard(interaction: discord.Interaction):
    levels = load_levels()
    g_id = str(interaction.guild_id)
    
    users_dict = levels.get(g_id, {}).get("users", {})
    if not users_dict:
        return await interaction.response.send_message("📭 No active XP statistics logged in this server yet.", ephemeral=True)
        
    sorted_users = sorted(users_dict.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)
    
    embed = discord.Embed(title=f"📊 Level Standings Leaderboard - {interaction.guild.name}", color=discord.Color.gold())
    
    description_text = ""
    for index, (u_id, data) in enumerate(sorted_users[:10], start=1):
        member = interaction.guild.get_member(int(u_id))
        name_str = member.display_name if member else f"User left server (`{u_id}`)"
        description_text += f"`#{index}` **{name_str}** - Lvl {data['level']} ({data['xp']} XP)\n"
        
    embed.description = description_text
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="lvl-edit", description="(Admin) Manually adjust or set a target user's level and XP indexes")
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
    await interaction.response.send_message(f"⚙️ Action complete. Set {user.mention} to **Level {level}** with **{xp} XP**.", ephemeral=True)


@bot.tree.command(name="lvl-channel-set", description="(Admin) Route level-up image logs into a designated text stream")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.checks.has_permissions(manage_guild=True)
async def lvl_channel_set(interaction: discord.Interaction, channel: discord.TextChannel):
    levels = load_levels()
    g_id = str(interaction.guild_id)
    
    if g_id not in levels: levels[g_id] = {"config": {}, "users": {}}
    
    levels[g_id]["config"]["channel_id"] = channel.id
    save_levels(levels)
    await interaction.response.send_message(f"📌 Destination updated! Level-up notifications will now send to {channel.mention}.")


@bot.tree.command(name="lvl-channel-remove", description="(Admin) Disable level-up notification image cards from sending")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.checks.has_permissions(manage_guild=True)
async def lvl_channel_remove(interaction: discord.Interaction):
    levels = load_levels()
    g_id = str(interaction.guild_id)
    
    if g_id not in levels or "config" not in levels[g_id] or levels[g_id]["config"].get("channel_id") is None:
        return await interaction.response.send_message(
            "❌ There is no level-up notification channel configured for this server currently.", 
            ephemeral=True
        )
    
    levels[g_id]["config"]["channel_id"] = None
    save_levels(levels)
    
    await interaction.response.send_message(
        "🗑️ Configuration removed! Level-up image banners are now disabled for this server.", 
        ephemeral=True
    )


@bot.tree.command(name="lvl-rewards-set", description="(Admin) Map an automatic reward milestone to a level")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(
    level="The target level milestone",
    role="Optional role to grant at this level",
    temp_role="Optional temporary role to grant at this level",
    duration="Duration for the temporary role in seconds",
    money="Optional money reward granted at this level",
    xp="Optional XP reward granted at this level",
    item="Optional item to give at this level",
    item_amount="Quantity of the item to give"
)
async def lvl_rewards_set(interaction: discord.Interaction, level: int, role: discord.Role = None, temp_role: discord.Role = None, duration: int = 0, money: int = 0, xp: int = 0, item: str = None, item_amount: int = 1):
    if not role and not temp_role and money <= 0 and xp <= 0 and not item:
        return await interaction.response.send_message(
            "❌ You must specify at least one reward: role, temp_role, money, xp, or item.",
            ephemeral=True
        )

    if role:
        if interaction.user.top_role <= role:
            return await interaction.response.send_message(
                "❌ You cannot configure a level reward role that is equal or higher than your highest role.",
                ephemeral=True
            )
        if interaction.guild.me.top_role <= role:
            return await interaction.response.send_message(
                "❌ I cannot assign that role because it is equal or higher than my highest role.",
                ephemeral=True
            )

    if temp_role:
        if interaction.user.top_role <= temp_role:
            return await interaction.response.send_message(
                "❌ You cannot configure a temporary role reward that is equal or higher than your highest role.",
                ephemeral=True
            )
        if interaction.guild.me.top_role <= temp_role:
            return await interaction.response.send_message(
                "❌ I cannot assign that temporary role because it is equal or higher than my highest role.",
                ephemeral=True
            )

    reward_data = {
        "role_id": role.id if role else None,
        "temp_role_id": temp_role.id if temp_role else None,
        "duration": duration,
        "money": money,
        "xp": xp,
        "give_item": normalize_item(item) if item else None,
        "give_item_amount": item_amount
    }

    levels = load_levels()
    g_id = str(interaction.guild_id)

    if g_id not in levels:
        levels[g_id] = {"config": {"channel_id": None, "rewards": {}}, "users": {}}
    if "rewards" not in levels[g_id]["config"]:
        levels[g_id]["config"]["rewards"] = {}
        
    levels[g_id]["config"]["rewards"][str(level)] = reward_data
    save_levels(levels)

    reward_parts = []
    if role:
        reward_parts.append(f"role {role.mention}")
    if temp_role:
        reward_parts.append(f"temp role {temp_role.mention} for {duration}s")
    if money > 0:
        reward_parts.append(f"${money}")
    if xp > 0:
        reward_parts.append(f"{xp} XP")
    if item:
        reward_parts.append(f"{item_amount}x {normalize_item(item)}")

    await interaction.response.send_message(
        f"🎁 Level {level} reward configured: {', '.join(reward_parts)}.", ephemeral=True
    )


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


@bot.tree.command(name="info-lvl-rewards", description="Show the level rewards configured for this guild")
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
        title=f"🎁 Level Rewards - {interaction.guild.name}",
        color=discord.Color.gold()
    )

    if level is not None:
        reward_data = rewards.get(str(level))
        if not reward_data:
            return await interaction.response.send_message(f"❌ No rewards are configured for level {level} in this server.", ephemeral=True)

        embed.description = format_level_reward_summary(interaction.guild, str(level), reward_data)
    else:
        sorted_levels = sorted(rewards.items(), key=lambda item: int(item[0]))
        embed.description = "\n".join(
            format_level_reward_summary(interaction.guild, lvl, reward_data)
            for lvl, reward_data in sorted_levels
        )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="lvl-rewards-del", description="(Admin) Delete all rewards configured for a level")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(level="The level whose rewards should be removed")
async def lvl_rewards_del(interaction: discord.Interaction, level: int):
    levels = load_levels()
    g_id = str(interaction.guild_id)

    if g_id not in levels or "config" not in levels[g_id] or "rewards" not in levels[g_id]["config"]:
        return await interaction.response.send_message(f"❌ No rewards are configured for level {level} in this server.", ephemeral=True)

    rewards = levels[g_id]["config"]["rewards"]
    if str(level) not in rewards:
        return await interaction.response.send_message(f"❌ No rewards are configured for level {level} in this server.", ephemeral=True)

    del rewards[str(level)]
    save_levels(levels)

    await interaction.response.send_message(f"🗑️ Removed all rewards configured for level {level}.", ephemeral=True)




# -------------------------------------------------------------------------------------------------------------
#                                               Owner Commands
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="own-shutdown", description="(owner) Stop the bot for an update or just to restart")
@app_commands.describe(
    channel="Optional announcement channel to send the shutdown message to",
    reason="The shutdown reason to publish"
)
async def own_shutdown(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None,
    reason: str = "No reason provided"
):
    if not await bot.is_owner(interaction.user):
        return await interaction.response.send_message("❌ Do not even try...", ephemeral=True)

    target_channel = channel or bot.get_channel(1514173159052415026)
    if target_channel is None and isinstance(interaction.channel, discord.TextChannel):
        target_channel = interaction.channel

    shutdown_text = (
        f"🔌 {reason}"
    )
    shutdown_embed = discord.Embed(
        title="Bot Shutdown Initiated",
        description=shutdown_text,
        color=discord.Color.light_gray()
    )

    published = False
    if target_channel is not None:
        try:
            sent_msg = await target_channel.send(embed=shutdown_embed)
            if target_channel.type == discord.ChannelType.news:
                try:
                    await sent_msg.publish()
                    published = True
                except Exception:
                    published = False
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Could not send the shutdown notice to {target_channel.mention}. Error: {e}",
                ephemeral=True
            )
            return

    if update_presence.is_running():
        update_presence.cancel()
        await asyncio.sleep(1)

    response_text = "Going to sleep..."
    if target_channel is not None:
        response_text = (
            f"Shutdown notice sent to {target_channel.mention}. "
            + ("Published to followers." if published else "")
        )

    await interaction.response.send_message(response_text)

    shutdown_activity = discord.Activity(type=discord.ActivityType.watching, name="App is shutting down!!! !! !")
    sleep_activity = discord.Activity(type=discord.ActivityType.watching, name="App is sleeping... zZzZzZ")
    for shard_id in bot.shards:
        await bot.change_presence(activity=shutdown_activity, status=discord.Status.dnd, shard_id=shard_id)
    await asyncio.sleep(10)
    for shard_id in bot.shards:
        await bot.change_presence(activity=sleep_activity, status=discord.Status.idle, shard_id=shard_id)
    await bot.close()


@bot.tree.command(name="own-stop-urgent", description="(owner) STOPS IMMEDIATLY IF SOMETHING WENT REALLY WRONG")
@app_commands.describe(channel="Optional announcement channel to send the force shutdown message to")
async def own_stop_urgent(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not await bot.is_owner(interaction.user):
        return await interaction.response.send_message("❌ Stop.", ephemeral=True)

    target_channel = channel or bot.get_channel(1514173159052415026)
    if target_channel is None and isinstance(interaction.channel, discord.TextChannel):
        target_channel = interaction.channel

    force_text = "⚠️ The bot is going offline immediately due to an urgent issue."
    force_embed = discord.Embed(
        title="Force Shutdown",
        description=force_text,
        color=discord.Color.red()
    )

    if target_channel is not None:
        try:
            sent_msg = await target_channel.send(embed=force_embed)
            if target_channel.type == discord.ChannelType.news:
                try:
                    await sent_msg.publish()
                except Exception:
                    pass
        except Exception:
            pass

    if update_presence.is_running():
        update_presence.cancel()
    await interaction.response.send_message("Goodbye.")
    forced_activity = discord.Activity(type=discord.ActivityType.watching, name="App was shutdown forcefully...")
    for shard_id in bot.shards:
        await bot.change_presence(activity=forced_activity, status=discord.Status.dnd, shard_id=shard_id)
    await bot.close()


@bot.tree.command(name="own-shard-info", description="(owner) Display shard status and guild distribution")
@app_commands.allowed_installs(guilds=True, users=False)
async def shard_info(interaction: discord.Interaction):
    if not await bot.is_owner(interaction.user):
        return await interaction.response.send_message("❌ Owner only.", ephemeral=True)

    total_shards = len(bot.shards) or 1
    embed = discord.Embed(title="🔀 Shard Information", color=discord.Color.blurple())
    embed.add_field(name="Total Shards", value=str(total_shards), inline=True)
    embed.add_field(name="Total Guilds", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="Total Users", value=str(len(bot.users)), inline=True)

    for shard_id, shard in bot.shards.items():
        guilds_on_shard = [g for g in bot.guilds if g.shard_id == shard_id]
        latency_ms = round(shard.latency * 1000, 1)
        embed.add_field(
            name=f"Shard {shard_id}",
            value=f"📶 {latency_ms}ms | 🏠 {len(guilds_on_shard)} guild(s)",
            inline=False,
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="own-shard-map", description="(owner) Show which guilds are assigned to each shard")
async def shard_map(interaction: discord.Interaction):
    if not await bot.is_owner(interaction.user):
        return await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)

    shard_map = {}
    for guild in bot.guilds:
        shard_id = getattr(guild, 'shard_id', 0)
        shard_map.setdefault(shard_id, []).append(f"> **{guild.name}** ||({guild.id})||")

    embed = discord.Embed(
        title="🧩 Shard Assignment Map",
        description="Shows which servers are served by each shard.",
        color=discord.Color.blurple()
    )
    for shard_id in sorted(shard_map.keys()):
        guild_list = shard_map[shard_id]
        value = "\n".join(guild_list)
        embed.add_field(name=f"Shard {shard_id}", value=value, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)




# -------------------------------------------------------------------------------------------------------------
bot.run(TOKEN)
