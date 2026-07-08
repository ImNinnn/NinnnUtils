import asyncio
import random

from discord.ext.commands import Cog, Context, hybrid_group, has_permissions
from discord import app_commands
import discord

from LowerLeveled.items import normalize_item, find_item_key
from Shared.Data import load_data, save_data
from Shared.Errors import add_bot_error_entry
from Shared.Guilds import get_guild_data
from Shared.Inventory import inventory_add, inventory_remove, inventory_count
from Shared.Leveling import add_xp
from Shared.User import get_user_data, format_user_reference
from Views.Shop import ShopView


async def setup(bot): await bot.add_cog(Economy(bot))

class Economy(Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @hybrid_group(name="eco", description="Economy related commands", invoke_without_command=True)
    async def e(self, ctx: Context): pass

    @e.command(name="leaderboard", description="Show the server economy leaderboard")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_leaderboard(self, ctx: Context, limit: int = 10):
        if limit <= 0:
            return await ctx.send(
                "<:disapprove:1517452151012589662> Limit must be greater than 0.", ephemeral=True)

        data = load_data()
        guild = get_guild_data(data, str(ctx.guild.id))
        users = guild.get("users", {})
        if not users:
            return await ctx.send("No economy data for this server.", ephemeral=True)

        leaderboard = []
        for uid, udata in users.items():
            balance = udata.get("balance", 0)
            leaderboard.append((uid, balance))

        leaderboard.sort(key=lambda x: x[1], reverse=True)
        top = leaderboard[:limit]

        description_lines = []
        for idx, (uid, bal) in enumerate(top, start=1):
            try:
                member = await ctx.guild.fetch_member(int(uid))
                name = member.display_name
            except Exception:
                name = f"User left server (`{uid}`)"
            description_lines.append(f"`#{idx}` **{name}** - ${bal}")

        embed = discord.Embed(
            title=f"<:chalice:1517579767573123092> Economy Standings Leaderboard - {ctx.guild.name}",
            color=discord.Color.gold())
        embed.description = "\n".join(description_lines)
        await ctx.send(embed=embed)

    @e.group(name="balance", description="Check your balance or another user's balance")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(user="The user whose balance you want to check")
    async def eco_balance(self, ctx: Context, user: discord.Member = None):
        target = user or ctx.author
        data = load_data()
        money = data.get(str(ctx.guild.id), {}).get("users", {}).get(str(target.id), {}).get("balance", 0)
        await ctx.send(
            f"<:money:1517580310395486239> {target.display_name}'s balance: **${money}**")

    @e.command(name="daily", description="Claim your daily reward")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.checks.cooldown(1, 86400, key=lambda i: (i.user.id, i.guild.id))
    async def eco_daily(self, ctx: Context):
        data = load_data()
        user_data = get_user_data(data, str(ctx.guild.id), str(ctx.author.id))
        earnings = random.randint(150, 200)
        user_data["balance"] += earnings
        save_data(data)
        await ctx.send(
            f"<:money:1517580310395486239> You claimed your daily reward and earned **${earnings}**!")

    @e.command(name="pay", description="Pay another user from your balance")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_pay(self, ctx: Context, user: discord.Member, amount: int):
        if amount <= 0:
            return await ctx.send(
                "<:disapprove:1517452151012589662> Amount must be greater than 0.", ephemeral=True)
        data = load_data()
        guild_id = str(ctx.guild.id)
        sender_data = get_user_data(data, guild_id, str(ctx.author.id))
        receiver_data = get_user_data(data, guild_id, str(user.id))
        if sender_data["balance"] < amount:
            return await ctx.send(
                "<:disapprove:1517452151012589662> You don't have enough money!", ephemeral=True)
        sender_data["balance"] -= amount
        receiver_data["balance"] += amount
        save_data(data)
        await ctx.send(
            f"<:approve:1517452125687513158> Successfully sent **${amount}** to {format_user_reference(user)}!")

    @e.command(name="shop", description="View the server shop")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_shop(self, ctx: Context):
        data = load_data()
        shop_items = data.get(str(ctx.guild.id), {}).get("shop", {})
        if not shop_items:
            await ctx.send("The shop is currently empty!")
            return

        view = ShopView(shop_items, str(ctx.guild.id), str(ctx.author.id))
        await ctx.send(view=view)

    @e.group(name="inventory", description="Check your inventory or another user's inventory")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(user="The user whose inventory you want to check")
    async def inv(self, ctx: Context, user: discord.Member = None):
        target = user or ctx.author
        data = load_data()
        user_data = get_user_data(data, str(ctx.guild.id), str(target.id))
        inv = user_data.get("inventory", {})
        embed = discord.Embed(title=f"<:box:1517581439552585759> {target.display_name}'s Inventory",
                              color=discord.Color.green())
        if not inv:
            embed.description = "This inventory is currently empty."
        else:
            embed.description = "\n".join(f"• {item} ×{count}" for item, count in inv.items())
        await ctx.send(embed=embed)

    @inv.command(name="edit", description="Edit a user's inventory (Owner Only)")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_guild=True)
    @has_permissions(manage_guild=True)
    async def eco_inventory_edit(self, ctx: Context, user: discord.Member, item: str, action: str,
                                 amount: int = 1):
        item = normalize_item(item)
        action = action.lower().strip()
        if action not in ("add", "remove"):
            return await ctx.send(
                "<:disapprove:1517452151012589662> Action must be **add** or **remove**.", ephemeral=True)
        data = load_data()
        user_data = get_user_data(data, str(ctx.guild.id), str(user.id))
        if action == "add":
            inventory_add(user_data["inventory"], item, amount)
        else:
            removed = inventory_remove(user_data["inventory"], item, amount)
            if removed < amount:
                save_data(data)
                return await ctx.send(
                    f"<:warning:1517452174991556758> Only removed **{removed}x {item}** - {user.display_name} didn't have enough.",
                    ephemeral=True
                )
        save_data(data)
        direction = "to" if action == "add" else "from"
        await ctx.send(
            f"<:approve:1517452125687513158> {action.capitalize()}d **{amount}x {item}** {direction} {user.display_name}'s inventory.")

    @eco_balance.command(name="edit", description="Set a user's balance (Owner Only)")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_guild=True)
    async def eco_balance_edit(self, ctx: Context, user: discord.Member, amount: int):
        data = load_data()
        user_data = get_user_data(data, str(ctx.guild.id), str(user.id))
        user_data["balance"] = amount
        save_data(data)
        await ctx.send(
            f"<:approve:1517452125687513158> Set {user.display_name}'s balance to **${amount}**.")

    @e.command(name="craft", description="Craft an item")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_craft(self, ctx: Context, item: str, amount: int = 1):
        data = load_data()
        guild = get_guild_data(data, str(ctx.guild.id))
        user_data = get_user_data(data, str(ctx.guild.id), str(ctx.author.id))
        canonical_item = find_item_key(guild["recipes"], item)
        if not canonical_item:
            return await ctx.send(
                "<:disapprove:1517452151012589662> This item is not craftable.", ephemeral=True)
        recipe = guild["recipes"][canonical_item]
        delay = recipe.get("delay", 0)
        for req_item, count in recipe["reqs"].items():
            if inventory_count(user_data["inventory"], req_item) < (count * amount):
                return await ctx.send(
                    f"<:disapprove:1517452151012589662> You don't have enough **{req_item}**.", ephemeral=True)
        await ctx.send(
            f"🔨 Starting to craft {amount}x **{canonical_item}**... (Wait {delay}s)")
        if delay > 0:
            await asyncio.sleep(delay)
            data = load_data()
            guild = get_guild_data(data, str(ctx.guild.id))
            user_data = get_user_data(data, str(ctx.guild.id), str(ctx.author.id))
            for req_item, count in recipe["reqs"].items():
                if inventory_count(user_data["inventory"], req_item) < (count * amount):
                    return await ctx.send(
                        "<:disapprove:1517452151012589662> Crafting failed: You spent your ingredients while waiting!",
                        ephemeral=True)
        for req_item, count in recipe["reqs"].items():
            inventory_remove(user_data["inventory"], req_item, count * amount)
        inventory_add(user_data["inventory"], canonical_item, amount)
        save_data(data)
        await ctx.send(
            f"<:approve:1517452125687513158> Finished crafting {amount}x **{canonical_item}**!")

    @e.command(name="use", description="Use an item from your inventory")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_use(self, ctx: Context, item: str, number_of_times: int = 1):
        data = load_data()
        guild = get_guild_data(data, str(ctx.guild.id))
        user_data = get_user_data(data, str(ctx.guild.id), str(ctx.author.id))
        if inventory_count(user_data["inventory"], item) < number_of_times:
            return await ctx.send(
                f"<:disapprove:1517452151012589662> You need **{number_of_times}x** of this item to do that.",
                ephemeral=True)
        canonical_item = find_item_key(guild["item_uses"], item)
        if not canonical_item:
            return await ctx.send(
                "<:disapprove:1517452151012589662> This item has no special use effect.", ephemeral=True)
        effect = guild["item_uses"][canonical_item]
        if number_of_times > 1 and (effect.get("role_id") or effect.get("temp_role_id")):
            return await ctx.send(
                "<:disapprove:1517452151012589662> You cannot use role-giving items multiple times at once.",
                ephemeral=True)
        if effect.get("instant_message"):
            await ctx.send(effect["instant_message"])
        else:
            if ctx.interaction:
                await ctx.interaction.response.defer()
        if effect.get("delay", 0) > 0:
            await asyncio.sleep(effect["delay"])
        total_money = 0
        reward_items_given = []
        total_xp = 0
        for _ in range(number_of_times):
            inventory_remove(user_data["inventory"], item)
            total_money += effect.get("money", 0)
            total_xp += effect.get("xp", 0)
            if effect.get("give_item"):
                reward_name = effect["give_item"]
                reward_amount = effect.get("give_item_amount", 1)
                inventory_add(user_data["inventory"], reward_name, reward_amount)
                reward_items_given.append(reward_name)
            if number_of_times == 1:
                if effect.get("role_id"):
                    role = ctx.guild.get_role(effect["role_id"])
                    if role and ctx.guild.me.top_role > role:
                        try:
                            await ctx.author.add_roles(role)
                        except discord.Forbidden as error:
                            add_bot_error_entry(ctx.guild.id, ctx.channel.id, ctx.author,
                                                "item use role grant", error)
                if effect.get("temp_role_id"):
                    role = ctx.guild.get_role(effect["temp_role_id"])
                    if role and ctx.guild.me.top_role > role:
                        try:
                            await ctx.author.add_roles(role)
                        except discord.Forbidden as error:
                            add_bot_error_entry(ctx.guild.id, ctx.channel.id, ctx.author,
                                                "item use temp role grant", error)
                            continue

                        async def remove_role(r):
                            await asyncio.sleep(effect["duration"])
                            try:
                                await ctx.author.remove_roles(r)
                            except discord.Forbidden as error:
                                add_bot_error_entry(ctx.guild.id, ctx.channel.id, ctx.author,
                                                    "item use temp role remove", error)

                        self.bot.loop.create_task(remove_role(role))
        user_data["balance"] += total_money
        save_data(data)
        if total_xp > 0:
            await add_xp(self.bot, ctx.author, ctx.guild, total_xp, announce_channel=ctx.channel)
        final_msg = f"<:spark:1517583248421552305> [{number_of_times}x] {effect['message']}"
        if total_money > 0:
            final_msg += f" (Reward: ${total_money})"
        if total_xp > 0:
            final_msg += f" (+{total_xp} XP)"
        if reward_items_given:
            final_msg += f" (Received: {reward_items_given[0]}!)"
        await ctx.send(final_msg)

    @e.command(name="sell", description="Sell a specific amount of an item from your inventory")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def eco_sell(self, ctx: Context, item: str, amount: int = 1):
        if amount <= 0:
            return await ctx.send(
                "<:disapprove:1517452151012589662> You must sell at least 1 item.", ephemeral=True)
        data = load_data()
        guild = get_guild_data(data, str(ctx.guild.id))
        user_data = get_user_data(data, str(ctx.guild.id), str(ctx.author.id))
        canonical_item = find_item_key(guild.get("item_values", {}), item)
        if canonical_item is None:
            return await ctx.send(
                f"<:disapprove:1517452151012589662> **{item}** cannot be sold. No price has been set for it.",
                ephemeral=True)
        item_price = guild["item_values"][canonical_item]
        user_count = inventory_count(user_data["inventory"], canonical_item)
        if user_count < amount:
            return await ctx.send(
                f"<:disapprove:1517452151012589662> You don't have enough! You have **{user_count}x {canonical_item}**, but tried to sell **{amount}x**.",
                ephemeral=True
            )
        inventory_remove(user_data["inventory"], canonical_item, amount)
        total_value = item_price * amount
        user_data["balance"] += total_value
        save_data(data)
        await ctx.send(
            f"<:money:1517580310395486239> You sold **{amount}x {canonical_item}** for a total of **${total_value}**!\n"
            f"Your new balance is **${user_data['balance']}**."
        )

    @e.group(name="info", description="Crafting info commands", invoke_without_command=True)
    async def i(self, ctx): pass

    @i.command(name="values", description="Show all items that can be sold and their prices")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def info_values(self, ctx: Context):
        data = load_data()
        guild = get_guild_data(data, str(ctx.guild.id))
        prices = guild.get("item_values", {})
        if not prices:
            return await ctx.send(
                "<:disapprove:1517452151012589662> No items have a selling price set yet.", ephemeral=True)

        embed = discord.Embed(title="<:money:1517580310395486239> Item Market Prices", color=discord.Color.gold())
        for item, price in prices.items():
            embed.add_field(name=item, value=f"Sell Price: **${price}**", inline=False)
        await ctx.send(embed=embed)

    @i.command(name="recipes", description="Show all available crafting recipes")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def info_recipes(self, ctx: Context):
        data = load_data()
        guild = get_guild_data(data, str(ctx.guild.id))
        recipes = guild.get("recipes", {})
        if not recipes:
            return await ctx.send(
                "<:disapprove:1517452151012589662> No crafting recipes found.", ephemeral=True)

        embed = discord.Embed(title="<:craft:1518348021161660539> Crafting Book", color=discord.Color.blue())
        for result_item, recipe in recipes.items():
            ing_list = ", ".join(f"{amt}x {name}" for name, amt in recipe["reqs"].items())
            delay_str = f"<:timer:1517996239583576194> {recipe.get('delay', 0)}s" if recipe.get("delay", 0) > 0 else ""
            embed.add_field(
                name=result_item,
                value=f"Requires: {ing_list}" + (f"\n{delay_str}" if delay_str else ""),
                inline=False,
            )
        await ctx.send(embed=embed)

    @i.command(name="uses", description="Show what items do when used")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def info_uses(self, ctx: Context):
        data = load_data()
        guild = get_guild_data(data, str(ctx.guild.id))
        uses = guild.get("item_uses", {})
        if not uses:
            return await ctx.send(
                "<:disapprove:1517452151012589662> No item effects have been set up.", ephemeral=True)

        embed = discord.Embed(title="<:Vial:1517681553377857628> Item Effects Directory", color=discord.Color.green())
        for item, effect in uses.items():
            details = []
            money = effect.get("money", 0)
            if money > 0:
                details.append(f"<:money:1517580310395486239> Gives Money: **${money}**")
            xp_amount = effect.get("xp", 0)
            if xp_amount > 0:
                details.append(f"<:Vial:1517681553377857628> Grants XP: **{xp_amount} XP**")
            give_item = effect.get("give_item")
            if give_item:
                amt = effect.get("give_item_amount", 1)
                details.append(f"<:box:1517581439552585759> Gives: **{amt}x {give_item}**")
            if effect.get("role_id"):
                role = ctx.guild.get_role(effect["role_id"])
                if role:
                    details.append(f"<:shield:1518340640801427566> Grants Role: **{role.name}**")
            if effect.get("temp_role_id"):
                role = ctx.guild.get_role(effect["temp_role_id"])
                dur = effect.get("duration", 0)
                if role:
                    details.append(f"<:hourglass:1517574046252924938> Temp Role: **{role.name}** ({dur}s)")
            delay = effect.get("delay", 0)
            if delay > 0:
                details.append(f"<:timer:1517996239583576194> Delay: {delay}s")
            msg = effect.get("message")
            if msg and msg != "Used item!":
                details.append(f"<:list:1517497572770451567> Message: *{msg}*")
            if details:
                embed.add_field(name=item, value="\n".join(details), inline=False)

        if not embed.fields:
            return await ctx.send(
                "<:disapprove:1517452151012589662> No item effects have been set up.", ephemeral=True)

        await ctx.send(embed=embed)
