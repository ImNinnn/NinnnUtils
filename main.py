import asyncio, ast, json, os, random, time, yt_dlp, discord, io, unicodedata, base64, queue, threading, traceback, aiohttp
from datetime import datetime, timedelta, timezone
from collections import Counter
from discord import ComponentType, TextInput, app_commands, Status
from discord.ext import tasks, commands
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageOps
from deep_translator import GoogleTranslator
from discord.ui import Modal, Separator, TextInput, View, Button, LayoutView, Container, Section, TextDisplay, MediaGallery, ChannelSelect
from pypresence import Presence
from pypresence.types import ActivityType



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
                        f"<:dissaprouve:1517452151012589662> Could not find a definition for **{word}**. Double check your spelling!", 
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
        await interaction.followup.send("<:dissaprouve:1517452151012589662> An internal error occurred while fetching the definition.", ephemeral=True)


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
    embed.add_field(name="<:dissaprouve:1517452151012589662> Bots", value=str(bot_count), inline=True)
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
            # prefer to show emoji (emoji_key) and required count
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

    embed = discord.Embed(title=f"<:drawer:1517497564189036574> Configured Channels for {guild.name}", color=discord.Color.blurple())
    embed.add_field(name="<:plus:1518348756570079262> Welcome Channel", value=welcome, inline=False)
    embed.add_field(name="<:minus:1518348754111959150> Goodbye Channel", value=goodbye, inline=False)
    embed.add_field(name="<:chalice:1517579767573123092> Level-up Announce Channel", value=lvl_channel, inline=False)
    embed.add_field(name="<:graph:1517584522877866065> Board Channels", value=board_channels, inline=False)
    embed.add_field(name="<:list:1517497572770451567> Counter Channels", value=counter_channels, inline=False)
    embed.add_field(name="<:unlocked:1517574880034558102> Admin Log Channel", value=admin_log_channel, inline=False)
    embed.add_field(name="<:locked:1517574877257924809> Locked Channels", value=locked_channels, inline=False)
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
    embed.add_field(name="<:nUtils:1518376146008539146> Bot owner", value="-ImNinnn- (imninnn.)", inline=True)
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


@bot.tree.command(name="adm-rename", description="Rename a user or reset their nickname")
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


@bot.tree.command(name="adm-purge-nuke", description="Fully clear a channel")
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


@bot.tree.command(name="adm-purge", description="Mass delete messages from the channel")
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
        await interaction.response.send_message("<:disapprove:1517452151012589662> You must specify a duration greater than 0!", ephemeral=True)
        return
    if duration.total_seconds() > 2419200:
        await interaction.response.send_message("<:disapprove:1517452151012589662> Timeout cannot exceed 28 days.", ephemeral=True)
        return

    if not guild_owner_bypasses_role_checks(interaction) and interaction.user != member and member.top_role >= interaction.user.top_role:
        await interaction.response.send_message("<:disapprove:1517452151012589662> You cannot timeout someone with an equal or higher role than yours.", ephemeral=True)
        return

    time_str = f"{days}d {hours}h {minutes}m {seconds}s"
    if not member.bot:
        try:
            dm_embed = discord.Embed(
                title="<:hourglass:1517574046252924938> You have been timed out",
                description=f"**Server:** {interaction.guild.name}\n**Duration:** {time_str}\n**Reason:** {reason}",
                color=discord.Color.orange()
            )
            await member.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    try:
        await member.timeout(duration, reason=reason)
        confirm_embed = discord.Embed(
            title="<:approve:1517452125687513158> User Timed Out",
            description=f"**{format_user_reference(member)}** has been timed out for {time_str}.",
            color=discord.Color.green()
        )
        confirm_embed.add_field(name="Reason", value=reason)
        await interaction.response.send_message(embed=confirm_embed)
    except discord.Forbidden:
        await interaction.response.send_message("<:disapprove:1517452151012589662> I don't have permission to timeout this user (Hierarchy issue).", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"<:disapprove:1517452151012589662> An error occurred: {e}", ephemeral=True)




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


@bot.tree.command(name="lock-add", description="Lock this channel - messages will be logged and deleted.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def lock_command(interaction: discord.Interaction):
    locked_channels[interaction.channel_id] = True
    save_lock_config(locked_channels, admin_log_channels)
    await interaction.response.send_message(f"<:locked:1517574877257924809> Channel locked.")


@bot.tree.command(name="lock-remove", description="Unlock this channel.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def unlock_command(interaction: discord.Interaction):
    if interaction.channel_id in locked_channels:
        locked_channels.pop(interaction.channel_id)
        save_lock_config(locked_channels, admin_log_channels)
        await interaction.response.send_message("<:unlocked:1517574880034558102> Channel unlocked.")
    else:
        await interaction.response.send_message("<:warning:1517452174991556758> This channel is not currently locked.", ephemeral=True)


@bot.tree.command(name="lock-adminstop", description="Stop admin logging in this channel.")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.default_permissions(manage_guild=True)
async def adminstop_command(interaction: discord.Interaction):
    if interaction.channel_id in admin_log_channels:
        admin_log_channels.pop(interaction.channel_id)
        save_lock_config(locked_channels, admin_log_channels)
        await interaction.response.send_message("<:prohibited:1517497579582132436> **Logging stopped.**")
    else:
        await interaction.response.send_message("<:warning:1517452174991556758> This channel has no active logging.", ephemeral=True)


@bot.tree.command(name="lock-pause", description="Pause message deletion for this channel or all locked channels.")
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


@bot.tree.command(name="lock-resume", description="Resume message deletion for this channel or all locked channels.")
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
    bg_path = os.path.join(base_path, "welcome_bg.png")
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

def wrap_text(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int) -> list[str]:
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
            if draw.textbbox((0, 0), test_line, font=font)[2] <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)

    return lines


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
    display_name_text = f"- {message.author.display_name if display_name_is_ascii else message.author.name}"
    username_text = f"@{message.author.name}"
    show_username = display_name_is_ascii

    original_content = message.content.strip() or "[Embed or media content]"
    content_text = original_content
    content_text = content_text.replace('\n', ' ')
    content_text = content_text.replace('"', '\\"')
    had_non_ascii = any(ord(char) > 127 for char in original_content)
    content_text = unicodedata.normalize('NFKD', content_text)
    content_text = content_text.encode('ascii', 'ignore').decode('ascii')
    content_text = f'"{content_text}"'

    bg_width, bg_height = background.size
    text_x = 250
    text_y = 35
    max_text_width = min(400, bg_width - text_x - 30)
    footer_y = bg_height - 44

    quote_font_size = 24
    quote_font = font_big
    lines = wrap_text(content_text, draw, quote_font, max_text_width)

    if len(lines) > 4:
        quote_font_size = max(12, 24 - 4 * (len(lines) - 4))
        quote_font = ImageFont.truetype(font_path, quote_font_size)
        lines = wrap_text(content_text, draw, quote_font, max_text_width)
        if len(lines) > 4:
            quote_font_size = max(12, 24 - 4 * (len(lines) - 4))
            quote_font = ImageFont.truetype(font_path, quote_font_size)
            lines = wrap_text(content_text, draw, quote_font, max_text_width)

    line_height = int(getattr(quote_font, 'size', quote_font_size) * 1.4)
    max_lines = max(1, (footer_y - text_y) // line_height)
    truncated = False
    if len(lines) > max_lines:
        truncated = True
        if quote_font_size == 12:
            visible = lines[:max_lines]
            ellipsis = "..."
            while ellipsis and draw.textbbox((0, 0), ellipsis, font=quote_font)[2] > max_text_width:
                ellipsis = ellipsis[:-1]

            last = visible[-1]
            if ellipsis:
                while last and draw.textbbox((0, 0), last + ellipsis, font=quote_font)[2] > max_text_width:
                    last = last[:-1]
                last = last.rstrip()
                if not last:
                    visible[-1] = ellipsis
                else:
                    visible[-1] = last + ellipsis
            else:
                while last and draw.textbbox((0, 0), last, font=quote_font)[2] > max_text_width:
                    last = last[:-1]
                visible[-1] = last

            lines = visible
        else:
            lines = lines[:max_lines]

    for line in lines:
        draw.text((text_x, text_y), line, fill=(255, 255, 255), font=quote_font)
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

    notices = []
    if 'had_non_ascii' in locals() and had_non_ascii:
        notices.append("ASCII Error")
    if truncated:
        notices.append("Size Error")

    if notices:
        notice_text = " | ".join(notices)
        try:
            notice_font = ImageFont.truetype(font_path, 12)
        except Exception:
            notice_font = font_small
        notice_color = (255, 60, 60)
        notice_x = 25
        notice_y = footer_y - -5
        draw.text((notice_x, notice_y), notice_text, fill=notice_color, font=notice_font)

    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="quote.png")




# -------------------------------------------------------------------------------------------------------------
#                                               Economy Commands
# -------------------------------------------------------------------------------------------------------------




@bot.tree.command(name="eco-leaderboard", description="Show the server economy leaderboard")
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


@bot.tree.command(name="eco-balance", description="Check your balance or another user's balance")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.describe(user="The user whose balance you want to check")
async def eco_balance(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    data = load_data()
    money = data.get(str(interaction.guild.id), {}).get("users", {}).get(str(target.id), {}).get("balance", 0)
    await interaction.response.send_message(f"<:money:1517580310395486239> {target.display_name}'s balance: **${money}**")


@bot.tree.command(name="eco-daily", description="Claim your daily reward")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.checks.cooldown(1, 86400, key=lambda i: (i.user.id, i.guild.id))
async def eco_daily(interaction: discord.Interaction):
    data = load_data()
    user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
    earnings = random.randint(150, 200)
    user_data["balance"] += earnings
    save_data(data)
    await interaction.response.send_message(f"<:money:1517580310395486239> You claimed your daily reward and earned **${earnings}**!")


@bot.tree.command(name="eco-pay", description="Pay another user from your balance")
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


@bot.tree.command(name="eco-shop", description="View the server shop")
@app_commands.allowed_installs(guilds=True, users=False)
async def eco_shop(interaction: discord.Interaction):
    data = load_data()
    shop_items = data.get(str(interaction.guild.id), {}).get("shop", {})
    if not shop_items:
        await interaction.response.send_message("The shop is currently empty!")
        return

    view = ShopView(shop_items, str(interaction.guild.id), str(interaction.user.id))
    await interaction.response.send_message(view=view)


@bot.tree.command(name="eco-inventory", description="Check your inventory or another user's inventory")
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


@bot.tree.command(name="eco-inventory-edit", description="Edit a user's inventory (Owner Only)")
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


@bot.tree.command(name="eco-balance-edit", description="Set a user's balance (Owner Only)")
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




@bot.tree.command(name="game-slot", description="Play the economy slot machine and wager money")
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


@bot.tree.command(name="game-coinflip", description="Play coinflip and wager money")
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


@bot.tree.command(name="game-mines", description="Play minesweeper and wager money")
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


@bot.tree.command(name="game-towers", description="Play tower gamble and wager money")
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


@bot.tree.command(name="game-work", description="Work to earn money (get 1 of 3 random jobs, 2 hour cooldown)")
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




@bot.tree.command(name="eco-craft", description="Craft an item")
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


@bot.tree.command(name="eco-use", description="Use an item from your inventory")
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


@bot.tree.command(name="eco-sell", description="Sell a specific amount of an item from your inventory")
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


@bot.tree.command(name="info-values", description="Show all items that can be sold and their prices")
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


@bot.tree.command(name="info-recipes", description="Show all available crafting recipes")
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


@bot.tree.command(name="info-uses", description="Show what items do when used")
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
        
    first_time_level_up = False
    if leveled_up and not get_user_has_leveled_up_before(user_id):
        first_time_level_up = True
        set_user_has_leveled_up_before(user_id, True)

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
                except discord.Forbidden as error:
                    add_bot_error_entry(guild.id, target_channel.id, member, "level banner", error)


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


@bot.tree.command(name="lvl-leaderboard", description="Display the top 10 highest-level users in this guild")
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


@bot.tree.command(name="lvl-rewards-del", description="(Admin) Delete all rewards configured for a level")
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(level="The level whose rewards should be removed")
async def lvl_rewards_del(interaction: discord.Interaction, level: int):
    levels = load_levels()
    g_id = str(interaction.guild_id)

    if g_id not in levels or "config" not in levels[g_id] or "rewards" not in levels[g_id]["config"]:
        return await interaction.response.send_message(f"<:disapprove:1517452151012589662> No rewards are configured for level {level} in this server.", ephemeral=True)

    rewards = levels[g_id]["config"]["rewards"]
    if str(level) not in rewards:
        return await interaction.response.send_message(f"<:disapprove:1517452151012589662> No rewards are configured for level {level} in this server.", ephemeral=True)

    del rewards[str(level)]
    save_levels(levels)

    await interaction.response.send_message(f"<:trash:1517497581058527404> Removed all rewards configured for level {level}.", ephemeral=True)




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
        return await ctx.send("<:disapprove:1517452151012589662> Do not even try...")

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
        return await ctx.send("<:disapprove:1517452151012589662> Do not even try...")

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
        return await ctx.send("<:disapprove:1517452151012589662> Do not even try...")

    global ACTIVITY_TEXT

    if not new_value.strip():
        return await ctx.send(f"Current activity: `{ACTIVITY_TEXT or ''}`")

    cleaned_value = new_value.strip()
    update_env_setting("ACTIVITY", cleaned_value)
    ACTIVITY_TEXT = cleaned_value

    if update_presence.is_running():
        update_presence.restart()

    await ctx.send(f"Updated ACTIVITY in .env to `{ACTIVITY_TEXT}`.")


@bot.command(name="shutdown")
async def own_shutdown(ctx: commands.Context, *, args: str = ""):
    if not await bot.is_owner(ctx.author):
        return await ctx.send("<:disapprove:1517452151012589662> Do not even try...")

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
        self.channel_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="settings_open_channel",
        )
        self.economy_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="settings_open_economy",
        )
        self.level_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="settings_open_level",
        )

        async def open_user(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            new_view = UserSettingsView(
                interaction.user.id,
                current_color=user_settings.get("color", "white"),
                current_pings=user_settings.get("user_pings", True),
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

            guild_id = str(interaction.guild.id)
            guild_config, _ = get_guild_config(guild_id)
            new_view = GuildSettingsView(
                interaction.user.id,
                guild_id,
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

            guild_id = str(interaction.guild.id)
            new_view = ChannelSettingsView(
                interaction.user.id,
                guild_id,
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

            guild_id = str(interaction.guild.id)
            new_view = EconomySettingsView(
                interaction.user.id,
                guild_id,
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

            guild_id = str(interaction.guild.id)
            new_view = LevelSettingsView(
                interaction.user.id,
                guild_id,
                get_user_color_value(str(interaction.user.id)),
                settings_message=interaction.message,
            )
            await interaction.response.edit_message(view=new_view)

        self.user_button.callback = open_user
        self.guild_button.callback = open_guild
        self.channel_button.callback = open_channel_settings
        self.economy_button.callback = open_economy_settings
        self.level_button.callback = open_level_settings

        container = Container(
            TextDisplay(f"<:gear:1517576939097952496> **Settings for {self.username}**"),
            Separator(),
            Section("<:edit:1517497568421085256> User settings", accessory=self.user_button),
            Section("<:drawer:1517497564189036574> Guild settings", accessory=self.guild_button),
            Section("<:list:1517497572770451567> Channel settings", accessory=self.channel_button),
            Section("<:money:1517580310395486239> Economy settings", accessory=self.economy_button),
            Section("<:chalice:1517579767573123092> Level settings", accessory=self.level_button),
            Separator(),
            TextDisplay("Found a bug ? Report it in the [support server](https://discord.gg/FSBPvc9zqY)"),
            accent_color=self.color,
        )
        self.add_item(container)


class UserSettingsView(LayoutView):
    def __init__(self, user_id: int, current_color: str, current_pings: bool):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.current_color = current_color or "white"
        self.current_pings = current_pings
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
            await interaction.response.edit_message(view=UserSettingsView(self.user_id, self.current_color, self.current_pings))

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
            await interaction.response.edit_message(view=UserSettingsView(self.user_id, self.current_color, self.current_pings))

        self.color_select.callback = color_select_callback

        self.back_button = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="user_settings_back")

        async def back_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

        self.back_button.callback = back_callback

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **User settings**"),
            TextDisplay("Adjust your personal preferences below."),
            Separator(),
            Section(f"<:bell:1517497562184024275> Ping notifications: {'Enabled' if self.current_pings else 'Disabled'}", accessory=self.ping_button),
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
            await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

        self.back_button.callback = back_callback

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **Guild settings**"),
            TextDisplay("Adjust guild-wide behavior below."),
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
        await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

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
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        await interaction.response.send_message(
            f"<:approve:1517452125687513158> Use effect for **{item_name}** saved. Choose a role to grant when it is used. Press No to skip.",
            view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a role", item_name, settings_message, self.handle_use_role_selection, False),
            ephemeral=True,
        )

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
            await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
            if role_id is None:
                await interaction.response.send_message(
                    f"<:approve:1517452125687513158> Temp role setup skipped for **{item_name}**.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_modal(
                    EconomyTempRoleDurationModal(self.handle_temp_role_duration_submit, self.guild_id, item_name, settings_message)
                )
            return

        effect["role_id"] = role_id
        save_data(data)
        await self.refresh_settings_message(interaction, EconomySettingsView(self.user_id, self.guild_id, self.color), settings_message)
        if role_id is None:
            await interaction.response.send_message(
                f"<:approve:1517452125687513158> Role setup skipped for **{item_name}**. Choose a temporary role next, or press No to skip.",
                view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a temporary role", item_name, settings_message, self.handle_use_role_selection, True),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"<:approve:1517452125687513158> Role saved for **{item_name}**. Choose a temporary role next, or press No to skip.",
            view=EconomyRoleSelectionView(self.user_id, interaction.guild, "Choose a temporary role", item_name, settings_message, self.handle_use_role_selection, True),
            ephemeral=True,
        )

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
        await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

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

        if self.page == 1:
            self.welcome_button = Button(label="Remove" if guild_config.get("welcome_channel_id") else "Set", style=discord.ButtonStyle.primary, custom_id="channel_welcome_toggle")
            self.goodbye_button = Button(label="Remove" if guild_config.get("goodbye_channel_id") else "Set", style=discord.ButtonStyle.primary, custom_id="channel_goodbye_toggle")
            self.level_button = Button(label="Remove" if level_id else "Set", style=discord.ButtonStyle.primary, custom_id="channel_level_toggle")
            self.admin_button = Button(label=admin_label, style=discord.ButtonStyle.primary, custom_id="channel_admin_toggle")

            self.welcome_button.callback = self.handle_welcome_toggle
            self.goodbye_button.callback = self.handle_goodbye_toggle
            self.level_button.callback = self.handle_level_toggle
            self.admin_button.callback = self.handle_admin_toggle

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
        await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

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




# -------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.presences = True
    bot = NinnnUtils(intents=intents, shard_count=SHARD_COUNT)
    bot.run(TOKEN)