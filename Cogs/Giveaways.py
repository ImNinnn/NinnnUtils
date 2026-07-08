from datetime import datetime, timezone

from discord.ext.commands import Cog
from discord.ext import tasks

from Shared.Giveaways import load_giveaway_data, finalize_giveaway
from Views.Giveaways import GiveawayView


async def setup(bot):
    await bot.add_cog(Giveaways(bot))

class Giveaways(Cog):
    def __init__(self, bot):
        self.bot = bot

    @tasks.loop(minutes=1)
    async def giveaway_loop(self):
        data = load_giveaway_data()
        if not data:
            return

        now = int(datetime.now(timezone.utc).timestamp())
        for giveaway_id, giveaway in list(data.items()):
            if giveaway.get('status') != 'active':
                continue
            if int(giveaway.get('end_time', 0)) <= now:
                await finalize_giveaway(self.bot, giveaway_id, giveaway)

    @tasks.loop(seconds=30)
    async def giveaway_refresh_loop(self):
        data = load_giveaway_data()
        if not data:
            return

        for giveaway_id, giveaway in list(data.items()):
            if giveaway.get('status') != 'active':
                continue

            channel = self.bot.get_channel(int(giveaway['channel_id'])) if giveaway.get('channel_id') else None
            if not channel or not giveaway.get('message_id'):
                continue

            try:
                message = await channel.fetch_message(int(giveaway['message_id']))
                await message.edit(view=GiveawayView(self.bot, giveaway_id, giveaway))
            except Exception:
                pass

    @giveaway_loop.before_loop
    async def before_giveaway_loop(self):
        await self.bot.wait_until_ready()