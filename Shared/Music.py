from __future__ import annotations

import asyncio

import yt_dlp
from discord import Guild

from Views.Music import NowPlayingControlsView
from main import song_queues, YTDL_OPTIONS, FFMPEG_PATH, FFMPEG_OPTIONS
import discord, time

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

    # Calculate unix timestamps for Discord dynamic time formatting
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

async def cleanup_now_playing_embed(guild: Guild):
    queue = get_song_queue(guild.id)
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

    channel = guild.get_channel(channel_id)
    if not channel:
        return

    try:
        message = await channel.fetch_message(message_id)
        await message.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


def get_now_playing_channel(bot, queue: dict) -> discord.TextChannel | None:
    if not queue.get('now_playing_channel_id'):
        return None
    return bot.get_channel(queue['now_playing_channel_id'])


async def refresh_now_playing_embed(guild: Guild):
    queue = get_song_queue(str(guild.id))
    if not queue.get('now_playing_message_id'):
        return
    channel = get_now_playing_channel(guild, queue) # A guild can also be used to get a channel!
    if not channel:
        return
    embed = build_song_embed(str(guild.id))
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


async def update_now_playing_embed_loop(guild: Guild):
    queue = get_song_queue(str(guild.id))
    while True:
        await asyncio.sleep(10)
        if not queue.get('now_playing_message_id') or not queue.get('tracks'):
            break
        if queue['current_index'] >= len(queue['tracks']):
            break
        await refresh_now_playing_embed(guild)
    queue['now_playing_task'] = None


async def start_now_playing_embed(guild: Guild):
    queue = get_song_queue(str(guild.id))
    if not queue.get('tracks') or queue['current_index'] >= len(queue['tracks']):
        return
    if not queue.get('now_playing_channel_id'):
        return

    await cleanup_now_playing_embed(guild)
    channel = get_now_playing_channel(guild, queue)
    if not channel:
        return

    embed = build_song_embed(str(guild.id))
    if not embed:
        return

    try:
        view = queue.get('now_playing_view')
        if view is None:
            view = NowPlayingControlsView(str(guild.id))
            queue['now_playing_view'] = view
        else:
            view.update_button_states()

        message = await channel.send(embed=embed, view=view)
        queue['now_playing_message_id'] = message.id
        queue['now_playing_task'] = asyncio.create_task(update_now_playing_embed_loop(guild))
    except Exception:
        queue['now_playing_message_id'] = None
        queue['now_playing_task'] = None


async def play_guild_song(guild: Guild, voice_client: discord.VoiceClient) -> bool:
    queue = get_song_queue(str(guild.id))
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
            bot.loop.call_soon_threadsafe(asyncio.create_task, playback_ended(guild, error))

        voice_client.play(audio_source, after=after_play)
        queue['track_start_time'] = time.time()
        queue['accumulated_pause'] = 0.0
        queue['pause_started_at'] = None
        await start_now_playing_embed(guild)
        return True
    except Exception as e:
        print(f"Failed to start playback: {e}")
        return False

async def playback_ended(guild: Guild, error=None):
    queue = get_song_queue(str(guild.id))
    if queue.get('stop_action'):
        queue['stop_action'] = None
        return

    if queue['loop'] and queue['tracks']:
        voice_client = guild.voice_client if guild else None
        if voice_client and voice_client.is_connected():
            await play_guild_song(guild, voice_client)
        return

    is_last_track = queue['current_index'] + 1 >= len(queue['tracks'])
    if is_last_track:
        await refresh_now_playing_embed(guild)

    queue['current_index'] += 1
    if queue['current_index'] < len(queue['tracks']):
        voice_client = guild.voice_client if guild else None
        if voice_client and voice_client.is_connected():
            await play_guild_song(guild, voice_client)
        return

    return
