import random

import discord

from Shared.Data import load_data, save_data
from Shared.User import get_user_data
from main import active_minigame_users


class MinesButton(discord.ui.Button):
    def __init__(self, index: int, row: int, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="❓", row=row)
        self.index = index
        self.row_index = row
        self.col_index = col

    async def callback(self, interaction: discord.Interaction):
        view: MinesGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)
        view.action_taken = True
        if self.index in view.mine_positions:
            self.style = discord.ButtonStyle.danger
            self.label = "💣"
            self.disabled = True
            view.reveal_board()
            view.finished = True
            view.disable_all_items()
            active_minigame_users.discard(view.user_id)
            data = load_data()
            user_data = get_user_data(data, view.guild_id, view.user_id)
            after_balance = user_data["balance"]
            view.embed.title = "💥 Minesweeper - Lost"
            view.embed.description = (
                f"You hit a mine and lost your wager of **${view.amount}**.\n"
                f"Safe tiles found: **{len(view.revealed_positions)}/{view.total_safe}**"
            )
            view.embed.set_footer(text=f"Before: ${view.before_balance} • After: ${after_balance}")
            await interaction.response.edit_message(embed=view.embed, view=view)
            return

        self.disabled = True
        self.style = discord.ButtonStyle.success
        view.revealed_positions.add(self.index)
        adjacent = view.adjacent_mine_count(self.index)
        self.label = str(adjacent) if adjacent > 0 else "0"
        view.update_embed()
        if len(view.revealed_positions) >= view.total_safe:
            await view.finish_game(interaction)
            return
        await interaction.response.edit_message(embed=view.embed, view=view)


class MinesCashoutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Cash Out", row=4)

    async def callback(self, interaction: discord.Interaction):
        view: MinesGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)
        if not view.action_taken:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> You must reveal at least one tile before cashing out.", ephemeral=True)

        payout = view.calculate_payout()
        data = load_data()
        user_data = get_user_data(data, view.guild_id, view.user_id)
        user_data["balance"] += payout
        save_data(data)
        active_minigame_users.discard(view.user_id)
        view.finished = True
        view.disable_all_items()
        view.embed.title = "<:money:1517580310395486239> Minesweeper - Cash Out"
        view.embed.description = (
            f"You cashed out with **${payout}**.\n"
            f"Safe tiles found: **{len(view.revealed_positions)}/{view.total_safe}**"
        )
        view.embed.set_footer(text=f"Before: ${view.before_balance} • After: ${user_data['balance']}")
        await interaction.response.edit_message(embed=view.embed, view=view)

class MinesGameView(discord.ui.View):
    def __init__(self, amount: int, mines: int, guild_id: str, user_id: int, before_balance: int):
        super().__init__(timeout=180)
        self.amount = amount
        self.mines = mines
        self.guild_id = guild_id
        self.user_id = user_id
        self.before_balance = before_balance
        self.finished = False
        self.action_taken = False
        self.revealed_positions = set()
        self.total_cells = 20
        self.total_safe = self.total_cells - self.mines
        self.mine_positions = set(random.sample(range(self.total_cells), self.mines))
        self.initial_revealed_index = None
        self.embed = discord.Embed(
            title="<:explosive:1517578642723573880> Minesweeper Gamble",
            description="",
            color=discord.Color.red(),
        )
        for row in range(5):
            for col in range(4):
                index = row * 4 + col
                button = MinesButton(index=index, row=row, col=col)
                self.add_item(button)
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
        self.embed.title = "<:explosive:1517578642723573880> Minesweeper Gamble"
        self.embed.description = (
            f"Bet: **${self.amount}**\n"
            f"Mines: **{self.mines}**\n"
            f"Safe tiles found: **{safe_count}/{self.total_safe}**\n"
            f"Cash out value: **${payout}**\n"
            f"Click any tile, or cash out at any time."
        )
        self.embed.set_footer(text=f"Before: ${self.before_balance}")

    def reveal_board(self):
        for item in self.children:
            if isinstance(item, MinesButton):
                if item.index in self.mine_positions:
                    item.disabled = True
                    item.style = discord.ButtonStyle.danger
                    item.label = "💣"
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
                item.label = str(adjacent) if adjacent > 0 else "0"
                break

    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def finish_game(self, interaction: discord.Interaction):
        payout = self.calculate_payout()
        data = load_data()
        user_data = get_user_data(data, self.guild_id, self.user_id)
        user_data["balance"] += payout
        save_data(data)
        active_minigame_users.discard(self.user_id)
        self.finished = True
        self.disable_all_items()
        self.embed.title = "<:chalice:1517579767573123092> Minesweeper - Victory"
        self.embed.description = (
            f"You safely revealed all non-mine tiles and won **${payout}**!\n"
            f"Safe tiles found: **{len(self.revealed_positions)}/{self.total_safe}**"
        )
        self.embed.set_footer(text=f"Before: ${self.before_balance} • After: ${user_data['balance']}")
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.finished:
            return
        active_minigame_users.discard(self.user_id)
        self.finished = True
        self.disable_all_items()
        self.reveal_board()
        if self.message:
            self.embed.title = "<:hourglass:1517574046252924938> Minesweeper - Timed Out"
            self.embed.description = (
                f"Time expired and your wager of **${self.amount}** was lost.\n"
                f"Safe tiles found: **{len(self.revealed_positions)}/{self.total_safe}**"
            )
            self.embed.set_footer(text=f"Before: ${self.before_balance}")
            try:
                await self.message.edit(embed=self.embed, view=self)
            except Exception:
                pass