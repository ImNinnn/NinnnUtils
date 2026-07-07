from discord.ext.commands import Cog, Context, hybrid_group
from discord import app_commands
from main import YTDL_OPTIONS
import yt_dlp
from Shared.Music import *
import asyncio

async def setup(bot):
    await bot.add_cog(Music(bot))

class Music(Cog):
    def __init__(self, bot):
        self.bot = bot

    @hybrid_group(name="music", description="Music commands", invoke_without_command=True)
    async def v(self, ctx): pass

    @Cog.listener()
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

    @v.command(name="leave", description="Disconnect the bot from the voice channel")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def voice_leave(self, ctx: Context):
        voice_client = ctx.guild.voice_client
        if voice_client:
            guild_id = str(ctx.guild.id)
            queue = get_song_queue(guild_id)
            queue['tracks'].clear()
            queue['current_index'] = 0
            queue['loop'] = False
            queue['stop_action'] = None
            await cleanup_now_playing_embed(guild_id)
            await voice_client.disconnect()
            await ctx.send("<:wave:1517576345603936296> Disconnected from the voice channel and cleared the queue.")
        else:
            await ctx.send("<:disapprove:1517452151012589662> I'm not connected to a voice channel!", ephemeral=True)

    @v.command(name="play", description="Play a song from YouTube")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(
        youtube_url="The YouTube video link (required for add)"
    )
    async def play(
        self,
        ctx: Context,
        youtube_url: str = None
    ):
        guild_id = str(ctx.guild.id)
        queue = get_song_queue(guild_id)

        # if action == "add":
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("<:disapprove:1517452151012589662> You must be in a voice channel to add a song!", ephemeral=True)
            return
        if not youtube_url:
            await ctx.send("<:disapprove:1517452151012589662> Please provide a YouTube link to add.", ephemeral=True)
            return

        if ctx.interaction:
            await ctx.interaction.response.defer()
        voice_channel = ctx.author.voice.channel
        was_empty = len(queue['tracks']) == 0 or queue['current_index'] >= len(queue['tracks'])

        try:
            with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                video_title = info.get('title', 'Unknown Title')

            voice_client = ctx.guild.voice_client
            if voice_client is None:
                voice_client = await voice_channel.connect()
            elif voice_client.channel != voice_channel:
                await voice_client.move_to(voice_channel)

            queue['tracks'].append({
                'url': youtube_url,
                'title': video_title,
                'requested_by': ctx.author.display_name
            })

            if was_empty and not voice_client.is_playing() and not voice_client.is_paused():
                queue['current_index'] = len(queue['tracks']) - 1
                queue['now_playing_channel_id'] = ctx.channel.id
                if await play_guild_song(guild_id, voice_client):
                    await ctx.send(f"<:music:1517575582764765224> Now playing: **{video_title}** in {voice_channel.mention}!")
                    return
                await ctx.send(f"<:disapprove:1517452151012589662> Failed to start playback for **{video_title}**.")
                return
            
            await ctx.send(f"<:music:1517575582764765224> Added to queue: **{video_title}** (Position {len(queue['tracks'])})")

        except Exception as e:
            await ctx.send(f"<:disapprove:1517452151012589662> Failed to add song. Error: {e}")
        return

        # if action == "skip":

        # if action == "remove":

    @v.command(name="skip", description="Skip the current song")
    async def skip(self, ctx: Context):
        voice_client = ctx.guild.voice_client
        guild_id = str(ctx.guild.id)
        queue = get_song_queue(guild_id)

        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not voice_client or not voice_client.is_connected():
            await ctx.send("<:disapprove:1517452151012589662> I'm not connected to a voice channel.", ephemeral=True)
            return
        if not queue['tracks']:
            await ctx.send("<:disapprove:1517452151012589662> The queue is empty.", ephemeral=True)
            return

        if queue['current_index'] >= len(queue['tracks']):
            queue['current_index'] = len(queue['tracks']) - 1

        if queue['current_index'] + 1 < len(queue['tracks']):
            queue['current_index'] += 1
            queue['stop_action'] = 'manual'
            voice_client.stop()
            await ctx.send(f"<:next:1518977801057865224> Skipped to **{queue['tracks'][queue['current_index']]['title']}**.")
            await play_guild_song(guild_id, voice_client)
            return

        queue['current_index'] = len(queue['tracks'])
        queue['stop_action'] = 'manual'
        voice_client.stop()
        await cleanup_now_playing_embed(guild_id)
        await ctx.send("<:disapprove:1517452151012589662> No more songs in the queue. Playback stopped.")
        return
    
    # I just read the docs, this will be so handy!
    async def remove_autocomplete(self, interaction: discord.Interaction, current: str):
        ctx = await Context.from_interaction(interaction)
        guild_id = str(ctx.guild.id)
        queue = get_song_queue(guild_id)

        """JSON FORMAT:
        {
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
        }
        """

        tracks: list = queue.get("tracks")
        try:
            cur = tracks.copy().pop(current)
        except Exception:
            cur = None

        return [
            app_commands.Choice(name=song.get("title"), value=)
            for song in tracks if current.lower() in song.get("title", "0000000") or cur
        ]
    
    @v.command(name="remove", description="Remove a song from the queue")
    @app_commands.describe(position="The track for removal (or the position)")
    async def remove(self, ctx: Context, position: int):
        voice_client = ctx.guild.voice_client
        guild_id = str(ctx.guild.id)
        queue = get_song_queue(guild_id)

        if ctx.interaction:
            await ctx.interaction.response.defer()

        if position is None:
            await ctx.send("<:disapprove:1517452151012589662> Please provide the queue position to remove.", ephemeral=True)
            return
        if not queue['tracks']:
            await ctx.send("<:disapprove:1517452151012589662> The queue is empty.", ephemeral=True)
            return
        if position < 1 or position > len(queue['tracks']):
            await ctx.send("<:disapprove:1517452151012589662> Invalid queue position.", ephemeral=True)
            return

        song_index = position - 1
        removed = queue['tracks'].pop(song_index)
        if song_index < queue['current_index']:
            queue['current_index'] -= 1
        elif song_index == queue['current_index']:
            voice_client = ctx.guild.voice_client
            if voice_client and voice_client.is_connected() and (voice_client.is_playing() or voice_client.is_paused()):
                queue['stop_action'] = 'manual'
                voice_client.stop()
                if queue['current_index'] >= len(queue['tracks']):
                    await cleanup_now_playing_embed(guild_id)
                    await ctx.send(f"Removed **{removed['title']}** and stopped playback because the queue is now empty.")
                    return
                await ctx.send(f"Removed **{removed['title']}**. Now playing **{queue['tracks'][queue['current_index']]['title']}**.")
                await play_guild_song(guild_id, voice_client)
                return

        await ctx.send(f"Removed **{removed['title']}** from the queue.")
        return