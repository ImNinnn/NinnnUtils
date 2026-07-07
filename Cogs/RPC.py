from discord.ext.commands import Cog
from discord.ext import tasks
from dotenv import load_dotenv
from Shared.RPC import *
import os, discord, asyncio

async def setup(bot):
    await bot.add_cog(RPC(bot))

class RPC(Cog):
    def __init__(self, bot): self.bot = bot

    @tasks.loop(seconds=15)
    async def update_presence(self):
        global presence_toggle, presence_index

        load_dotenv(override=True)
        raw_blacklist = os.getenv('SERVER_BLACKLIST', '')
        BLACKLISTED_GUILDS = [int(sid.strip()) for sid in raw_blacklist.split(',') if sid.strip().isdigit()]

        for guild in self.bot.guilds:
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

        # cycle between three presence messages
        online_users = sum(
            len([m for m in guild.members if m.status != discord.Status.offline and not m.bot])
            for guild in self.bot.guilds
        )

        if presence_index == 0:
            activity_text = f"ver{VERSION} ┃ {online_users} online users"
        elif presence_index == 1:
            activity_text = f"ver{VERSION} ┃ {ACTIVITY_TEXT}"
        else:
            activity_text = f"ver{VERSION} ┃ alt{VERSION_ALTERNATE}"

        activity = discord.Activity(type=discord.ActivityType.watching, name=activity_text)

        for shard_id, shard in self.bot.shards.items():
            await self.bot.change_presence(
                activity=activity,
                status=discord.Status.online,
                shard_id=shard_id,
            )

        sync_local_rpc(activity_text)

        presence_index = (presence_index + 1) % 3


    @update_presence.before_loop
    async def before_update_presence(self):
        await self.bot.wait_until_ready()
        sync_local_rpc("App just started... .. .")
        startup_activity = discord.Streaming(
            name="App just started... .. .",
            url="https://www.twitch.tv/imninnn"
        )
        for shard_id in self.bot.shards:
            await self.bot.change_presence(activity=startup_activity, shard_id=shard_id)
        await asyncio.sleep(30)
