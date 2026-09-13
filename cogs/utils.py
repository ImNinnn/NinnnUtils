"""Utility and general user-installable commands."""

import asyncio
import os
import random
import time

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Container, LayoutView, Separator, TextDisplay

import helper as main
from utils.banners import create_banner_preview
from utils.permissions import run_automod_check_for_interaction


class UtilitiesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='stats', description='Show bot statistics and status')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def stats(self, interaction: discord.Interaction):
        from dotenv import load_dotenv
        load_dotenv(override=True)
        version = os.getenv('BOT_VERSION')
        alt_version = os.getenv('BOT_VERSION_ALTERNATE')
        activity_text = os.getenv('ACTIVITY')
        total_guilds = len(self.bot.guilds)
        start_time = time.perf_counter()
        await interaction.response.defer()
        ws_latency = round(self.bot.latency * 1000)
        end_time = time.perf_counter()
        api_latency = round((end_time - start_time) * 1000)

        embed = discord.Embed(
            title='<:gear:1517576939097952496> Bot Statistics',
            color=discord.Color.gold(),
            description='Current status and technical details of the bot.',
        )
        avatar = self.bot.user.avatar.url if self.bot.user and self.bot.user.avatar else self.bot.user.default_avatar.url
        embed.set_thumbnail(url=avatar)
        embed.add_field(name='<:gear:1517576939097952496> Version', value=f'ver{version} | {alt_version}\n{activity_text}', inline=True)
        embed.add_field(name='<:internet:1518376144246804672> Servers', value=str(total_guilds), inline=True)
        embed.add_field(name='<:graph:1517584522877866065> Total Users', value=str(len(self.bot.users)), inline=True)
        embed.add_field(name='<:timer:1517996239583576194> WebSocket', value=f'{ws_latency}ms', inline=True)
        embed.add_field(name='<:hourglass:1517574046252924938> API Round-Trip', value=f'{api_latency}ms', inline=True)
        embed.add_field(name='<:python:1518376147413635154> Library', value=f'discord.py {discord.__version__}', inline=True)

        guild_shard_id = interaction.guild.shard_id if interaction.guild else 0
        total_shards = len(self.bot.shards) or 1
        shard_info = f'Shard id: {guild_shard_id} | total: {total_shards}'
        embed.add_field(name='<:shard:1518376149741338744> Shard Info', value=shard_info, inline=True)

        app_info = await self.bot.application_info()
        if app_info.team:
            owner_value = app_info.team.name
        elif app_info.owner:
            owner_value = f'{app_info.owner.name}#{app_info.owner.discriminator}'
        else:
            owner_value = 'Unknown'
        embed.add_field(name='<:nUtils:1518376146008539146> Bot owner', value=owner_value, inline=True)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='quickstats', description='Show bot statistics and status in a compact format')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def quickstats(self, interaction: discord.Interaction):
        from dotenv import load_dotenv
        load_dotenv(override=True)
        await interaction.response.defer()
        await interaction.followup.send(
            f'ver : **{os.getenv("BOT_VERSION")}**  |  alt : **{os.getenv("BOT_VERSION_ALTERNATE")}**  |  **{os.getenv("ACTIVITY")}**  |  servers : **{len(self.bot.guilds)}**  |  users : **{len(self.bot.users)}**',
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name='embed', description='Create a fully-loaded customized embed message using a styling menu')
    @app_commands.describe(color='Choose a preset theme color for the embed accent line', footer='Optional: Custom text at the very bottom row of the embed', footer_icon='Optional: Direct image URL for a tiny icon next to the footer text', thumbnail='Optional: Direct image URL to place as a small card in the top right', image='Optional: Direct image URL to place as a giant full-width display banner')
    @app_commands.choices(color=[app_commands.Choice(name='🔴 Red', value='red'), app_commands.Choice(name='🔵 Blue', value='blue'), app_commands.Choice(name='🟢 Green', value='green'), app_commands.Choice(name='🟡 Yellow', value='yellow'), app_commands.Choice(name='🟣 Purple', value='purple'), app_commands.Choice(name='⚫ Dark Grey', value='dark'), app_commands.Choice(name='<:spark:1517583248421552305> Random Color', value='random')])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def embed_builder(self, interaction: discord.Interaction, color: str = 'blue', footer: str | None = None, footer_icon: str | None = None, thumbnail: str | None = None, image: str | None = None):
        await main.embed_builder.callback(interaction, color, footer, footer_icon, thumbnail, image)

    @app_commands.command(name='help', description='Browse the bot commands in a paginated list')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def help_command(self, interaction: discord.Interaction):
        await interaction.response.send_message(view=HelpCommandsView(str(interaction.user.id)), ephemeral=True)

    @app_commands.command(name='ping', description="Check the bot's latency")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def ping(self, interaction: discord.Interaction):
        start_time = time.perf_counter()
        await interaction.response.defer()
        ws_latency = round(self.bot.latency * 1000)
        end_time = time.perf_counter()
        api_latency = round((end_time - start_time) * 1000)
        await interaction.edit_original_response(
            content=f'🏓 Pong! - **WebSocket:** {ws_latency}ms - **API Round-Trip:** {api_latency}ms',
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name='slot-classic', description='Spin the slot machine!')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def slot_classic(self, interaction: discord.Interaction):
        emojis = ['🍒', '🍎', '🍇', '💎', '<:bell:1517497562184024275>', '🍋']
        await interaction.response.defer()
        await interaction.followup.send('🎰 **Spinning...**')
        for _ in range(3):
            e1, e2, e3 = (random.choice(emojis) for _ in range(3))
            await interaction.edit_original_response(content=f'🎰 | {e1} | {e2} | {e3} |')
            await asyncio.sleep(0.5)
        final_e1, final_e2, final_e3 = (random.choice(emojis) for _ in range(3))
        if final_e1 == final_e2 == final_e3:
            result_msg = f'🎰 **JACKPOT!** You won!\n\n| {final_e1} | {final_e2} | {final_e3} |'
        else:
            result_msg = f'🎰 Slot Machine:\n\n| {final_e1} | {final_e2} | {final_e3} |\n\nBetter luck next time!'
        await interaction.edit_original_response(content=result_msg)

    @app_commands.command(name='coinflip-classic', description='Flips a coin and shows Heads or Tails')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def coinflip_classic(self, interaction: discord.Interaction):
        result = random.choice(['Heads', 'Tails'])
        await interaction.response.defer()
        await interaction.followup.send(f'<:coin:1518351100783231138> The coin landed on: **{result}**!')

    @app_commands.command(name='definition', description='Look up the dictionary definition of a word')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(word='The word you want to define')
    async def definition(self, interaction: discord.Interaction, word: str):
        await main.define_word.callback(interaction, word)

    @app_commands.command(name='encode-decode', description='Encode or decode text using Base64, Base32, Base16, or Binary')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(text='The text you want to process', encoding_type='Choose the format method', action='Choose whether to encode or decode')
    @app_commands.choices(
        encoding_type=[
            app_commands.Choice(name='Base64', value='base64'),
            app_commands.Choice(name='Base32', value='base32'),
            app_commands.Choice(name='Base16 (Hex)', value='base16'),
            app_commands.Choice(name='Binary', value='binary'),
        ],
        action=[
            app_commands.Choice(name='Encode (Text ➔ Format)', value='encode'),
            app_commands.Choice(name='Decode (Format ➔ Text)', value='decode'),
        ],
    )
    async def encode_decode(self, interaction: discord.Interaction, text: str, encoding_type: str, action: str):
        await main.encode_decode_command.callback(interaction, text, encoding_type, action)

    @app_commands.command(name='translate', description='Translate text into another language')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(text='The message you want to translate', to_language='The language code to translate into (e.g. en, es, fr, ja)', from_language='Optional: Specify the original language code (defaults to auto-detect)')
    async def translate(self, interaction: discord.Interaction, text: str, to_language: str = 'en', from_language: str = 'auto'):
        await main.translate.callback(interaction, text, to_language, from_language)

    @app_commands.command(name='gif', description='Convert an image attachment into a GIF file')
    @app_commands.default_permissions(attach_files=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(image='The image to convert to GIF')
    async def gif(self, interaction: discord.Interaction, image: discord.Attachment):
        await main.gif.callback(interaction, image)

    @app_commands.command(name='afk', description='Set yourself as AFK with a reason')
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.describe(reason='Why you are going AFK')
    async def afk(self, interaction: discord.Interaction, reason: str = None):
        await main.afk_command.callback(interaction, reason)

    @app_commands.command(name='serverinfo', description='Display detailed information about this server')
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def serverinfo(self, interaction: discord.Interaction):
        await main.serverinfo.callback(interaction)

    @app_commands.command(name='channelinfo', description='Show configured channels for this server')
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def channelinfo(self, interaction: discord.Interaction):
        await main.channelinfo.callback(interaction)

    @app_commands.command(name='emoji', description='Get the image for a custom emoji')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(emoji='The custom emoji to get the image from')
    async def emoji(self, interaction: discord.Interaction, emoji: str):
        if not emoji:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Please provide a valid custom emoji.', ephemeral=True)
            return
        try:
            emoji_obj = discord.PartialEmoji.from_str(emoji)
        except Exception:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Please provide a valid custom emoji.', ephemeral=True)
            return
        if not emoji_obj.id:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('<:disapprove:1517452151012589662> Please provide a valid custom emoji.', ephemeral=True)
            return
        embed = discord.Embed(title=f'Emoji: {emoji_obj.name}', color=discord.Color.blue())
        embed.set_image(url=emoji_obj.url)
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='say', description='Make the bot say something')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def say(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer()
        await interaction.followup.send(message)


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


class HelpSearchModal(discord.ui.Modal):
    def __init__(self, help_view):
        super().__init__(title='Search help')
        self.help_view = help_view
        self.query = discord.ui.TextInput(label='Command, category, or keyword', placeholder='Try: economy, ping, fun', required=True, max_length=100)
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        search_value = (self.query.value or '').strip().lower()
        defs = main.load_help_definitions()
        commands = defs.get('commands', {}) if isinstance(defs.get('commands', {}), dict) else {}

        matches = []
        for command_name, entry in commands.items():
            if not isinstance(command_name, str) or not isinstance(entry, dict):
                continue
            haystack = ' '.join([
                command_name.lower(),
                str(entry.get('description') or '').lower(),
                str(entry.get('environement') or '').lower(),
                str(entry.get('category') or '').lower(),
            ])
            if search_value and search_value in haystack:
                matches.append(command_name)

        self.help_view.search_query = search_value or None
        self.help_view.search_matches = matches
        self.help_view.page = 0
        self.help_view.build_components()

        try:
            await interaction.response.edit_message(view=self.help_view)
        except Exception:
            try:
                await interaction.followup.send(view=self.help_view, ephemeral=True)
            except Exception:
                pass


class HelpCommandsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: str, page: int = 0):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.page = page
        self.per_page = 7
        self.search_query = None
        self.search_matches = []
        self.build_components()

    def build_components(self):
        self.clear_items()
        defs = main.load_help_definitions()
        commands = defs.get('commands', {}) if isinstance(defs.get('commands', {}), dict) else {}
        command_names = [name for name in commands.keys() if isinstance(name, str) and name.strip()]
        if not command_names:
            command_names = ['/help', '/ping', '/stats', '/avatar', '/banner', '/emoji', '/daily', '/balance', '/shop']

        tutorial = (defs.get('mini_tutorial') or '').strip() or (
            'Use slash commands to explore the bot.\n'
            'Tip: some commands are guild-only, some work in DMs, and some require permissions.'
        )

        if self.search_query:
            matches = self.search_matches
            total_pages = max(1, (len(matches) + self.per_page - 1) // self.per_page)
            self.page = max(0, min(self.page, total_pages - 1))
            visible = matches[self.page * self.per_page:(self.page + 1) * self.per_page]
            heading = f'Search results for: **{self.search_query}**'
            page_label = f'Page {self.page + 1}/{total_pages} · {len(matches)} match(es)'
            no_results = not matches
        else:
            total_pages = 1 if len(command_names) <= 3 else 1 + ((len(command_names) - 3 + self.per_page - 1) // self.per_page)
            self.page = max(0, min(self.page, total_pages - 1))
            page_label = f'Page {self.page + 1}/{total_pages}'
            if self.page == 0:
                visible = command_names[:3]
            else:
                start = 3 + (self.page - 1) * self.per_page
                visible = command_names[start:start + self.per_page]
            heading = 'Browse the available commands page by page.'
            no_results = False

        parts = [
            TextDisplay('## <:nUtils:1518376146008539146> Help menu'),
            TextDisplay(heading),
            Separator(),
            TextDisplay(page_label),
        ]

        if not self.search_query and self.page == 0:
            parts.append(TextDisplay(tutorial))

        if self.search_query and no_results:
            parts.append(TextDisplay(f'No command matched: **{self.search_query}**'))

        for command_name in visible:
            entry = commands.get(command_name, {}) if isinstance(commands.get(command_name, {}), dict) else {}
            description = (entry.get('description') or 'No description set yet.').strip() or 'No description set yet.'
            environment = (entry.get('environement') or 'Not set').strip() or 'Not set'
            category = (entry.get('category') or 'General').strip() or 'General'
            section_text = f'**{command_name}**\n{description}\nCategory: {category}\nEnvironment: {environment}'
            parts.append(TextDisplay(section_text))
            parts.append(Separator())

        self.add_item(Container(*parts, accent_color=discord.Color.blue()))

        if self.search_query:
            search_total_pages = max(1, (len(self.search_matches) + self.per_page - 1) // self.per_page)
            prev_button = Button(label='Previous', style=discord.ButtonStyle.secondary, custom_id='help_prev', disabled=self.page == 0 or not self.search_matches)
            next_button = Button(label='Next', style=discord.ButtonStyle.secondary, custom_id='help_next', disabled=self.page >= search_total_pages - 1 or not self.search_matches)
        else:
            prev_button = Button(label='Previous', style=discord.ButtonStyle.secondary, custom_id='help_prev', disabled=self.page == 0)
            next_button = Button(label='Next', style=discord.ButtonStyle.secondary, custom_id='help_next', disabled=self.page >= total_pages - 1)

        search_button = Button(label='Search', style=discord.ButtonStyle.primary, custom_id='help_search')

        async def prev_cb(interaction: discord.Interaction):
            if self.page > 0:
                self.page -= 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        async def next_cb(interaction: discord.Interaction):
            if self.search_query:
                max_page = max(1, (len(self.search_matches) + self.per_page - 1) // self.per_page)
                if self.page < max_page - 1:
                    self.page += 1
                    self.build_components()
                    await interaction.response.edit_message(view=self)
            elif self.page < total_pages - 1:
                self.page += 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        async def search_cb(interaction: discord.Interaction):
            try:
                await interaction.response.send_modal(HelpSearchModal(self))
            except Exception:
                try:
                    await interaction.followup.send('Could not open search.', ephemeral=True)
                except Exception:
                    pass

        prev_button.callback = prev_cb
        next_button.callback = next_cb
        search_button.callback = search_cb
        self.add_item(discord.ui.ActionRow(prev_button, next_button, search_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != int(self.user_id):
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('This help menu is only for the original user.', ephemeral=True)
            return False
        return True


async def setup(bot):
    await bot.add_cog(UtilitiesCog(bot))
