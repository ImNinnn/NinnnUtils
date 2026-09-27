"""Fun and lightweight social commands."""

import random
import re

import discord
from discord import app_commands
from discord.ext import commands

from save import load_fun_data, load_love_data, save_love_data
from utils.audit import add_bot_error_entry
from utils.automod import is_honeypot_channel
from utils.banners import create_quote_card
from utils.permissions import run_automod_check_for_interaction


EIGHTBALL_RESPONSES = [
    "It is certain.",
    "It is decidedly so.",
    "Without a doubt.",
    "Yes - definitely.",
    "You may rely on it.",
    "As I see it, yes.",
    "Most likely.",
    "Outlook good.",
    "Yes.",
    "Signs point to yes.",
    "Better not tell you.",
    "Cannot predict.",
    "I dont know.",
    "Don't count on it.",
    "My reply is no.",
    "My sources say no.",
    "Outlook not so good.",
    "Very doubtful.",
    "No.",
    "Absolutely not.",
]


def _meter_reply(line: str, message: discord.Message) -> str:
    original_text = message.content if message.content else '*[Media or Embed]*'
    prefix = f'{line}\n-# **{message.author.display_name}:** '
    room = 2000 - len(prefix)
    if len(original_text) > room:
        original_text = original_text[:room - 3] + '...'
    return prefix + original_text


def auto_reply_trigger_matches(content: str, trigger: str) -> bool:
    """Match a trigger as a whole word or phrase, ignoring case and surrounding punctuation."""
    trigger = trigger.strip().lower()
    if not trigger:
        return False
    return re.search(rf"(?<!\w){re.escape(trigger)}(?!\w)", content.lower()) is not None


class FunCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        _install_types = app_commands.AppInstallationType(guild=True, user=True)
        _contexts = app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)
        self._context_menu_commands = [
            app_commands.ContextMenu(name='Rizz Meter', callback=self._rizz_context_menu, allowed_installs=_install_types, allowed_contexts=_contexts),
            app_commands.ContextMenu(name='Cringe Meter', callback=self._cringe_context_menu, allowed_installs=_install_types, allowed_contexts=_contexts),
            app_commands.ContextMenu(name='Stupid Meter', callback=self._stupid_context_menu, allowed_installs=_install_types, allowed_contexts=_contexts),
            app_commands.ContextMenu(name='Lie Meter', callback=self._lie_context_menu, allowed_installs=_install_types, allowed_contexts=_contexts),
            app_commands.ContextMenu(name='Quote', callback=self._quote_context_menu, allowed_installs=_install_types, allowed_contexts=_contexts),
        ]
        for command in self._context_menu_commands:
            self.bot.tree.add_command(command) 


    async def _rizz_context_menu(self, interaction: discord.Interaction, message: discord.Message):
        percentage = random.randint(0, 100)
        await interaction.response.defer()
        await interaction.followup.send(_meter_reply(f'> This message has **{percentage}%** Rizz.', message))

    async def _cringe_context_menu(self, interaction: discord.Interaction, message: discord.Message):
        percentage = random.randint(0, 100)
        await interaction.response.defer()
        await interaction.followup.send(_meter_reply(f'> This message is **{percentage}%** Cringe.', message))

    async def _stupid_context_menu(self, interaction: discord.Interaction, message: discord.Message):
        percentage = random.randint(0, 100)
        await interaction.response.defer()
        await interaction.followup.send(_meter_reply(f'> This message is **{percentage}%** stupid.', message))

    async def _lie_context_menu(self, interaction: discord.Interaction, message: discord.Message):
        percentage = random.randint(0, 100)
        await interaction.response.defer()
        await interaction.followup.send(_meter_reply(f'> This message is **{percentage}%** a lie.', message))

    async def _quote_context_menu(self, interaction: discord.Interaction, message: discord.Message):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True)
        except Exception:
            pass

        quote_file = await create_quote_card(message, viewer_id=interaction.user.id)
        if quote_file is None:
            try:
                if interaction.response.is_done():
                    await interaction.followup.send('<:disapprove:1517452151012589662> Unable to create quote image right now.', ephemeral=True)
                else:
                    await interaction.response.send_message('<:disapprove:1517452151012589662> Unable to create quote image right now.', ephemeral=True)
            except Exception:
                pass
            return

        try:
            if interaction.response.is_done():
                await interaction.followup.send(file=quote_file)
            else:
                await interaction.response.send_message(file=quote_file)
        except Exception:
            try:
                await interaction.followup.send(file=quote_file)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not message.content:
            return
        if is_honeypot_channel(message.guild, message.channel):
            return

        guild_replies = load_fun_data().get(str(message.guild.id))
        if not isinstance(guild_replies, dict):
            return
        for trigger, replies in guild_replies.items():
            if not replies or not auto_reply_trigger_matches(message.content, trigger):
                continue
            try:
                await message.reply(random.choice(replies))
            except Exception as error:
                add_bot_error_entry(message.guild.id, message.channel.id, message.author, f"auto-reply: {trigger}", error)
            break

    async def cog_unload(self):
        for command in self._context_menu_commands:
            self.bot.tree.remove_command(command.name, type=command.type)

    @app_commands.command(name='roll', description='Roll a 6-sided die')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def roll(self, interaction: discord.Interaction):
        result = random.randint(1, 6)
        await interaction.response.defer()
        await interaction.followup.send(f'🎲 You rolled a **{result}**!')

    @app_commands.command(name='random', description='Pick a random number between two values')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(min_value='The lowest number', max_value='The highest number')
    async def random_number(self, interaction: discord.Interaction, min_value: int, max_value: int):
        low, high = min(min_value, max_value), max(min_value, max_value)
        result = random.randint(low, high)
        await interaction.response.defer()
        await interaction.followup.send(f'<:list:1517497572770451567> Your random number between **{low}** and **{high}** is: **{result}**')

    @app_commands.command(name='love', description='Check the compatibility between two things or users')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(item1='The first person or thing', item2='The second person or thing')
    async def love(self, interaction: discord.Interaction, item1: str, item2: str):
        content = f'{item1} {item2}'.strip()
        if interaction.guild and await run_automod_check_for_interaction(interaction, content, source_label='/love'):
            return

        love_data = load_love_data()
        guild_id = str(interaction.guild.id) if interaction.guild else 'dm'
        if guild_id not in love_data:
            love_data[guild_id] = {}
        pair = sorted([item1.lower().strip(), item2.lower().strip()])
        match_key = f'{pair[0]}&{pair[1]}'
        if match_key in love_data[guild_id]:
            score = love_data[guild_id][match_key]
        else:
            score = random.randint(1, 100)
            love_data[guild_id][match_key] = score
            save_love_data(love_data)
        filled = max(0, int(score / 10))
        bar = '<:Square_Red:1517679897068306522>' * filled + '<:Square_Black:1517679889615032540>' * (10 - filled)
        embed = discord.Embed(title='Love Compatibility <:heart:1517577673763979344>', color=discord.Color.red())
        embed.add_field(name='Match', value=f'{item1} & {item2}', inline=False)
        embed.add_field(name='Compatibility', value=f'**{score}%**\n{bar}', inline=False)
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='rate-cool', description='Rate how cool someone is')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(username='The person or thing to rate')
    async def rate_cool(self, interaction: discord.Interaction, username: str):
        if interaction.guild and await run_automod_check_for_interaction(interaction, username, source_label='/rate-cool'):
            return

        love_data = load_love_data()
        guild_id = str(interaction.guild.id) if interaction.guild else 'dm'
        if guild_id not in love_data:
            love_data[guild_id] = {}
        cool_key = f'cool_{username.lower().strip()}'
        if cool_key in love_data[guild_id]:
            score = love_data[guild_id][cool_key]
        else:
            score = random.randint(1, 100)
            love_data[guild_id][cool_key] = score
            save_love_data(love_data)
        filled = max(0, int(score / 10))
        bar = '<:Square_Yellow:1517679899769311302>' * filled + '<:Square_Black:1517679889615032540>' * (10 - filled)
        embed = discord.Embed(title='Coolness Rating <:spark:1517583248421552305>', color=discord.Color.yellow())
        embed.add_field(name='User', value=username, inline=False)
        embed.add_field(name='Coolness', value=f'**{score}%**\n{bar}', inline=False)
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='rate-gay', description='Rate how gay someone is')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(username='The person or thing to rate')
    async def rate_gay(self, interaction: discord.Interaction, username: str):
        if interaction.guild and await run_automod_check_for_interaction(interaction, username, source_label='/rate-gay'):
            return

        love_data = load_love_data()
        guild_id = str(interaction.guild.id) if interaction.guild else 'dm'
        if guild_id not in love_data:
            love_data[guild_id] = {}
        gay_key = f'gay_{username.lower().strip()}'
        if gay_key in love_data[guild_id]:
            score = love_data[guild_id][gay_key]
        else:
            score = random.randint(1, 100)
            love_data[guild_id][gay_key] = score
            save_love_data(love_data)
        filled = max(0, int(score / 10))
        bar = '<:Square_Blue:1517679890932043897>' * filled + '<:Square_Black:1517679889615032540>' * (10 - filled)
        embed = discord.Embed(title='Gayness Rating <:rainbow:1518708398772846722>', color=discord.Color.blue())
        embed.add_field(name='User', value=username, inline=False)
        embed.add_field(name='Gayness', value=f'**{score}%**\n{bar}', inline=False)
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='8ball', description='Ask the magic 8-ball a question')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(question='The question you want the 8-ball to answer')
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        if interaction.guild and await run_automod_check_for_interaction(interaction, question, source_label='/8ball'):
            return

        rate_data = load_love_data()
        guild_id = str(interaction.guild.id) if interaction.guild else 'dm'
        if guild_id not in rate_data:
            rate_data[guild_id] = {}

        question_key = f'8ball_{question.lower().strip()}'
        if question_key in rate_data[guild_id]:
            response = rate_data[guild_id][question_key]
        else:
            response = random.choice(EIGHTBALL_RESPONSES)
            rate_data[guild_id][question_key] = response
            save_love_data(rate_data)

        embed = discord.Embed(title='Magic 8-Ball <:8ball:1533654157477679365>', color=discord.Color.dark_gray())
        embed.add_field(name='Question', value=question, inline=False)
        embed.add_field(name='Answer', value=response, inline=False)
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(FunCog(bot))