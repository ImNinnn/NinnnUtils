from discord.ext.commands import Cog, Context, hybrid_group
import asyncio

async def setup(bot):
    await bot.add_cog(Voice(bot))

class Voice(Cog):
    def __init__(self, bot):
        self.bot = bot

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
