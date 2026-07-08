import asyncio, os, random, discord, queue, threading
from datetime import datetime, timezone
from discord import TextInput, app_commands
from discord.ext import commands
from dotenv import load_dotenv
from discord.ui import Modal, Separator, TextInput, Button, LayoutView, Container, Section, TextDisplay, ChannelSelect

from Shared.Locks import load_lock_config

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




# -------------------------------------------------------------------------------------------------------------
#                                               Bot Setup
# -------------------------------------------------------------------------------------------------------------




class NinnnUtils(commands.AutoShardedBot):
    def __init__(self, intents, shard_count: int = 0):
        super().__init__(
            command_prefix="n!",
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

locked_channels, admin_log_channels = load_lock_config()


# -------------------------------------------------------------------------------------------------------------
#                                               UI Views
# -------------------------------------------------------------------------------------------------------------



# -------------------------------------------------------------------------------------------------------------
#                                               Events
# -------------------------------------------------------------------------------------------------------------

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

# -------------------------------------------------------------------------------------------------------------
#                                               Error Handling
# -------------------------------------------------------------------------------------------------------------


# -------------------------------------------------------------------------------------------------------------
#                                               Presence Update Loop
# -------------------------------------------------------------------------------------------------------------

presence_index = 0

# -------------------------------------------------------------------------------------------------------------
#                                               Blacklist Handling
# -------------------------------------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------------------------------
#                                               User Level Commands
# -------------------------------------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------------------------------
#                                               Admin Commands
# -------------------------------------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------------------------------
#                                               Deleted Edited / Ghost Pings / Error
# -------------------------------------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------------------------------
#                                               Counter command, its alone now ]: poor thing 😭 all his friends moved to /settings 😭😭😭
# -------------------------------------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------------------------------
#                                               Board Commands
# -------------------------------------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------------------------------
#                                               Lock Commands
# -------------------------------------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------------------------------
#                                               Welcome/Goodbye Commands
# -------------------------------------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------------------------------
#                                               Economy Commands
# -------------------------------------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------------------------------
#                                               Minigames
# -------------------------------------------------------------------------------------------------------------

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

# -------------------------------------------------------------------------------------------------------------
#                                               Crafting Commands
# -------------------------------------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------------------------------
#                                               Leveling System
# -------------------------------------------------------------------------------------------------------------

COLOR_EMOJIS = {
    "white": "<:Square_White:1517679898414813427>", "black": "<:Square_Black:1517679889615032540>", "red": "<:Square_Red:1517679897068306522>", "blue": "<:Square_Blue:1517679890932043897>", 
    "green": "<:Square_Green:1517679893234716843>", "yellow": "<:Square_Yellow:1517679899769311302>", "purple": "<:Square_Purple:1517679895738581062>", "orange": "<:Square_Orange:1517679894526562405>", "brown": "<:Square_Brown:1517679892039204955>"
}

# -------------------------------------------------------------------------------------------------------------
#                                               Owner Commands
# -------------------------------------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------------------------------
#                                               Personalization Commands
# -------------------------------------------------------------------------------------------------------------




USER_COLOR_OPTIONS = [name for name in COLOR_EMOJIS.keys() if name != "black"]

def validate_role_selection(interaction: discord.Interaction, role: discord.Role | None, role_label: str) -> str | None:
    if role is None:
        return None
    if not guild_owner_bypasses_role_checks(interaction) and interaction.user.top_role <= role:
        return f"<:disapprove:1517452151012589662> You cannot configure a {role_label} that is equal or higher than your highest role."
    if interaction.guild.me.top_role <= role:
        return "<:disapprove:1517452151012589662> I cannot assign that role because it is equal or higher than my highest role."
    return None

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

# -------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.presences = True
    bot = NinnnUtils(intents=intents, shard_count=SHARD_COUNT)
    bot.run(TOKEN)