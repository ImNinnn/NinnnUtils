import discord, random

from Shared.Data import load_data, save_data
from Shared.User import get_user_data
from main import active_minigame_users


class TowerButton(discord.ui.Button):
    def __init__(self, row: int, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="❓", row=row)
        self.row_index = row
        self.col_index = col

    async def callback(self, interaction: discord.Interaction):
        view: TowersGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)
        if self.row_index != view.current_row:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> You must click a button in the current row first.", ephemeral=True)

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
            active_minigame_users.discard(view.user_id)
            view.disable_all_items()
            data = load_data()
            user_data = get_user_data(data, view.guild_id, view.user_id)
            after_balance = user_data["balance"]
            view.embed.title = "<:tower:1518350397008252958> Tower Gamble - Lost"
            view.embed.description = (
                f"You chose the wrong button and lost your wager of **${view.amount}**.\n"
                f"Rows cleared: {view.rows_cleared()}/5"
            )
            view.embed.set_footer(text=f"Before: ${view.before_balance} • After: ${after_balance}")
            await interaction.response.edit_message(embed=view.embed, view=view)


class CashoutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Cash Out", row=0)

    async def callback(self, interaction: discord.Interaction):
        view: TowersGameView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
        if view.finished:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> This game has already ended.", ephemeral=True)
        if not view.action_taken:
            return await interaction.response.send_message("<:disapprove:1517452151012589662> You must pick at least one tile before cashing out.", ephemeral=True)

        payout = view.calculate_payout(view.rows_cleared())
        data = load_data()
        user_data = get_user_data(data, view.guild_id, view.user_id)
        user_data["balance"] += payout
        save_data(data)
        after_balance = user_data["balance"]
        active_minigame_users.discard(view.user_id)
        view.finished = True
        view.disable_all_items()
        view.embed.title = "<:money:1517580310395486239> Tower Gamble - Cash Out"
        view.embed.description = (
            f"You cashed out with **${payout}**.\n"
            f"Rows cleared: {view.rows_cleared()}/5"
        )
        view.embed.set_footer(text=f"Before: ${view.before_balance} • After: ${after_balance}")
        await interaction.response.edit_message(embed=view.embed, view=view)


class TowersGameView(discord.ui.View):
    def __init__(self, amount: int, guild_id: str, user_id: int, before_balance: int):
        super().__init__(timeout=180)
        self.amount = amount
        self.guild_id = guild_id
        self.user_id = user_id
        self.before_balance = before_balance
        self.finished = False
        self.action_taken = False
        self.current_row = 4
        self.correct_positions = [set(random.sample(range(3), 2)) for _ in range(5)]
        self.embed = discord.Embed(
            title="<:tower:1518350397008252958> Tower Gamble",
            description="",
            color=discord.Color.red(),
        )
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
        self.embed.title = "<:tower:1518350397008252958> Tower Gamble"
        self.embed.description = (
            f"Bet: **${self.amount}**\n"
            f"Rows cleared: **{completed}/5**\n"
            f"Current cash out value: **${potential}**\n"
            f"Click a button in row **{next_row}** below, or cash out at any time."
        )
        self.embed.set_footer(text=f"Before: ${self.before_balance}")

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
        data = load_data()
        user_data = get_user_data(data, self.guild_id, self.user_id)
        user_data["balance"] += payout
        save_data(data)
        active_minigame_users.discard(self.user_id)
        self.finished = True
        self.disable_all_items()
        self.embed.title = "<:chalice:1517579767573123092> Tower Gamble - Victory"
        self.embed.description = (
            f"You reached the top and won **${payout}**!\n"
            f"Rows cleared: **5/5**"
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
        if self.message:
            data = load_data()
            user_data = get_user_data(data, self.guild_id, self.user_id)
            after_balance = user_data["balance"]
            self.embed.title = "<:hourglass:1517574046252924938> Tower Gamble - Timed Out"
            self.embed.description = (
                f"Time expired and your wager of **${self.amount}** was lost.\n"
                f"Rows cleared: **{self.rows_cleared()}/5**"
            )
            self.embed.set_footer(text=f"Before: ${self.before_balance} • After: ${after_balance}")
            try:
                await self.message.edit(embed=self.embed, view=self)
            except Exception:
                pass