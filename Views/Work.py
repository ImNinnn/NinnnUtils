import random

import discord

from Shared.Data import load_data, save_data
from Shared.User import get_user_data
from Views.DevCode import DeveloperCodeButton
from Views.Farmer import FarmerCropButton
from main import WORK_DIFFICULTY_SETTINGS


class WorkGameView(discord.ui.View):
    def __init__(self, job_type: str, guild_id: str, user_id: int, amount: int, difficulty: str = "normal"):
        difficulty_settings = WORK_DIFFICULTY_SETTINGS.get(difficulty, WORK_DIFFICULTY_SETTINGS["normal"])
        super().__init__(timeout=difficulty_settings["timeout"])
        self.job_type = job_type
        self.guild_id = guild_id
        self.user_id = user_id
        self.amount = amount
        self.difficulty = difficulty if difficulty in WORK_DIFFICULTY_SETTINGS else "normal"
        self.timeout_seconds = difficulty_settings["timeout"]
        self.developer_button_count = difficulty_settings["developer_buttons"]
        self.farmer_target_count = difficulty_settings["farmer_targets"]
        self.math_operations = difficulty_settings["math_operations"]
        self.finished = False
        self.correct_crops_clicked = set()
        self.target_crop_indices = set()
        self.embed = discord.Embed(color=discord.Color.blue())
        self.message = None

        if job_type == "developer":
            self.setup_developer_job()
        elif job_type == "farmer":
            self.setup_farmer_job()
        elif job_type == "math":
            self.setup_math_job()

    def setup_developer_job(self):
        code_string = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", k=6))
        code_options = [code_string] * (self.developer_button_count - 1)
        odd_code = self.mutate_string(code_string)
        code_options.append(odd_code)
        random.shuffle(code_options)

        self.embed.title = "<:list:1517497572770451567> Developer Job"
        self.embed.description = (
            f"Find the code string that is different from the others!\n"
            f"<:timer:1517996239583576194> **{self.timeout_seconds} seconds left**"
        )

        odd_index = code_options.index(odd_code)
        for i, code in enumerate(code_options):
            is_odd = (i == odd_index)
            button = DeveloperCodeButton(i, code, is_odd, row=i // 5)
            self.add_item(button)

    def setup_farmer_job(self):
        crops = ["🥕", "🥬", "🌾", "🫛", "🥔"]
        target_crop = random.choice(crops)
        wrong_crops = random.sample([c for c in crops if c != target_crop], 2)

        target_positions = set(random.sample(range(8), self.farmer_target_count))
        wrong_positions = set(random.sample([i for i in range(8) if i not in target_positions], 2))
        self.target_crop_indices = target_positions

        self.embed.title = "🌱 Farmer Job"
        self.embed.description = (
            f"Collect all **{len(target_positions)}** {target_crop} crops from the farm!\n"
            f"Click the right crops and avoid the others.\n"
            f"<:timer:1517996239583576194> **{self.timeout_seconds} seconds left**"
        )

        for i in range(8):
            row = i // 4
            col = i % 4
            if i in target_positions:
                button = FarmerCropButton(i, target_crop, True, False, row, col)
            elif i in wrong_positions:
                wrong_crop = wrong_crops.pop()
                button = FarmerCropButton(i, wrong_crop, False, False, row, col)
            else:
                button = FarmerCropButton(i, "🟫", False, True, row, col)
            self.add_item(button)

    def setup_math_job(self):
        self.embed.title = "<:plus:1518348756570079262> Math Teacher Job"
        self.embed.description = f"Solve the equation!\n<:timer:1517996239583576194> **{self.timeout_seconds} seconds left**"

        operation = random.choice(self.math_operations)
        if operation == "/":
            num2 = random.randint(2, 12)
            self.correct_answer = random.randint(2, 12)
            num1 = num2 * self.correct_answer
        else:
            num1 = random.randint(10, 99)
            num2 = random.randint(1, 50)

        if operation == "+":
            self.correct_answer = num1 + num2
        elif operation == "-":
            self.correct_answer = num1 - num2
        elif operation == "*":
            self.correct_answer = num1 * num2
        else:
            self.correct_answer = num1 // num2

        self.equation = f"{num1} {operation} {num2} = ?"
        self.embed.description = f"**{self.equation}**\n<:timer:1517996239583576194> **{self.timeout_seconds} seconds left**"

        answer_input = discord.ui.TextInput(
            label="Your Answer",
            placeholder="Enter the answer",
            min_length=1,
            max_length=10,
        )

        class MathAnswerModal(discord.ui.Modal):
            def __init__(self, view: "WorkGameView"):
                super().__init__(title="Answer")
                self.add_item(answer_input)
                self.view = view

            async def on_submit(self, modal_interaction: discord.Interaction):
                if modal_interaction.user.id != self.view.user_id:
                    return await modal_interaction.response.send_message(
                        "<:multi:1518348755261460661> This is not for you.", ephemeral=True)
                if self.view.finished:
                    return await modal_interaction.response.send_message(
                        "<:disapprove:1517452151012589662> Game already finished.", ephemeral=True)

                try:
                    user_answer = int(answer_input.value)
                    if user_answer == self.view.correct_answer:
                        self.view.finished = True
                        self.view.disable_all_items()
                        payout = get_work_payout(self.view.difficulty)
                        data = load_data()
                        user_data = get_user_data(data, self.view.guild_id, self.view.user_id)
                        user_data["balance"] += payout
                        save_data(data)
                        self.view.embed.title = "<:multi:1518348755261460661> Math Teacher Job - Success!"
                        self.view.embed.description = f"Correct! The answer is **{self.view.correct_answer}**. You earned **${payout}**!"
                        await modal_interaction.response.defer()
                        await self.view.message.edit(embed=self.view.embed, view=self.view)
                    else:
                        self.view.finished = True
                        self.view.disable_all_items()
                        self.view.embed.title = "<:minus:1518348754111959150> Math Teacher Job - Failed!"
                        self.view.embed.description = f"Wrong! The correct answer is **{self.view.correct_answer}**. You didn't earn anything this time."
                        await modal_interaction.response.defer()
                        await self.view.message.edit(embed=self.view.embed, view=self.view)
                except ValueError:
                    await modal_interaction.response.send_message(
                        "<:disapprove:1517452151012589662> Please enter a valid number.", ephemeral=True)

        submit_button = discord.ui.Button(label="Submit Answer", style=discord.ButtonStyle.primary)

        async def submit_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message(
                    "<:disapprove:1517452151012589662> This game is not for you.", ephemeral=True)
            await interaction.response.send_modal(MathAnswerModal(self))

        submit_button.callback = submit_callback
        self.add_item(submit_button)

    def mutate_string(self, s: str) -> str:
        chars = list(s)
        pos = random.randint(0, len(chars) - 1)
        pool = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        pool = pool.replace(chars[pos], "")
        chars[pos] = random.choice(pool)
        return "".join(chars)

    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        self.disable_all_items()
        if self.message:
            self.embed.title = "<:timer:1517996239583576194> Work - Timed Out"
            self.embed.description = "Time expired! You didn't earn anything this time."
            try:
                await self.message.edit(embed=self.embed, view=self)
            except Exception:
                pass
