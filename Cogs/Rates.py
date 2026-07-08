from discord.ext.commands import Cog, Context, hybrid_group
from discord.app_commands import context_menu
from discord import app_commands, Interaction, Message
import random, discord

from Shared.Love import load_love_data, save_love_data


async def setup(bot):
    await bot.add_cog(Rates())

class Rates(Cog):
    @context_menu(name="Rizz Meter")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def rizz_menu(interaction: Interaction, message: Message):
        percentage = random.randint(0, 100)
        original_text = message.content if message.content else "*[Media or Embed]*"
        await interaction.response.send_message(
            f"> This message has **{percentage}%** Rizz.\n-# **{message.author.display_name}:** {original_text}")

    @context_menu(name="Cringe Meter")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def cringe_menu(interaction: Interaction, message: Message):
        percentage = random.randint(0, 100)
        original_text = message.content if message.content else "*[Media or Embed]*"
        await interaction.response.send_message(
            f"> This message is **{percentage}%** Cringe.\n-# **{message.author.display_name}:** {original_text}")

    @context_menu(name="Stupid Meter")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def stupid_menu(interaction: Interaction, message: Message):
        percentage = random.randint(0, 100)
        original_text = message.content if message.content else "*[Media or Embed]*"
        await interaction.response.send_message(
            f"> This message is **{percentage}%** Stupid.\n-# **{message.author.display_name}:** {original_text}")

    @context_menu(name="Lie Meter")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def lie_menu(interaction: Interaction, message: Message):
        percentage = random.randint(0, 100)
        original_text = message.content if message.content else "*[Media or Embed]*"
        await interaction.response.send_message(
            f"> This message is **{percentage}%** a Lie.\n-# **{message.author.display_name}:** {original_text}")

    @context_menu(name="Quote")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def quote_menu(interaction: Interaction, message: Message):
        quote_file = await create_quote_card(message)
        if quote_file is None:
            await interaction.response.send_message("Unable to create quote image right now.", ephemeral=True)
            return
        await interaction.response.send_message(file=quote_file)

    @hybrid_group(name="rate", description="Check the rates of someone", invoke_without_command=True)
    async def r(self, ctx): pass

    @r.command(name="love", description="Check the compatibility between two things or users")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(item1="The first person or thing", item2="The second person or thing")
    async def love(self, ctx: Context, item1: str, item2: str):
        love_data = load_love_data()
        guild_id = str(ctx.guild.id) if ctx.guild else "dm"
        if guild_id not in love_data:
            love_data[guild_id] = {}
        pair = sorted([item1.lower().strip(), item2.lower().strip()])
        match_key = f"{pair[0]}&{pair[1]}"
        if match_key in love_data[guild_id]:
            score = love_data[guild_id][match_key]
        else:
            score = random.randint(1, 100)
            love_data[guild_id][match_key] = score
            save_love_data(love_data)
        filled = max(0, int(score / 10))
        bar = "<:Square_Red:1517679897068306522>" * filled + "<:Square_Black:1517679889615032540>" * (10 - filled)
        embed = discord.Embed(title="Love Compatibility <:heart:1517577673763979344>", color=discord.Color.red())
        embed.add_field(name="Match", value=f"{item1} & {item2}", inline=False)
        embed.add_field(name="Compatibility", value=f"**{score}%**\n{bar}", inline=False)
        await ctx.send(embed=embed)

    @r.command(name="cool", description="Rate how cool someone is")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(username="The person or thing to rate")
    async def rate_cool(self, ctx: Context, username: str):
        love_data = load_love_data()
        guild_id = str(ctx.guild.id) if ctx.guild else "dm"
        if guild_id not in love_data:
            love_data[guild_id] = {}
        cool_key = f"cool_{username.lower().strip()}"
        if cool_key in love_data[guild_id]:
            score = love_data[guild_id][cool_key]
        else:
            score = random.randint(1, 100)
            love_data[guild_id][cool_key] = score
            save_love_data(love_data)
        filled = max(0, int(score / 10))
        bar = "<:Square_Yellow:1517679899769311302>" * filled + "<:Square_Black:1517679889615032540>" * (10 - filled)
        embed = discord.Embed(title="Coolness Rating <:spark:1517583248421552305>", color=discord.Color.yellow())
        embed.add_field(name="User", value=username, inline=False)
        embed.add_field(name="Coolness", value=f"**{score}%**\n{bar}", inline=False)
        await ctx.send(embed=embed)

    @r.command(name="gay", description="Rate how gay someone is")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(username="The person or thing to rate")
    async def rate_gay(self, ctx: Context, username: str):
        love_data = load_love_data()
        guild_id = str(ctx.guild.id) if ctx.guild else "dm"
        if guild_id not in love_data:
            love_data[guild_id] = {}
        gay_key = f"gay_{username.lower().strip()}"
        if gay_key in love_data[guild_id]:
            score = love_data[guild_id][gay_key]
        else:
            score = random.randint(1, 100)
            love_data[guild_id][gay_key] = score
            save_love_data(love_data)
        filled = max(0, int(score / 10))
        bar = "<:Square_Blue:1517679890932043897>" * filled + "<:Square_Black:1517679889615032540>" * (10 - filled)
        embed = discord.Embed(title="Gayness Rating <:rainbow:1518708398772846722>", color=discord.Color.blue())
        embed.add_field(name="User", value=username, inline=False)
        embed.add_field(name="Gayness", value=f"**{score}%**\n{bar}", inline=False)
        await ctx.send(embed=embed)
