import time
import discord

from Shared.Music import get_song_queue, play_guild_song, cleanup_now_playing_embed, get_now_playing_channel, \
    build_song_embed


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
