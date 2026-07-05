from discord.ext.commands import Cog, Context, hybrid_group
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

    @bot.tree.command(name="leave", description="Disconnect the bot from the voice channel")
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
