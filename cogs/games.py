"""Game commands and interactive game logic."""

import random
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

import helper as main


class GamesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api = main
        self.active_minigame_users: set[int] = set()
        self.work_cooldowns: dict[str, datetime] = {}

    @app_commands.command(name='slot_game', description='Play the economy slot machine and wager money')
    async def game_slot(self, interaction: discord.Interaction, amount: int):
        if not await self.api.ensure_economy_enabled(interaction):
            return
        if amount <= 0:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Bet amount must be greater than 0.', ephemeral=True)
            return

        data = self.api.load_data()
        guild_id = str(interaction.guild.id)
        user_data = self.api.get_user_data(data, guild_id, str(interaction.user.id))
        before_balance = user_data['balance']

        if before_balance < amount:
            return await interaction.response.defer(ephemeral=True), await interaction.followup.send('<:disapprove:1517452151012589662> You don\'t have enough money to place that bet.', ephemeral=True)

        emojis = ['🍒', '🍎', '🍇', '💎', '🔔', '🍋']
        e1, e2, e3 = (random.choice(emojis) for _ in range(3))

        if e1 == e2 == e3:
            user_data['balance'] += amount * 10
            result_text = f'<:chalice:1517579767573123092> **JACKPOT!** You won **${amount * 10}**!'
            color = discord.Color.green()
        else:
            user_data['balance'] -= amount
            result_text = f'<:money:1517580310395486239> You lost **${amount}**. Better luck next time!'
            color = discord.Color.red()

        self.api.save_data(data)
        embed = discord.Embed(title='<:777:1518352060574208031> Economy Slot Machine', description=f'Bet: **${amount}**', color=color)
        embed.add_field(name='Result', value=f'| {e1} | {e2} | {e3} |', inline=False)
        embed.add_field(name='Outcome', value=result_text, inline=False)
        embed.set_footer(text=f'Before: ${before_balance} • After: ${user_data["balance"]}')
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='coinflip_game', description='Play coinflip and wager money')
    async def game_coinflip(self, interaction: discord.Interaction, amount: int):
        if not await self.api.ensure_economy_enabled(interaction):
            return
        if amount <= 0:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Bet amount must be greater than 0.', ephemeral=True)
            return

        data = self.api.load_data()
        guild_id = str(interaction.guild.id)
        user_data = self.api.get_user_data(data, guild_id, str(interaction.user.id))
        before_balance = user_data['balance']

        if before_balance < amount:
            return await interaction.response.defer(ephemeral=True), await interaction.followup.send('<:disapprove:1517452151012589662> You don\'t have enough money to place that bet.', ephemeral=True)

        result = random.choice(['heads', 'tails'])
        if result == 'heads':
            user_data['balance'] += amount
            result_text = f'<:chalice:1517579767573123092> You won **${amount}**! The coin landed on **Heads**.'
            color = discord.Color.green()
        else:
            user_data['balance'] -= amount
            result_text = f'<:money:1517580310395486239> You lost **${amount}**. The coin landed on **Tails**.'
            color = discord.Color.red()

        self.api.save_data(data)

        embed = discord.Embed(title='<:coin:1518351100783231138> Coin Flip', description=f'Bet: **${amount}**', color=color)
        embed.add_field(name='Result', value=result_text, inline=False)
        embed.set_footer(text=f'Before: ${before_balance} • After: ${user_data["balance"]}')
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='minesweeper_game', description='Play minesweeper and wager money')
    async def game_mines(self, interaction: discord.Interaction, amount: int, mines: int):
        if not await self.api.ensure_economy_enabled(interaction):
            return
        if amount <= 0:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Bet amount must be greater than 0.', ephemeral=True)
            return
        if mines < 3 or mines > 10:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Number of mines must be between 3 and 10.', ephemeral=True)
            return

        data = self.api.load_data()
        guild_id = str(interaction.guild.id)
        user_data = self.api.get_user_data(data, guild_id, str(interaction.user.id))
        before_balance = user_data['balance']

        if interaction.user.id in self.active_minigame_users:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> You already have an active minigame. Finish or wait for it to time out before starting another.', ephemeral=True)
            return

        if before_balance < amount:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> You don\'t have enough money to place that bet.', ephemeral=True)
            return

        user_data['balance'] -= amount
        self.api.save_data(data)
        view = MinesGameView(amount=amount, mines=mines, guild_id=guild_id, user_id=interaction.user.id, before_balance=before_balance, bot=self.bot, active_minigame_users=self.active_minigame_users)
        self.active_minigame_users.add(interaction.user.id)
        await interaction.response.defer()
        await interaction.followup.send(embed=view.embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name='towers_game', description='Play tower gamble and wager money')
    async def game_towers(self, interaction: discord.Interaction, amount: int):
        if not await self.api.ensure_economy_enabled(interaction):
            return
        if amount <= 0:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Bet amount must be greater than 0.', ephemeral=True)
            return

        data = self.api.load_data()
        guild_id = str(interaction.guild.id)
        user_data = self.api.get_user_data(data, guild_id, str(interaction.user.id))
        before_balance = user_data['balance']

        if interaction.user.id in self.active_minigame_users:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> You already have an active minigame. Finish or wait for it to time out before starting another.', ephemeral=True)
            return

        if before_balance < amount:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> You don\'t have enough money to place that bet.', ephemeral=True)
            return

        user_data['balance'] -= amount
        self.api.save_data(data)
        view = TowersGameView(amount=amount, guild_id=guild_id, user_id=interaction.user.id, before_balance=before_balance, bot=self.bot, active_minigame_users=self.active_minigame_users)
        self.active_minigame_users.add(interaction.user.id)
        await interaction.response.defer()
        await interaction.followup.send(embed=view.embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name='work_game', description='Work to earn money (get 1 of 3 random jobs, 2 hour cooldown)')
    @app_commands.describe(difficulty='Choose the work difficulty')
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name='Easy', value='easy'),
            app_commands.Choice(name='Normal', value='normal'),
            app_commands.Choice(name='Hard', value='hard'),
        ]
    )
    async def game_work(self, interaction: discord.Interaction, difficulty: str = 'normal'):
        if not await self.api.ensure_economy_enabled(interaction):
            return
        difficulty = difficulty.lower().strip()
        if difficulty not in WORK_DIFFICULTY_SETTINGS:
            difficulty = 'normal'

        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)
        cooldown_key = f'{guild_id}_{user_id}'

        now = datetime.now()
        if cooldown_key in self.work_cooldowns:
            last_use = self.work_cooldowns[cooldown_key]
            elapsed = (now - last_use).total_seconds()
            remaining = 7200 - elapsed
            if remaining > 0:
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(f'<:timer:1517996239583576194> You can work again in **{minutes}m {seconds}s**.', ephemeral=True)
                return

        job_type = random.choice(['developer', 'farmer', 'math'])
        self.work_cooldowns[cooldown_key] = now
        view = WorkGameView(job_type, guild_id, interaction.user.id, 0, difficulty, bot=self.bot)
        await interaction.response.defer()
        await interaction.followup.send(embed=view.embed, view=view)
        view.message = await interaction.original_response()


class MinesButton(discord.ui.Button):
    def __init__(self, index: int, row: int, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label='❓', row=row)
        self.index = index
        self.row_index = row
        self.col_index = col

    async def callback(self, interaction: discord.Interaction):
        view: MinesGameView = self.view
        if interaction.user.id != view.user_id:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game is not for you.', ephemeral=True)
            return
        if view.finished:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game has already ended.', ephemeral=True)
            return
        view.action_taken = True
        if self.index in view.mine_positions:
            self.style = discord.ButtonStyle.danger
            self.label = '💣'
            self.disabled = True
            view.reveal_board()
            view.finished = True
            view.disable_all_items()
            view.active_minigame_users.discard(view.user_id)
            data = main.load_data()
            user_data = main.get_user_data(data, view.guild_id, view.user_id)
            after_balance = user_data['balance']
            view.embed.title = '💥 Minesweeper - Lost'
            view.embed.description = (
                f'You hit a mine and lost your wager of **${view.amount}**.\n'
                f'Safe tiles found: **{len(view.revealed_positions)}/{view.total_safe}**'
            )
            view.embed.set_footer(text=f'Before: ${view.before_balance} • After: ${after_balance}')
            await interaction.response.edit_message(embed=view.embed, view=view)
            return

        self.disabled = True
        self.style = discord.ButtonStyle.success
        view.revealed_positions.add(self.index)
        adjacent = view.adjacent_mine_count(self.index)
        self.label = str(adjacent) if adjacent > 0 else '0'
        view.update_embed()
        if len(view.revealed_positions) >= view.total_safe:
            await view.finish_game(interaction)
            return
        await interaction.response.edit_message(embed=view.embed, view=view)


class MinesCashoutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label='Cash Out', row=4)

    async def callback(self, interaction: discord.Interaction):
        view: MinesGameView = self.view
        if interaction.user.id != view.user_id:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game is not for you.', ephemeral=True)
            return
        if view.finished:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game has already ended.', ephemeral=True)
            return
        if not view.action_taken:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> You must reveal at least one tile before cashing out.', ephemeral=True)
            return

        payout = view.calculate_payout()
        data = main.load_data()
        user_data = main.get_user_data(data, view.guild_id, view.user_id)
        user_data['balance'] += payout
        main.save_data(data)
        view.active_minigame_users.discard(view.user_id)
        view.finished = True
        view.disable_all_items()
        view.embed.title = '<:money:1517580310395486239> Minesweeper - Cash Out'
        view.embed.description = (
            f'You cashed out with **${payout}**.\n'
            f'Safe tiles found: **{len(view.revealed_positions)}/{view.total_safe}**'
        )
        view.embed.set_footer(text=f'Before: ${view.before_balance} • After: ${user_data["balance"]}')
        await interaction.response.edit_message(embed=view.embed, view=view)


class MinesGameView(discord.ui.View):
    def __init__(self, amount: int, mines: int, guild_id: str, user_id: int, before_balance: int, bot: discord.Client, active_minigame_users: set[int] | None = None):
        super().__init__(timeout=600)
        self.amount = amount
        self.mines = mines
        self.guild_id = guild_id
        self.user_id = user_id
        self.before_balance = before_balance
        self.bot = bot
        self.active_minigame_users = active_minigame_users if active_minigame_users is not None else set()
        self.finished = False
        self.action_taken = False
        self.revealed_positions = set()
        self.total_cells = 20
        self.total_safe = self.total_cells - self.mines
        self.mine_positions = set(random.sample(range(self.total_cells), self.mines))
        self.initial_revealed_index = None
        self.embed = discord.Embed(title='<:explosive:1517578642723573880> Minesweeper Gamble', description='', color=discord.Color.red())
        for row in range(5):
            for col in range(4):
                index = row * 4 + col
                self.add_item(MinesButton(index=index, row=row, col=col))
        self.add_item(MinesCashoutButton())
        self.message = None
        self.reveal_initial_tile()
        self.update_embed()

    def player_safe_count(self) -> int:
        return len(self.revealed_positions) - (1 if self.initial_revealed_index is not None else 0)

    def calculate_payout(self) -> int:
        multiplier = 1 + self.mines * 0.01
        payout = self.amount * (multiplier ** self.player_safe_count())
        return int(round(payout))

    def adjacent_mine_count(self, index: int) -> int:
        row = index // 4
        col = index % 4
        count = 0
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr = row + dr
                nc = col + dc
                if 0 <= nr < 5 and 0 <= nc < 4:
                    if nr * 4 + nc in self.mine_positions:
                        count += 1
        return count

    def update_embed(self):
        safe_count = len(self.revealed_positions)
        payout = self.calculate_payout()
        self.embed.title = '<:explosive:1517578642723573880> Minesweeper Gamble'
        self.embed.description = (
            f'Bet: **${self.amount}**\n'
            f'Mines: **{self.mines}**\n'
            f'Safe tiles found: **{safe_count}/{self.total_safe}**\n'
            f'Cash out value: **${payout}**\n'
            'Click any tile, or cash out at any time.'
        )
        self.embed.set_footer(text=f'Before: ${self.before_balance}')

    def reveal_board(self):
        for item in self.children:
            if isinstance(item, MinesButton):
                if item.index in self.mine_positions:
                    item.disabled = True
                    item.style = discord.ButtonStyle.danger
                    item.label = '💣'
                else:
                    item.disabled = True

    def reveal_initial_tile(self):
        safe_positions = [i for i in range(self.total_cells) if i not in self.mine_positions]
        if not safe_positions:
            return
        initial_index = random.choice(safe_positions)
        self.initial_revealed_index = initial_index
        self.revealed_positions.add(initial_index)

        for item in self.children:
            if isinstance(item, MinesButton) and item.index == initial_index:
                item.disabled = True
                item.style = discord.ButtonStyle.primary
                adjacent = self.adjacent_mine_count(item.index)
                item.label = str(adjacent) if adjacent > 0 else '0'
                break

    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def finish_game(self, interaction: discord.Interaction):
        payout = self.calculate_payout()
        data = main.load_data()
        user_data = main.get_user_data(data, self.guild_id, self.user_id)
        user_data['balance'] += payout
        main.save_data(data)

        self.active_minigame_users.discard(self.user_id)
        self.finished = True
        self.disable_all_items()
        self.embed.title = '<:chalice:1517579767573123092> Minesweeper - Victory'
        self.embed.description = (
            f'You safely revealed all non-mine tiles and won **${payout}**!\n'
            f'Safe tiles found: **{len(self.revealed_positions)}/{self.total_safe}**'
        )
        self.embed.set_footer(text=f'Before: ${self.before_balance} • After: ${user_data["balance"]}')
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game is not for you.', ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.finished:
            return
        self.active_minigame_users.discard(self.user_id)
        self.finished = True
        self.disable_all_items()
        self.reveal_board()
        if self.message:
            self.embed.title = '<:hourglass:1517574046252924938> Minesweeper - Timed Out'
            self.embed.description = (
                f'Time expired and your wager of **${self.amount}** was lost.\n'
                f'Safe tiles found: **{len(self.revealed_positions)}/{self.total_safe}**'
            )
            self.embed.set_footer(text=f'Before: ${self.before_balance}')
            try:
                await self.message.edit(embed=self.embed, view=self)
            except Exception:
                pass


class TowerButton(discord.ui.Button):
    def __init__(self, row: int, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label='❓', row=row)
        self.row_index = row
        self.col_index = col

    async def callback(self, interaction: discord.Interaction):
        view: TowersGameView = self.view
        if interaction.user.id != view.user_id:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game is not for you.', ephemeral=True)
            return
        if view.finished:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game has already ended.', ephemeral=True)
            return
        if self.row_index != view.current_row:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> You must click a button in the current row first.', ephemeral=True)
            return

        view.action_taken = True
        if self.col_index in view.correct_positions[self.row_index]:
            self.style = discord.ButtonStyle.success
            self.disabled = True
            view.reveal_row(self.row_index)
            view.current_row -= 1
            view.update_embed()
            if view.current_row < 0:
                await view.finish_game(interaction)
                return
            view.update_row_buttons()
            await interaction.response.edit_message(embed=view.embed, view=view)
        else:
            self.style = discord.ButtonStyle.danger
            view.reveal_row(self.row_index)
            view.finished = True
            view.active_minigame_users.discard(view.user_id)
            view.disable_all_items()
            data = main.load_data()
            user_data = main.get_user_data(data, view.guild_id, view.user_id)
            after_balance = user_data['balance']
            view.embed.title = '<:tower:1518350397008252958> Tower Gamble - Lost'
            view.embed.description = (
                f'You chose the wrong button and lost your wager of **${view.amount}**.\n'
                f'Rows cleared: {view.rows_cleared()}/5'
            )
            view.embed.set_footer(text=f'Before: ${view.before_balance} • After: ${after_balance}')
            await interaction.response.edit_message(embed=view.embed, view=view)


class CashoutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label='Cash Out', row=0)

    async def callback(self, interaction: discord.Interaction):
        view: TowersGameView = self.view
        if interaction.user.id != view.user_id:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game is not for you.', ephemeral=True)
            return
        if view.finished:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game has already ended.', ephemeral=True)
            return
        if not view.action_taken:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> You must pick at least one tile before cashing out.', ephemeral=True)
            return

        payout = view.calculate_payout(view.rows_cleared())
        data = main.load_data()
        user_data = main.get_user_data(data, view.guild_id, view.user_id)
        user_data['balance'] += payout
        main.save_data(data)
        view.active_minigame_users.discard(view.user_id)
        view.finished = True
        view.disable_all_items()
        view.embed.title = '<:money:1517580310395486239> Tower Gamble - Cash Out'
        view.embed.description = (
            f'You cashed out with **${payout}**.\n'
            f'Rows cleared: **{view.rows_cleared()}/5**'
        )
        view.embed.set_footer(text=f'Before: ${view.before_balance} • After: ${user_data["balance"]}')
        await interaction.response.edit_message(embed=view.embed, view=view)


class TowersGameView(discord.ui.View):
    def __init__(self, amount: int, guild_id: str, user_id: int, before_balance: int, bot: discord.Client, active_minigame_users: set[int] | None = None):
        super().__init__(timeout=600)
        self.amount = amount
        self.guild_id = guild_id
        self.user_id = user_id
        self.before_balance = before_balance
        self.bot = bot
        self.active_minigame_users = active_minigame_users if active_minigame_users is not None else set()
        self.finished = False
        self.action_taken = False
        self.current_row = 4
        self.correct_positions = [set(random.sample(range(3), 2)) for _ in range(5)]
        self.embed = discord.Embed(title='<:tower:1518350397008252958> Tower Gamble', description='', color=discord.Color.red())
        self.update_embed()
        for row in range(5):
            for col in range(3):
                button = TowerButton(row=row, col=col)
                button.disabled = row != self.current_row
                self.add_item(button)
        self.add_item(CashoutButton())
        self.message = None

    def rows_cleared(self) -> int:
        return max(0, 4 - self.current_row)

    def calculate_payout(self, completed_rows: int) -> int:
        return int(round(self.amount * (1.07 ** completed_rows)))

    def update_embed(self):
        completed = self.rows_cleared()
        potential = self.calculate_payout(completed)
        next_row = 5 - self.current_row
        self.embed.title = '<:tower:1518350397008252958> Tower Gamble'
        self.embed.description = (
            f'Bet: **${self.amount}**\n'
            f'Rows cleared: **{completed}/5**\n'
            f'Current cash out value: **${potential}**\n'
            f'Click a button in row **{next_row}** below, or cash out at any time.'
        )
        self.embed.set_footer(text=f'Before: ${self.before_balance}')

    def update_row_buttons(self):
        for item in self.children:
            if isinstance(item, TowerButton):
                if item.row_index == self.current_row:
                    item.disabled = False
                    item.style = discord.ButtonStyle.secondary
                else:
                    item.disabled = True

    def reveal_row(self, row_index: int):
        for item in self.children:
            if isinstance(item, TowerButton) and item.row_index == row_index:
                item.disabled = True
                if item.col_index in self.correct_positions[row_index]:
                    item.style = discord.ButtonStyle.success
                else:
                    item.style = discord.ButtonStyle.danger

    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def finish_game(self, interaction: discord.Interaction):
        payout = self.calculate_payout(5)
        data = main.load_data()
        user_data = main.get_user_data(data, self.guild_id, self.user_id)
        user_data['balance'] += payout
        main.save_data(data)

        self.active_minigame_users.discard(self.user_id)
        self.finished = True
        self.disable_all_items()
        self.embed.title = '<:chalice:1517579767573123092> Tower Gamble - Victory'
        self.embed.description = (
            f'You reached the top and won **${payout}**!\n'
            'Rows cleared: **5/5**'
        )
        self.embed.set_footer(text=f'Before: ${self.before_balance} • After: ${user_data["balance"]}')
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game is not for you.', ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.finished:
            return
        self.active_minigame_users.discard(self.user_id)
        self.finished = True
        self.disable_all_items()
        if self.message:
            data = main.load_data()
            user_data = main.get_user_data(data, self.guild_id, self.user_id)
            after_balance = user_data['balance']
            self.embed.title = '<:hourglass:1517574046252924938> Tower Gamble - Timed Out'
            self.embed.description = (
                f'Time expired and your wager of **${self.amount}** was lost.\n'
                f'Rows cleared: **{self.rows_cleared()}/5**'
            )
            self.embed.set_footer(text=f'Before: ${self.before_balance} • After: ${after_balance}')
            try:
                await self.message.edit(embed=self.embed, view=self)
            except Exception:
                pass


class DeveloperCodeSelect(discord.ui.Select):
    def __init__(self, correct_index: int):
        self.correct_index = correct_index
        options = [discord.SelectOption(label=f'Code {i + 1}', value=str(i)) for i in range(10)]
        super().__init__(placeholder='Choose the different code...', options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        view: WorkGameView = self.view
        if interaction.user.id != view.user_id:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game is not for you.', ephemeral=True)
            return
        if view.finished:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game has already ended.', ephemeral=True)
            return

        selected_index = int(self.values[0])
        if selected_index == self.correct_index:
            view.finished = True
            view.disable_all_items()
            payout = get_work_payout(view.difficulty)
            data = main.load_data()
            user_data = main.get_user_data(data, view.guild_id, view.user_id)
            user_data['balance'] += payout
            main.save_data(data)
            view.embed.title = '<:list:1517497572770451567> Developer Job - Success!'
            view.embed.description = f'You found the odd code string and earned **${payout}**!'
            await interaction.response.edit_message(embed=view.embed, view=view)
        else:
            view.finished = True
            view.disable_all_items()
            view.embed.title = '<:list:1517497572770451567> Developer Job - Failed!'
            view.embed.description = "That's not the odd code! You didn't earn anything this time."
            await interaction.response.edit_message(embed=view.embed, view=view)


class DeveloperCodeButton(discord.ui.Button):
    def __init__(self, index: int, code: str, is_odd: bool, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label=code, row=row)
        self.index = index
        self.code = code
        self.is_odd = is_odd

    async def callback(self, interaction: discord.Interaction):
        view: WorkGameView = self.view
        if interaction.user.id != view.user_id:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game is not for you.', ephemeral=True)
            return
        if view.finished:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game has already ended.', ephemeral=True)
            return

        if self.is_odd:
            view.finished = True
            view.disable_all_items()
            payout = get_work_payout(view.difficulty)
            data = main.load_data()
            user_data = main.get_user_data(data, view.guild_id, view.user_id)
            user_data['balance'] += payout
            main.save_data(data)
            view.embed.title = '<:list:1517497572770451567> Developer Job - Success!'
            view.embed.description = f'You found the odd code string and earned **${payout}**!'
            await interaction.response.edit_message(embed=view.embed, view=view)
        else:
            self.disabled = True
            self.style = discord.ButtonStyle.danger
            view.finished = True
            view.disable_all_items()
            view.embed.title = '<:list:1517497572770451567> Developer Job - Failed!'
            view.embed.description = "That's not the odd code! You didn't earn anything this time."
            await interaction.response.edit_message(embed=view.embed, view=view)


class FarmerCropButton(discord.ui.Button):
    def __init__(self, index: int, crop: str, is_target: bool, is_dirt: bool, row: int, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label=crop, row=row)
        self.index = index
        self.crop = crop
        self.is_target = is_target
        self.is_dirt = is_dirt
        self.col_index = col

    async def callback(self, interaction: discord.Interaction):
        view: WorkGameView = self.view
        if interaction.user.id != view.user_id:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game is not for you.', ephemeral=True)
            return
        if view.finished:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> This game has already ended.', ephemeral=True)
            return

        if self.is_dirt:
            self.disabled = True
            await interaction.response.defer()
            return

        if self.is_target:
            view.correct_crops_clicked.add(self.index)
            self.disabled = True
            self.style = discord.ButtonStyle.success
            if len(view.correct_crops_clicked) == len(view.target_crop_indices):
                view.finished = True
                view.disable_all_items()
                payout = get_work_payout(view.difficulty)
                data = main.load_data()
                user_data = main.get_user_data(data, view.guild_id, view.user_id)
                user_data['balance'] += payout
                main.save_data(data)
                view.embed.title = '🌱 Farmer Job - Success!'
                view.embed.description = f'You collected all the correct crops and earned **${payout}**!'
                await interaction.response.edit_message(embed=view.embed, view=view)
            else:
                await interaction.response.defer()
        else:
            self.disabled = True
            self.style = discord.ButtonStyle.danger
            view.finished = True
            view.disable_all_items()
            view.embed.title = '🌱 Farmer Job - Failed!'
            view.embed.description = "You clicked the wrong crop! You didn't earn anything this time."
            await interaction.response.edit_message(embed=view.embed, view=view)


class WorkGameView(discord.ui.View):
    def __init__(self, job_type: str, guild_id: str, user_id: int, amount: int, difficulty: str = 'normal', bot: discord.Client | None = None):
        difficulty_settings = WORK_DIFFICULTY_SETTINGS.get(difficulty, WORK_DIFFICULTY_SETTINGS['normal'])
        super().__init__(timeout=difficulty_settings['timeout'])
        self.bot = bot
        self.job_type = job_type
        self.guild_id = guild_id
        self.user_id = user_id
        self.amount = amount
        self.difficulty = difficulty if difficulty in WORK_DIFFICULTY_SETTINGS else 'normal'
        self.timeout_seconds = difficulty_settings['timeout']
        self.developer_button_count = difficulty_settings['developer_buttons']
        self.farmer_target_count = difficulty_settings['farmer_targets']
        self.math_operations = difficulty_settings['math_operations']
        self.finished = False
        self.correct_crops_clicked = set()
        self.target_crop_indices = set()
        self.embed = discord.Embed(color=discord.Color.blue())
        self.message = None

        if job_type == 'developer':
            self.setup_developer_job()
        elif job_type == 'farmer':
            self.setup_farmer_job()
        elif job_type == 'math':
            self.setup_math_job()

    def setup_developer_job(self):
        code_string = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', k=6))
        code_options = [code_string] * (self.developer_button_count - 1)
        odd_code = self.mutate_string(code_string)
        code_options.append(odd_code)
        random.shuffle(code_options)

        self.embed.title = '<:list:1517497572770451567> Developer Job'
        self.embed.description = (
            f'Find the code string that is different from the others!\n'
            f'<:timer:1517996239583576194> **{self.timeout_seconds} seconds left**'
        )

        odd_index = code_options.index(odd_code)
        for i, code in enumerate(code_options):
            is_odd = i == odd_index
            self.add_item(DeveloperCodeButton(i, code, is_odd, row=i // 5))

    def setup_farmer_job(self):
        crops = ['🥕', '🥬', '🌾', '🫛', '🥔']
        target_crop = random.choice(crops)
        wrong_crops = random.sample([c for c in crops if c != target_crop], 2)

        target_positions = set(random.sample(range(8), self.farmer_target_count))
        wrong_positions = set(random.sample([i for i in range(8) if i not in target_positions], 2))
        self.target_crop_indices = target_positions

        self.embed.title = '🌱 Farmer Job'
        self.embed.description = (
            f'Collect all **{len(target_positions)}** {target_crop} crops from the farm!\n'
            'Click the right crops and avoid the others.\n'
            f'<:timer:1517996239583576194> **{self.timeout_seconds} seconds left**'
        )

        for i in range(8):
            row = i // 4
            col = i % 4
            if i in target_positions:
                self.add_item(FarmerCropButton(i, target_crop, True, False, row, col))
            elif i in wrong_positions:
                self.add_item(FarmerCropButton(i, wrong_crops.pop(), False, False, row, col))
            else:
                self.add_item(FarmerCropButton(i, '🟫', False, True, row, col))

    def setup_math_job(self):
        self.embed.title = '<:plus:1518348756570079262> Math Teacher Job'
        self.embed.description = f'Solve the equation!\n<:timer:1517996239583576194> **{self.timeout_seconds} seconds left**'

        operation = random.choice(self.math_operations)
        if operation == '/':
            num2 = random.randint(2, 12)
            self.correct_answer = random.randint(2, 12)
            num1 = num2 * self.correct_answer
        else:
            num1 = random.randint(10, 99)
            num2 = random.randint(1, 50)

        if operation == '+':
            self.correct_answer = num1 + num2
        elif operation == '-':
            self.correct_answer = num1 - num2
        elif operation == '*':
            self.correct_answer = num1 * num2
        else:
            self.correct_answer = num1 // num2

        self.equation = f'{num1} {operation} {num2} = ?'
        self.embed.description = f'**{self.equation}**\n<:timer:1517996239583576194> **{self.timeout_seconds} seconds left**'

        answer_input = discord.ui.TextInput(label='Your Answer', placeholder='Enter the answer', min_length=1, max_length=10)

        class MathAnswerModal(discord.ui.Modal):
            def __init__(self, view: 'WorkGameView'):
                super().__init__(title='Answer')
                self.add_item(answer_input)
                self.view = view

            async def on_submit(self, modal_interaction: discord.Interaction):
                if modal_interaction.user.id != self.view.user_id:
                    await modal_interaction.response.defer(ephemeral=True)
                    await modal_interaction.followup.send('<:multi:1518348755261460661> This is not for you.', ephemeral=True)
                    return
                if self.view.finished:
                    await modal_interaction.response.defer(ephemeral=True)
                    await modal_interaction.followup.send('<:disapprove:1517452151012589662> Game already finished.', ephemeral=True)
                    return

                try:
                    user_answer = int(answer_input.value)
                    if user_answer == self.view.correct_answer:
                        self.view.finished = True
                        self.view.disable_all_items()
                        payout = get_work_payout(self.view.difficulty)
                        data = main.load_data()
                        user_data = main.get_user_data(data, self.view.guild_id, self.view.user_id)
                        user_data['balance'] += payout
                        main.save_data(data)
                        self.view.embed.title = '<:multi:1518348755261460661> Math Teacher Job - Success!'
                        self.view.embed.description = f'Correct! The answer is **{self.view.correct_answer}**. You earned **${payout}**!'
                        await modal_interaction.response.defer()

                        await self.view.message.edit(embed=self.view.embed, view=self.view)
                    else:
                        self.view.finished = True
                        self.view.disable_all_items()
                        self.view.embed.title = '<:minus:1518348754111959150> Math Teacher Job - Failed!'
                        self.view.embed.description = f"Wrong! The correct answer is **{self.view.correct_answer}**. You didn't earn anything this time."
                        await modal_interaction.response.defer(ephemeral=True)
                        await self.view.message.edit(embed=self.view.embed, view=self.view)
                except ValueError:
                    await modal_interaction.response.defer(ephemeral=True)
                    await modal_interaction.followup.send('<:disapprove:1517452151012589662> Please enter a valid number.', ephemeral=True)

        submit_button = discord.ui.Button(label='Submit Answer', style=discord.ButtonStyle.primary)

        async def submit_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send('<:disapprove:1517452151012589662> This game is not for you.', ephemeral=True)
                return
            await interaction.response.send_modal(MathAnswerModal(self))

        submit_button.callback = submit_callback
        self.add_item(submit_button)

    def mutate_string(self, s: str) -> str:
        chars = list(s)
        pos = random.randint(0, len(chars) - 1)
        pool = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
        pool = pool.replace(chars[pos], '')
        chars[pos] = random.choice(pool)
        return ''.join(chars)

    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        self.disable_all_items()
        if self.message:
            self.embed.title = '<:timer:1517996239583576194> Work - Timed Out'
            self.embed.description = "Time expired! You didn't earn anything this time."
            try:
                await self.message.edit(embed=self.embed, view=self)
            except Exception:
                pass


WORK_DIFFICULTY_SETTINGS = {
    'easy': {
        'timeout': 30,
        'developer_buttons': 8,
        'farmer_targets': 2,
        'math_operations': ['+', '-'],
        'payout_range': (200, 300),
    },
    'normal': {
        'timeout': 25,
        'developer_buttons': 10,
        'farmer_targets': 3,
        'math_operations': ['*', '-'],
        'payout_range': (450, 550),
    },
    'hard': {
        'timeout': 20,
        'developer_buttons': 12,
        'farmer_targets': 4,
        'math_operations': ['*', '/'],
        'payout_range': (700, 800),
    },
}


def get_work_payout(difficulty: str) -> int:
    settings = WORK_DIFFICULTY_SETTINGS.get(difficulty, WORK_DIFFICULTY_SETTINGS['normal'])
    low, high = settings['payout_range']
    return random.randint(low, high)


async def setup(bot):
    await bot.add_cog(GamesCog(bot))
