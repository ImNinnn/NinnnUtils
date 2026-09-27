import discord
from discord.ext import commands


class HelloWorldTestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='hello_world_test')
    async def hello_world_test(self, ctx: commands.Context):
        channel = self.bot.get_channel(1531804803875999896)
        if channel is None:
            return await ctx.send('Target channel not found.')
        await channel.send('hello world')
        await ctx.send('hello world sent to target channel.')


async def setup(bot: commands.Bot):
    await bot.add_cog(HelloWorldTestCog(bot))
