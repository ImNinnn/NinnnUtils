import random

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Container, LayoutView, Section, Separator, TextDisplay

from helper import (
    MAX_ITEM_BATCH_SIZE,
    ensure_economy_enabled,
    find_item_key,
    format_user_reference,
    get_user_data,
    inventory_add,
    inventory_remove,
    load_data,
    normalize_item,
    save_data,
    validate_item_batch_amount,
)


class TimeoutDisabledViewMixin:
    def __init__(self, *args, timeout: float = 600, **kwargs):
        self._timeout_message = None
        if timeout is not None and timeout < 600:
            timeout = 600
        super().__init__(*args, timeout=timeout, **kwargs)

    def _attach_message(self, message):
        if message is None:
            return None
        self._timeout_message = message
        self.message = message
        return message

    def _get_timeout_message(self):
        for attr_name in ("message", "settings_message", "original_message", "target_message", "msg"):
            candidate = getattr(self, attr_name, None)
            if candidate is not None:
                return candidate
        return self._timeout_message

    async def on_timeout(self):
        return None


class TimeoutDisabledLayoutView(TimeoutDisabledViewMixin, LayoutView):
    pass


class ShopView(TimeoutDisabledLayoutView):
    def __init__(self, shop_items, guild_id, user_id):
        super().__init__(timeout=600)
        self.shop_items = dict(shop_items)
        self.guild_id = guild_id
        self.user_id = user_id
        self.current_page = 0
        self.items_per_page = 5
        self.build_components()

    def build_components(self):
        self.clear_items()

        items = list(self.shop_items.items())
        total_pages = max(1, (len(items) + self.items_per_page - 1) // self.items_per_page)
        start = self.current_page * self.items_per_page
        page_items = items[start:start + self.items_per_page]

        container_parts = [
            TextDisplay("## <:chalice:1517579767573123092> Server Shop"),
            TextDisplay("Choose an item from the menu below and buy it with the button."),
            Separator(),
            TextDisplay(f"Page {self.current_page + 1}/{total_pages}"),
        ]

        for item_name, info in page_items:
            buy_button = Button(
                label=f"Buy ${info['price']}",
                style=discord.ButtonStyle.primary,
                custom_id=f"shop_buy:{item_name}",
            )

            async def buy_callback(interaction: discord.Interaction, button: Button = None, item_name=item_name, info=info):
                data = load_data()
                user_data = get_user_data(data, self.guild_id, str(interaction.user.id))
                price = int(info.get('price', 0))

                if user_data.get('balance', 0) < price:
                    await interaction.response.send_message('<:disapprove:1517452151012589662> You can\'t afford this!', ephemeral=True)
                    return

                user_data['balance'] = user_data.get('balance', 0) - price
                inventory_add(user_data.get('inventory', {}), item_name)
                save_data(data)

                self.build_components()
                await interaction.response.edit_message(view=self)
                await interaction.followup.send(f'<:approve:1517452125687513158> You bought **{item_name}**!', ephemeral=True)

            buy_button.callback = buy_callback
            container_parts.append(
                Section(
                    f"**{item_name}**\n{str(info.get('desc', 'No description provided')).strip() or 'No description provided'}",
                    accessory=buy_button,
                )
            )

        data = load_data()
        user_data = get_user_data(data, self.guild_id, str(self.user_id))
        balance = user_data.get('balance', 0)

        container_parts.extend([
            Separator(),
            TextDisplay(f"<:money:1517580310395486239> Your balance: **${balance}**"),
        ])

        container = Container(*container_parts, accent_color=discord.Color.gold())
        self.add_item(container)

        prev_button = Button(label='Previous', style=discord.ButtonStyle.secondary, custom_id='shop_prev', disabled=self.current_page == 0)
        next_button = Button(label='Next', style=discord.ButtonStyle.secondary, custom_id='shop_next', disabled=self.current_page >= total_pages - 1)

        async def prev_callback(interaction: discord.Interaction):
            if self.current_page > 0:
                self.current_page -= 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        async def next_callback(interaction: discord.Interaction):
            if self.current_page < total_pages - 1:
                self.current_page += 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        prev_button.callback = prev_callback
        next_button.callback = next_callback
        self.add_item(discord.ui.ActionRow(prev_button, next_button))


class EconomyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='economy-leaderboard', description='Show the server economy leaderboard')
    async def eco_leaderboard(self, interaction: discord.Interaction, limit: int = 10):
        if not await ensure_economy_enabled(interaction):
            return
        if limit <= 0:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Limit must be greater than 0.', ephemeral=True)
            return

        data = load_data()
        guild = data.get(str(interaction.guild.id), {})
        users = guild.get('users', {})
        if not users:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('No economy data for this server.', ephemeral=True)
            return

        leaderboard = [(uid, entry.get('balance', 0)) for uid, entry in users.items()]
        leaderboard.sort(key=lambda item: item[1], reverse=True)
        top = leaderboard[:limit]
        lines = []
        for index, (uid, balance) in enumerate(top, start=1):
            try:
                member = await interaction.guild.fetch_member(int(uid))
                label = member.display_name
            except Exception:
                label = f'User left server (`{uid}`)'
            lines.append(f'`#{index}` **{label}** - ${balance}')

        embed = discord.Embed(
            title=f'<:chalice:1517579767573123092> Economy Standings Leaderboard - {interaction.guild.name}',
            color=discord.Color.gold(),
        )
        embed.description = '\n'.join(lines)
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='balance', description='Check your balance or another user\'s balance')
    @app_commands.describe(user='The user whose balance you want to check')
    async def eco_balance(self, interaction: discord.Interaction, user: discord.Member = None):
        if not await ensure_economy_enabled(interaction):
            return
        target = user or interaction.user
        data = load_data()
        balance = data.get(str(interaction.guild.id), {}).get('users', {}).get(str(target.id), {}).get('balance', 0)
        await interaction.response.defer()
        await interaction.followup.send(f'<:money:1517580310395486239> {target.display_name}\'s balance: **${balance}**')

    @app_commands.command(name='daily', description='Claim your daily reward')
    @app_commands.checks.cooldown(1, 86400, key=lambda i: (i.user.id, i.guild.id))
    async def eco_daily(self, interaction: discord.Interaction):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
        earnings = random.randint(150, 200)
        user_data['balance'] = user_data.get('balance', 0) + earnings
        save_data(data)
        await interaction.response.defer()
        await interaction.followup.send(f'<:money:1517580310395486239> You claimed your daily reward and earned **${earnings}**!')

    @app_commands.command(name='pay', description='Pay another user from your balance')
    async def eco_pay(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        if not await ensure_economy_enabled(interaction):
            return
        if amount <= 0:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Amount must be greater than 0.', ephemeral=True)
            return

        data = load_data()
        guild_id = str(interaction.guild.id)
        sender = get_user_data(data, guild_id, str(interaction.user.id))
        receiver = get_user_data(data, guild_id, str(user.id))
        if sender.get('balance', 0) < amount:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> You don\'t have enough money!', ephemeral=True)
            return

        sender['balance'] = sender.get('balance', 0) - amount
        receiver['balance'] = receiver.get('balance', 0) + amount
        save_data(data)
        await interaction.response.defer()
        await interaction.followup.send(f'<:approve:1517452125687513158> Successfully sent **${amount}** to {format_user_reference(user)}!')

    @app_commands.command(name='shop', description='View the server shop')
    async def eco_shop(self, interaction: discord.Interaction):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        shop_items = data.get(str(interaction.guild.id), {}).get('shop', {})
        if not shop_items:
            await interaction.response.defer()
            await interaction.followup.send('The shop is currently empty!')
            return

        await interaction.response.send_message(view=ShopView(shop_items, str(interaction.guild.id), str(interaction.user.id)))

    @app_commands.command(name='buy', description='Buy a shop item directly')
    @app_commands.describe(item='The shop item to buy', amount='How many of the item to buy (up to 99)')
    async def eco_buy(self, interaction: discord.Interaction, item: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        is_valid, error_message = validate_item_batch_amount(amount, action_name='buy')
        if not is_valid:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(error_message, ephemeral=True)
            return

        data = load_data()
        guild_id = str(interaction.guild.id)
        guild = data.get(guild_id, {})
        user_data = get_user_data(data, guild_id, str(interaction.user.id))

        canonical_item = find_item_key(guild.get('shop', {}), item)
        if canonical_item is None:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> That item is not available in the shop.', ephemeral=True)
            return

        shop_info = guild['shop'][canonical_item]
        price = int(shop_info.get('price', 0))
        total_price = price * amount
        if user_data.get('balance', 0) < total_price:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(f'<:disapprove:1517452151012589662> You can\'t afford this purchase. Total cost: **${total_price}**.', ephemeral=True)
            return

        user_data['balance'] = user_data.get('balance', 0) - total_price
        inventory_add(user_data.get('inventory', {}), canonical_item, amount)
        save_data(data)
        await interaction.response.defer()
        await interaction.followup.send(f'<:approve:1517452125687513158> You bought **{amount}x {canonical_item}** for **${total_price}**!')

    @app_commands.command(name='inventory', description='Check your inventory or another user\'s inventory')
    @app_commands.describe(user='The user whose inventory you want to check')
    async def eco_inventory(self, interaction: discord.Interaction, user: discord.Member = None):
        if not await ensure_economy_enabled(interaction):
            return
        target = user or interaction.user
        data = load_data()
        user_data = get_user_data(data, str(interaction.guild.id), str(target.id))
        inventory = user_data.get('inventory', {})
        embed = discord.Embed(title=f'<:box:1517581439552585759> {target.display_name}\'s Inventory', color=discord.Color.green())
        if not inventory:
            embed.description = 'This inventory is currently empty.'
        else:
            embed.description = '\n'.join(f'• {item} ×{count}' for item, count in inventory.items())
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='inventory-edit', description='Edit a user\'s inventory')
    @app_commands.default_permissions(manage_guild=True)
    async def eco_inventory_edit(self, interaction: discord.Interaction, user: discord.Member, item: str, action: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        normalized_item = normalize_item(item)
        action = action.lower().strip()
        if action not in ('add', 'remove'):
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Action must be **add** or **remove**.', ephemeral=True)
            return

        data = load_data()
        user_data = get_user_data(data, str(interaction.guild.id), str(user.id))
        if action == 'add':
            inventory_add(user_data.get('inventory', {}), normalized_item, amount)
        else:
            removed = inventory_remove(user_data.get('inventory', {}), normalized_item, amount)
            if removed < amount:
                save_data(data)
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(f'<:warning:1517452174991556758> Only removed **{removed}x {normalized_item}** - {user.display_name} didn\'t have enough.', ephemeral=True)
                return
        save_data(data)
        direction = 'to' if action == 'add' else 'from'
        await interaction.response.defer()
        await interaction.followup.send(f'<:approve:1517452125687513158> {action.capitalize()}d **{amount}x {normalized_item}** {direction} {user.display_name}\'s inventory.')

    @app_commands.command(name='balance-edit', description='Set a user\'s balance')
    @app_commands.default_permissions(manage_guild=True)
    async def eco_balance_edit(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        user_data = get_user_data(data, str(interaction.guild.id), str(user.id))
        user_data['balance'] = amount
        save_data(data)
        await interaction.response.defer()
        await interaction.followup.send(f'<:approve:1517452125687513158> Set {user.display_name}\'s balance to **${amount}**.')

    @app_commands.command(name='craft', description='Craft an item')
    async def eco_craft(self, interaction: discord.Interaction, item: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        is_valid, error_message = validate_item_batch_amount(amount, action_name='craft')
        if not is_valid:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(error_message, ephemeral=True)
            return
        data = load_data()
        guild = data.get(str(interaction.guild.id), {})
        user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
        canonical_item = find_item_key(guild.get('recipes', {}), item)
        if not canonical_item:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This item is not craftable.', ephemeral=True)
            return
        inventory_add(user_data.get('inventory', {}), canonical_item, amount)
        save_data(data)
        await interaction.response.defer()
        await interaction.followup.send(f'<:approve:1517452125687513158> Crafted **{amount}x {canonical_item}**!')

    @app_commands.command(name='use', description='Use an item from your inventory')
    async def eco_use(self, interaction: discord.Interaction, item: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        if amount <= 0:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Amount must be at least 1.', ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(f'<:approve:1517452125687513158> Used **{amount}x {item}**.')

    @app_commands.command(name='sell', description='Sell a specific amount of an item from your inventory')
    async def eco_sell(self, interaction: discord.Interaction, item: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        if amount <= 0:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Amount must be at least 1.', ephemeral=True)
            return
        data = load_data()
        guild_id = str(interaction.guild.id)
        user_data = get_user_data(data, guild_id, str(interaction.user.id))
        removed = inventory_remove(user_data.get('inventory', {}), normalize_item(item), amount)
        if removed < amount:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> You do not have enough of that item.', ephemeral=True)
            return
        save_data(data)
        await interaction.response.defer()
        await interaction.followup.send(f'<:approve:1517452125687513158> Sold **{amount}x {normalize_item(item)}**.')

    @app_commands.command(name='trash', description='Delete an item from your inventory')
    async def eco_trash(self, interaction: discord.Interaction, item: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        user_data = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
        removed = inventory_remove(user_data.get('inventory', {}), normalize_item(item), amount)
        save_data(data)
        await interaction.response.defer()
        await interaction.followup.send(f'<:trash:1517497581058527404> Removed **{removed}x {normalize_item(item)}** from your inventory.')

    @app_commands.command(name='give', description='Give an item from your inventory to another user')
    async def eco_give(self, interaction: discord.Interaction, user: discord.Member, item: str, amount: int = 1):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        sender = get_user_data(data, str(interaction.guild.id), str(interaction.user.id))
        receiver = get_user_data(data, str(interaction.guild.id), str(user.id))
        removed = inventory_remove(sender.get('inventory', {}), normalize_item(item), amount)
        if removed < amount:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> You do not have enough of that item.', ephemeral=True)
            return
        inventory_add(receiver.get('inventory', {}), normalize_item(item), amount)
        save_data(data)
        await interaction.response.defer()
        await interaction.followup.send(f'<:approve:1517452125687513158> Gave **{amount}x {normalize_item(item)}** to {user.mention}.')

    @app_commands.command(name='trade', description='Start a trade with another user')
    async def eco_trade(self, interaction: discord.Interaction, user: discord.Member):
        if not await ensure_economy_enabled(interaction):
            return
        await interaction.response.defer()
        await interaction.followup.send(f'{interaction.user.mention} started a trade with {user.mention}.')

    @app_commands.command(name='values_info', description='Show all items that can be sold and their prices')
    async def values_info(self, interaction: discord.Interaction):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        guild = data.get(str(interaction.guild.id), {})
        shop_items = guild.get('shop', {})
        if not shop_items:
            await interaction.response.defer()
            await interaction.followup.send('No sellable values are configured for this server.')
            return
        embed = discord.Embed(title='Item Values', color=discord.Color.gold())
        embed.description = '\n'.join(f'• **{item}** — ${data.get("price", 0)}' for item, data in shop_items.items())
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='recipes_info', description='Show all available crafting recipes')
    async def recipes_info(self, interaction: discord.Interaction):
        if not await ensure_economy_enabled(interaction):
            return
        data = load_data()
        guild = data.get(str(interaction.guild.id), {})
        recipes = guild.get('recipes', {})
        if not recipes:
            await interaction.response.defer()
            await interaction.followup.send('No recipes are configured for this server.')
            return
        embed = discord.Embed(title='Crafting Recipes', color=discord.Color.blurple())
        embed.description = '\n'.join(f'• **{name}**' for name in recipes.keys())
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='uses_info', description='Show what items do when used')
    async def uses_info(self, interaction: discord.Interaction):
        if not await ensure_economy_enabled(interaction):
            return
        await interaction.response.defer()
        await interaction.followup.send('Item use descriptions are available in the recipe data for this server.')


async def setup(bot):
    await bot.add_cog(EconomyCog(bot))
