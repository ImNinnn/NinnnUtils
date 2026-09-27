"""Music playback: /song queue player and /voice-leave."""

import asyncio
import os
import re
import shutil
import time
import traceback

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Container, Modal, Section, Separator, TextDisplay, TextInput, Thumbnail

from utils.formatting import format_duration
from utils.views import TimeoutDisabledLayoutView


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


def _extract_info(url: str) -> dict | None:
    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
        return ydl.extract_info(url, download=False)


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


class SongRemoveModal(Modal):
    def __init__(self, cog: "MusicCog", guild_id: str | int):
        super().__init__(title="Remove queued song")
        self.cog = cog
        self.guild_id = str(guild_id)
        self.song_target = TextInput(
            label="Song number or title",
            placeholder="Example: 2 or my favorite song",
            required=True,
            max_length=120
        )
        self.add_item(self.song_target)

    async def on_submit(self, interaction: discord.Interaction):
        queue = self.cog.get_song_queue(self.guild_id)
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
            await self.cog.play_guild_song(self.guild_id, voice_client)

        await interaction.response.send_message(f"<:trash:1517497581058527404> Removed **{removed_track.get('title', 'Unknown Title')}** from the queue.", ephemeral=True)
        await self.cog.refresh_song_message(self.guild_id)


class SongControlsView(TimeoutDisabledLayoutView):
    def __init__(self, cog: "MusicCog", guild_id: str | int):
        super().__init__()
        self.cog = cog
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
        main_items = self.cog.build_song_container(self.guild_id)
        if main_items is not None:
            container_parts.extend(main_items)
        else:
            container_parts.append(TextDisplay("<:disapprove:1517452151012589662> Nothing is queued right now."))

        self.update_button_states()
        self.add_item(Container(*container_parts, accent_color=discord.Color.orange()))
        self.add_item(discord.ui.ActionRow(self.previous_button, self.next_button, self.pause_button, self.loop_button, self.remove_button))

    def update_button_states(self):
        queue = self.cog.get_song_queue(self.guild_id)
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
        queue = self.cog.get_song_queue(self.guild_id)
        if not queue.get('tracks'):
            await interaction.response.send_message("<:disapprove:1517452151012589662> There is no queue to go back through.", ephemeral=True)
            return
        if queue['current_index'] <= 0:
            await interaction.response.send_message("<:disapprove:1517452151012589662> There is no previous song.", ephemeral=True)
            return

        queue['current_index'] -= 1
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            self.cog.stop_without_advancing(self.guild_id, voice_client)
        await interaction.response.send_message(f"<:prev:1518977803092234331> Now playing **{queue['tracks'][queue['current_index']]['title']}**.", ephemeral=True)
        if voice_client and voice_client.is_connected():
            await self.cog.play_guild_song(self.guild_id, voice_client)
        await self.cog.refresh_song_message(self.guild_id)

    async def next_song(self, interaction: discord.Interaction):
        queue = self.cog.get_song_queue(self.guild_id)
        if not queue.get('tracks'):
            await interaction.response.send_message("<:disapprove:1517452151012589662> The queue is empty.", ephemeral=True)
            return
        if queue['current_index'] + 1 >= len(queue['tracks']):
            queue['current_index'] = len(queue['tracks']) - 1
            if interaction.guild and interaction.guild.voice_client and interaction.guild.voice_client.is_connected():
                self.cog.stop_without_advancing(self.guild_id, interaction.guild.voice_client)
            await interaction.response.send_message("<:disapprove:1517452151012589662> No more songs in the queue.", ephemeral=True)
            await self.cog.refresh_song_message(self.guild_id)
            return

        queue['current_index'] += 1
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            self.cog.stop_without_advancing(self.guild_id, voice_client)
        await interaction.response.send_message(f"<:next:1518977801057861643> Skipping to **{queue['tracks'][queue['current_index']]['title']}**.", ephemeral=True)
        if voice_client and voice_client.is_connected():
            await self.cog.play_guild_song(self.guild_id, voice_client)
        await self.cog.refresh_song_message(self.guild_id)

    async def pause_song(self, interaction: discord.Interaction):
        queue = self.cog.get_song_queue(self.guild_id)
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
            await self.cog.refresh_song_message(self.guild_id)
            return
        if not voice_client.is_playing():
            await interaction.response.send_message("<:disapprove:1517452151012589662> Nothing is playing right now.", ephemeral=True)
            return
        voice_client.pause()
        queue['pause_started_at'] = time.time()
        await interaction.response.send_message("<:pause:1517497575219920986> Paused the song.", ephemeral=True)
        await self.cog.refresh_song_message(self.guild_id)

    async def toggle_loop(self, interaction: discord.Interaction):
        queue = self.cog.get_song_queue(self.guild_id)
        queue['loop'] = not queue.get('loop', False)
        await interaction.response.send_message(f"<:loop:1518977798939742449> Looping is now {'enabled' if queue['loop'] else 'disabled'}.", ephemeral=True)
        await self.cog.refresh_song_message(self.guild_id)

    async def remove_song(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SongRemoveModal(self.cog, self.guild_id))


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.song_queues: dict[str, dict] = {}

    async def cog_unload(self):
        for queue in self.song_queues.values():
            task = queue.get('ui_refresh_task')
            if task is not None and not task.done():
                task.cancel()

    # ---------------------------------------------------------------- queue state

    def get_song_queue(self, guild_id: str | int) -> dict:
        key = str(guild_id)
        queue = self.song_queues.setdefault(key, {
            'tracks': [],
            'current_index': 0,
            'loop': False,
            'pause_started_at': None,
            'track_start_time': None,
            'accumulated_pause': 0.0,
            'message_id': None,
            'channel_id': None,
            'ui_refresh_task': None,
            'skip_advance': 0,
        })
        return queue

    def _get_guild(self, guild_id: str | int) -> discord.Guild | None:
        return self.bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None

    def stop_without_advancing(self, guild_id: str | int, voice_client: discord.VoiceClient) -> None:
        # Stopping triggers the `after` callback; mark it so playback_ended doesn't also
        # move the queue forward when a button already picked the next track.
        if voice_client.is_playing() or voice_client.is_paused():
            self.get_song_queue(guild_id)['skip_advance'] += 1
        voice_client.stop()

    # ---------------------------------------------------------------- player UI

    def build_song_container(self, guild_id: str | int) -> list | None:
        queue = self.get_song_queue(guild_id)
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

    def _get_view(self, guild_id: str | int) -> SongControlsView:
        queue = self.get_song_queue(guild_id)
        view = queue.get('view') or SongControlsView(self, guild_id)
        view.rebuild()
        queue['view'] = view
        return view

    async def ensure_song_ui_message(self, guild_id: str | int, interaction: discord.Interaction | None = None, member: discord.Member | None = None) -> discord.Message | None:
        queue = self.get_song_queue(guild_id)
        guild = self._get_guild(guild_id)
        if guild is None:
            return None

        if queue.get('message_id') and queue.get('channel_id'):
            channel = self.bot.get_channel(queue['channel_id'])
            if channel is not None:
                try:
                    message = await channel.fetch_message(queue['message_id'])
                    await message.edit(view=self._get_view(guild_id))
                    return message
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    queue['message_id'] = None
                    queue['channel_id'] = None

        send_channel = get_song_ui_channel(guild, interaction=interaction, member=member)
        if send_channel is None:
            return None

        view = self._get_view(guild_id)
        try:
            message = await send_channel.send(view=view)
            queue['message_id'] = message.id
            queue['channel_id'] = send_channel.id
            if queue.get('ui_refresh_task') is None or queue['ui_refresh_task'].done():
                queue['ui_refresh_task'] = asyncio.create_task(self._song_ui_refresh_loop(guild_id))
            return message
        except Exception:
            print("[Song UI] Failed to send player UI")
            traceback.print_exc()
            return None

    async def refresh_song_message(self, guild_id: str | int):
        queue = self.get_song_queue(guild_id)
        guild = self._get_guild(guild_id)
        if guild is not None and (guild.voice_client is None or not guild.voice_client.is_connected()):
            await self._cleanup_song_message(guild_id)
            return
        if not queue.get('message_id') or not queue.get('channel_id'):
            return
        channel = self.bot.get_channel(queue['channel_id'])
        if not channel:
            return
        try:
            message = await channel.fetch_message(queue['message_id'])
            await message.edit(view=self._get_view(guild_id))
        except Exception:
            print("[Song UI] Failed to refresh player UI")
            traceback.print_exc()
            queue['message_id'] = None
            queue['channel_id'] = None

    async def _song_ui_refresh_loop(self, guild_id: str | int):
        while True:
            await asyncio.sleep(5)
            queue = self.get_song_queue(guild_id)
            if not queue.get('tracks'):
                break
            if not queue.get('message_id') or not queue.get('channel_id'):
                break
            await self.refresh_song_message(guild_id)

        queue = self.get_song_queue(guild_id)
        queue['ui_refresh_task'] = None

    async def _cleanup_song_message(self, guild_id: str | int):
        queue = self.get_song_queue(guild_id)
        task = queue.get('ui_refresh_task')
        if task is not None and not task.done() and task is not asyncio.current_task():
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
            channel = self.bot.get_channel(channel_id)
            if channel:
                message = await channel.fetch_message(message_id)
                await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    async def reset_song_queue_for_disconnect(self, guild_id: str | int):
        queue = self.get_song_queue(guild_id)
        queue['tracks'] = []
        queue['current_index'] = 0
        queue['track_start_time'] = None
        queue['pause_started_at'] = None
        queue['accumulated_pause'] = 0.0
        queue['loop'] = False
        await self._cleanup_song_message(guild_id)

    # ---------------------------------------------------------------- playback

    async def _search_track(self, query: str) -> dict | None:
        if not query or not query.strip():
            return None
        url = query.strip()
        if not re.match(r'https?://', url):
            url = f"ytsearch1:{url}"
        info = await asyncio.to_thread(_extract_info, url)

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

    async def play_guild_song(self, guild_id: str | int, voice_client: discord.VoiceClient) -> bool:
        queue = self.get_song_queue(guild_id)
        if not queue.get('tracks'):
            return False
        if queue['current_index'] >= len(queue['tracks']):
            queue['current_index'] = max(0, len(queue['tracks']) - 1)
        track = queue['tracks'][queue['current_index']]

        try:
            info = await asyncio.to_thread(_extract_info, track['url'])
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

            # The extraction above awaits, so another play may have started meanwhile.
            if voice_client.is_playing() or voice_client.is_paused():
                self.stop_without_advancing(guild_id, voice_client)

            loop = asyncio.get_running_loop()

            def after_play(error):
                if error:
                    print(f"[song] playback error: {error}")
                asyncio.run_coroutine_threadsafe(self.playback_ended(guild_id), loop)

            voice_client.play(audio_source, after=after_play)
            queue['track_start_time'] = time.time()
            queue['accumulated_pause'] = 0.0
            queue['pause_started_at'] = None
            await self.refresh_song_message(guild_id)
            return True
        except Exception as exc:
            print(f"[song] failed to start playback: {exc}")
            return False

    async def playback_ended(self, guild_id: str | int):
        queue = self.get_song_queue(guild_id)
        if queue.get('skip_advance', 0) > 0:
            queue['skip_advance'] -= 1
            return

        if not queue.get('tracks'):
            await self._cleanup_song_message(guild_id)
            return

        if queue.get('loop'):
            guild = self._get_guild(guild_id)
            if guild and guild.voice_client and guild.voice_client.is_connected():
                await self.play_guild_song(guild_id, guild.voice_client)
            return

        if queue['current_index'] + 1 < len(queue['tracks']):
            queue['current_index'] += 1
            guild = self._get_guild(guild_id)
            if guild and guild.voice_client and guild.voice_client.is_connected():
                await self.play_guild_song(guild_id, guild.voice_client)
            return

        queue['current_index'] = len(queue['tracks']) - 1
        queue['track_start_time'] = None
        queue['pause_started_at'] = None
        queue['accumulated_pause'] = 0.0
        await self.refresh_song_message(guild_id)

    # ---------------------------------------------------------------- listeners

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id == self.bot.user.id and before.channel is not None and after.channel is None:
            await self.reset_song_queue_for_disconnect(member.guild.id)
            return

        voice_client = member.guild.voice_client
        if not voice_client:
            return
        if before.channel and before.channel.id == voice_client.channel.id:
            human_members = [m for m in voice_client.channel.members if not m.bot]
            if len(human_members) == 0:
                print(f"Voice channel empty in {member.guild.name}. Starting 30s leave timer...")
                await asyncio.sleep(30)
                if voice_client.is_connected() and voice_client.channel:
                    current_humans = [m for m in voice_client.channel.members if not m.bot]
                    if len(current_humans) == 0:
                        await self.reset_song_queue_for_disconnect(member.guild.id)
                        await voice_client.disconnect()
                        print(f"Left empty voice channel in {member.guild.name} after 30 seconds.")

    # ---------------------------------------------------------------- commands

    @app_commands.command(name="song", description="Play a song or open the current queue UI")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.describe(query="Song name or YouTube URL to play. Leave blank to show the current player.")
    async def song(self, interaction: discord.Interaction, query: str | None = None):
        await interaction.response.defer()

        if interaction.guild is None:
            await interaction.followup.send("This command can only be used in a server voice channel.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        queue = self.get_song_queue(guild_id)

        if query:
            if interaction.user.voice is None or interaction.user.voice.channel is None:
                await interaction.followup.send("<:disapprove:1517452151012589662> Join a voice channel first.", ephemeral=True)
                return

            channel = interaction.user.voice.channel
            voice_client = interaction.guild.voice_client
            try:
                if voice_client is None:
                    await channel.connect()
                    voice_client = interaction.guild.voice_client
                elif voice_client.channel != channel:
                    await voice_client.move_to(channel)
            except (discord.ClientException, discord.Forbidden, asyncio.TimeoutError) as exc:
                print(f"[song] failed to join voice: {exc}")
                voice_client = None

            if not voice_client:
                await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't join the voice channel.", ephemeral=True)
                return

            track = await self._search_track(query)
            if not track:
                await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't find that song.", ephemeral=True)
                return
            track['requested_by'] = str(interaction.user)
            queue['tracks'].append(track)

            if not voice_client.is_playing() and not voice_client.is_paused():
                # Nothing is playing (fresh queue, or the previous queue already finished):
                # start from the song that was just added.
                queue['current_index'] = len(queue['tracks']) - 1
                await self.play_guild_song(guild_id, voice_client)

            await interaction.followup.send(f"<:music:1517575582764765224> Added **{track['title']}** to the queue.", ephemeral=False)
            await self.ensure_song_ui_message(guild_id, interaction=interaction, member=interaction.user)
            return

        if not queue.get('tracks'):
            await interaction.followup.send("<:disapprove:1517452151012589662> There is nothing in the queue yet. Try /song <song name or URL>.", ephemeral=True)
            return

        message = await self.ensure_song_ui_message(guild_id, interaction=interaction, member=interaction.user)
        if message is None:
            await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't find a text channel to post the player into.", ephemeral=True)
            return

        send_channel = self.bot.get_channel(queue['channel_id']) if queue.get('channel_id') else None
        if send_channel is not None:
            await interaction.followup.send(f"<:music:1517575582764765224> Now playing in {send_channel.mention}.", ephemeral=True)
        else:
            await interaction.followup.send("<:music:1517575582764765224> The player is live in the current voice text channel.", ephemeral=True)

    @app_commands.command(name="voice-leave", description="Leave the current voice channel")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def voice_leave(self, interaction: discord.Interaction):
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

        await self.reset_song_queue_for_disconnect(guild_id)
        if voice_client.is_connected():
            self.stop_without_advancing(guild_id, voice_client)
            await voice_client.disconnect()

        await interaction.response.defer()
        await interaction.followup.send("<:leave:1518977801485588083> Left the voice channel.")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
