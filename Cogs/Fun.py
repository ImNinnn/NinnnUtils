import asyncio
from datetime import datetime

import discord
from discord.ext.commands import Cog, Context, hybrid_command, hybrid_group
from discord import app_commands
import random

from Shared.Data import load_data, save_data
from Shared.User import get_user_data
from Views.Mines import MinesGameView
from Views.Towers import TowersGameView
from Views.Work import WorkGameView
from main import active_minigame_users, WORK_DIFFICULTY_SETTINGS, work_cooldowns


async def setup(bot):
    await bot.add_cog(Fun())

class Fun(Cog):
    @hybrid_group(name="fun", description="Fun commands", invoke_without_command=True)
    async def f(self, ctx): pass
    
    @hybrid_group(name="game", description="Game commands", invoke_without_command=True)
    async def g(self, ctx: Context): pass

    @hybrid_command(name="roll", description="Roll a 6-sided die")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def roll(self, ctx: Context):
        result = random.randint(1, 6)
        await ctx.send(f"🎲 You rolled a **{result}**!")

    @hybrid_command(name="random", description="Pick a random number between two values")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(min_value="The lowest number", max_value="The highest number")
    async def random_cmd(self, ctx: Context, min_value: int, max_value: int):
        low, high = min(min_value, max_value), max(min_value, max_value)
        result = random.randint(low, high)
        await ctx.send(
            f"<:list:1517497572770451567> Your random number between **{low}** and **{high}** is: **{result}**"
        )

    @hybrid_command(name="say", description="Make the bot say something")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def say(self, ctx: Context, message: str):
        await ctx.send(message)

    @g.group(name="classic", description="Classic fun command", invoke_without_command=True)
    async def c(self, ctx: Context): pass

    @c.command(name="slot", description="Spin the slot machine!")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def slot(self, ctx: Context):
        emojis = ['🍒', '🍎', '🍇', '💎', '<:bell:1517497562184024275>', '🍋']
        msg = await ctx.send("🎰 **Spinning...**")
        for _ in range(3):
            e1, e2, e3 = (random.choice(emojis) for _ in range(3))
            await msg.edit(content=f"🎰 | {e1} | {e2} | {e3} |")
            await asyncio.sleep(0.5)
        final_e1, final_e2, final_e3 = (random.choice(emojis) for _ in range(3))
        if final_e1 == final_e2 == final_e3:
            result_msg = f"🎰 **JACKPOT!** You won!\n\n| {final_e1} | {final_e2} | {final_e3} |"
        else:
            result_msg = f"🎰 Slot Machine:\n\n| {final_e1} | {final_e2} | {final_e3} |\n\nBetter luck next time!"
        await msg.edit(content=result_msg)

    @c.command(name="coinflip", description="Flips a coin and shows Heads or Tails")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def coinflip(self, ctx: Context):
        result = random.choice(["Heads", "Tails"])
        await ctx.send(f"<:coin:1518351100783231138> The coin landed on: **{result}**!")

    @g.command(name="slot", description="Play the economy slot machine and wager money")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def game_slot(self, ctx: Context, amount: int):
        if amount <= 0:
            return await ctx.send(
                "<:disapprove:1517452151012589662> Bet amount must be greater than 0.", ephemeral=True)

        data = load_data()
        guild_id = str(ctx.guild.id)
        user_data = get_user_data(data, guild_id, str(ctx.author.id))
        before_balance = user_data["balance"]

        if before_balance < amount:
            return await ctx.send(
                "<:disapprove:1517452151012589662> You don't have enough money to place that bet.", ephemeral=True)

        emojis = ['🍒', '🍎', '🍇', '💎', '🔔', '🍋']
        e1, e2, e3 = (random.choice(emojis) for _ in range(3))

        if e1 == e2 == e3:
            user_data["balance"] += amount * 10
            result_text = f"<:chalice:1517579767573123092> **JACKPOT!** You won **${amount * 10}**!"
            color = discord.Color.green()
        else:
            user_data["balance"] -= amount
            result_text = f"<:money:1517580310395486239> You lost **${amount}**. Better luck next time!"
            color = discord.Color.red()

        save_data(data)

        embed = discord.Embed(title="<:777:1518352060574208031> Economy Slot Machine",
                              description=f"Bet: **${amount}**", color=color)
        embed.add_field(name="Result", value=f"| {e1} | {e2} | {e3} |", inline=False)
        embed.add_field(name="Outcome", value=result_text, inline=False)
        embed.set_footer(text=f"Before: ${before_balance} • After: ${user_data['balance']}")
        await ctx.send(embed=embed)

    @g.command(name="coinflip", description="Play coinflip and wager money")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def game_coinflip(self, ctx: Context, amount: int):
        if amount <= 0:
            return await ctx.send(
                "<:disapprove:1517452151012589662> Bet amount must be greater than 0.", ephemeral=True)

        data = load_data()
        guild_id = str(ctx.guild.id)
        user_data = get_user_data(data, guild_id, str(ctx.author.id))
        before_balance = user_data["balance"]

        if before_balance < amount:
            return await ctx.send(
                "<:disapprove:1517452151012589662> You don't have enough money to place that bet.", ephemeral=True)

        result = random.choice(["heads", "tails"])
        if result == "heads":
            user_data["balance"] += amount
            result_text = f"<:chalice:1517579767573123092> You won **${amount}**! The coin landed on **Heads**."
            color = discord.Color.green()
        else:
            user_data["balance"] -= amount
            result_text = f"<:money:1517580310395486239> You lost **${amount}**. The coin landed on **Tails**."
            color = discord.Color.red()

        save_data(data)

        embed = discord.Embed(title="<:coin:1518351100783231138> Coin Flip", description=f"Bet: **${amount}**",
                              color=color)
        embed.add_field(name="Result", value=result_text, inline=False)
        embed.set_footer(text=f"Before: ${before_balance} • After: ${user_data['balance']}")
        await ctx.send(embed=embed)

    @g.command(name="mines", description="Play minesweeper and wager money")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def game_mines(self, ctx: Context, amount: int, mines: int):
        if amount <= 0:
            return await ctx.send(
                "<:disapprove:1517452151012589662> Bet amount must be greater than 0.", ephemeral=True)
        if mines < 3 or mines > 10:
            return await ctx.send(
                "<:disapprove:1517452151012589662> Number of mines must be between 3 and 10.", ephemeral=True)

        data = load_data()
        guild_id = str(ctx.guild.id)
        user_data = get_user_data(data, guild_id, str(ctx.author.id))
        before_balance = user_data["balance"]

        if ctx.author.id in active_minigame_users:
            return await ctx.send(
                "<:disapprove:1517452151012589662> You already have an active minigame. Finish or wait for it to time out before starting another.",
                ephemeral=True)

        if before_balance < amount:
            return await ctx.send(
                "<:disapprove:1517452151012589662> You don't have enough money to place that bet.", ephemeral=True)

        user_data["balance"] -= amount
        save_data(data)
        view = MinesGameView(amount=amount, mines=mines, guild_id=guild_id, user_id=ctx.author.id,
                             before_balance=before_balance)
        active_minigame_users.add(ctx.author.id)
        msg = await ctx.send(embed=view.embed, view=view)
        view.message = msg

    @g.command(name="towers", description="Play tower gamble and wager money")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def game_towers(self, ctx: Context, amount: int):
        if amount <= 0:
            return await ctx.send(
                "<:disapprove:1517452151012589662> Bet amount must be greater than 0.", ephemeral=True)

        data = load_data()
        guild_id = str(ctx.guild.id)
        user_data = get_user_data(data, guild_id, str(ctx.author.id))
        before_balance = user_data["balance"]

        if ctx.author.id in active_minigame_users:
            return await ctx.send(
                "<:disapprove:1517452151012589662> You already have an active minigame. Finish or wait for it to time out before starting another.",
                ephemeral=True)

        if before_balance < amount:
            return await ctx.send(
                "<:disapprove:1517452151012589662> You don't have enough money to place that bet.", ephemeral=True)

        user_data["balance"] -= amount
        save_data(data)
        view = TowersGameView(amount=amount, guild_id=guild_id, user_id=ctx.author.id,
                              before_balance=before_balance)
        active_minigame_users.add(ctx.author.id)
        msg = await ctx.send(embed=view.embed, view=view)
        view.message = msg

    @g.command(name="work", description="Work to earn money (get 1 of 3 random jobs, 2 hour cooldown)")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(difficulty="Choose the work difficulty")
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name="Easy", value="easy"),
            app_commands.Choice(name="Normal", value="normal"),
            app_commands.Choice(name="Hard", value="hard"),
        ]
    )
    async def game_work(self, ctx: Context, difficulty: str = "normal"):
        difficulty = difficulty.lower().strip()
        if difficulty not in WORK_DIFFICULTY_SETTINGS:
            difficulty = "normal"

        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)
        cooldown_key = f"{guild_id}_{user_id}"

        now = datetime.now()
        if cooldown_key in work_cooldowns:
            last_use = work_cooldowns[cooldown_key]
            elapsed = (now - last_use).total_seconds()
            remaining = 7200 - elapsed

            if remaining > 0:
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)
                return await ctx.send(
                    f"<:timer:1517996239583576194> You can work again in **{minutes}m {seconds}s**.",
                    ephemeral=True
                )

        data = load_data()
        user_data = get_user_data(data, guild_id, user_id)

        job_type = random.choice(["developer", "farmer", "math"])
        amount = 0

        work_cooldowns[cooldown_key] = now

        view = WorkGameView(job_type, guild_id, ctx.author.id, amount, difficulty)
        msg = await ctx.send(embed=view.embed, view=view)
        view.message = msg