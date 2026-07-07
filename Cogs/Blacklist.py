from discord.ext.commands import Cog
from main import BLACKLISTED_GUILDS
from dotenv import load_dotenv
import os

async def setup(bot):
    await bot.add_cog(Blacklist(bot))

class Blacklist(Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_guild_join(self, guild):
        load_dotenv(override=True)
        raw_blacklist = os.getenv('SERVER_BLACKLIST', '')
        BLACKLISTED_GUILDS = [int(sid.strip()) for sid in raw_blacklist.split(',') if sid.strip().isdigit()]
        if guild.id in BLACKLISTED_GUILDS:
            print(f"Joined blacklisted guild: {guild.name} ({guild.id}). Leaving immediately...")
            await guild.leave()

    async def blacklist_startup_cleanup(self):
        await self.bot.wait_until_ready()
        print("Running startup blacklist check...")
        print('-------------------------------------')
        for guild in self.bot.guilds:
            if guild.id in BLACKLISTED_GUILDS:
                print(f"Found blacklisted guild on startup: {guild.name} ({guild.id}). Leaving...")
                try:
                    await guild.leave()
                except Exception as e:
                    print(f"Failed to leave {guild.name}: {e}")
