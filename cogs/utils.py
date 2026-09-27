"""Utility and general user-installable commands."""

import asyncio
import base64
import io
import os
import random
import time
from urllib.parse import quote

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Container, Modal, Separator, TextDisplay, TextInput
from PIL import Image, ImageOps, ImageSequence

import save
from utils.audit import get_admin_log_channel_mentions
from utils.formatting import discord_timestamp, format_user_reference, normalize_language_code
from utils.permissions import run_automod_check_for_interaction
from utils.views import TimeoutDisabledLayoutView

try:
    from googletrans import Translator
except Exception:
    Translator = None


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _convert_image_to_gif(img: Image.Image) -> io.BytesIO:
    buffer = io.BytesIO()

    # exif_transpose returns a single-frame copy, so only apply it to still images;
    # otherwise every animated upload was flattened to its first frame.
    if getattr(img, "is_animated", False):
        frames = [frame.copy().convert("RGBA") for frame in ImageSequence.Iterator(img)]
        if not frames:
            raise ValueError("No frames found in the provided image.")

        # Each frame keeps its own palette. Forcing the first frame's palette onto the others
        # recoloured every frame the same and collapsed animations into a single still frame.
        quantized_frames = [frame.quantize(colors=256, method=Image.Quantize.FASTOCTREE) for frame in frames]

        quantized_frames[0].save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=quantized_frames[1:],
            loop=0,
            duration=img.info.get("duration", 100),
            disposal=2,
            optimize=False,
        )
    else:
        converted = ImageOps.exif_transpose(img).convert("RGBA")
        quantized = converted.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
        quantized.save(buffer, format="GIF", optimize=False)

    buffer.seek(0)
    return buffer


def _convert_bytes_to_gif(image_bytes: bytes) -> io.BytesIO:
    with Image.open(io.BytesIO(image_bytes)) as img:
        return _convert_image_to_gif(img)


class CustomEmbedModal(Modal):
    def __init__(self, color: discord.Color, thumbnail: str, image: str, footer_text: str, footer_icon: str):
        super().__init__(title="Configure Your Custom Embed")
        
        self.embed_color = color
        self.thumbnail_url = thumbnail
        self.image_url = image
        self.footer_text = footer_text
        self.footer_icon = footer_icon

        self.embed_title = TextInput(
            label="Embed Title",
            placeholder="Enter the main title (Optional)...",
            required=False,
            max_length=256
        )
        self.embed_author = TextInput(
            label="Author Name",
            placeholder="Display a small creator name at the very top (Optional)...",
            required=False,
            max_length=256
        )
        self.embed_author_icon = TextInput(
            label="Author Icon URL",
            placeholder="Direct link to a small image for the author icon (Optional)...",
            required=False
        )
        self.embed_description = TextInput(
            label="Embed Description",
            style=discord.TextStyle.paragraph,
            placeholder="Enter the main body text content here...",
            required=True,
            max_length=4000
        )
        self.embed_url = TextInput(
            label="Title Hyperlink URL",
            placeholder="Make the title clickable by adding a web link (Optional)...",
            required=False
        )
        
        self.add_item(self.embed_author)
        self.add_item(self.embed_author_icon)
        self.add_item(self.embed_title)
        self.add_item(self.embed_url)
        self.add_item(self.embed_description)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=self.embed_title.value if self.embed_title.value else None,
            description=self.embed_description.value,
            url=self.embed_url.value if self.embed_url.value else None,
            color=self.embed_color
        )
        
        if self.embed_author.value:
            embed.set_author(
                name=self.embed_author.value,
                icon_url=self.embed_author_icon.value if self.embed_author_icon.value else None
            )
        
        if self.thumbnail_url:
            embed.set_thumbnail(url=self.thumbnail_url)
        if self.image_url:
            embed.set_image(url=self.image_url)
            
        if self.footer_text:
            embed.set_footer(
                text=self.footer_text,
                icon_url=self.footer_icon if self.footer_icon else None
            )
        else:
            embed.set_footer(
                text=f"Created by {interaction.user.name}", 
                icon_url=interaction.user.display_avatar.url
            )

        await interaction.response.defer(); await interaction.followup.send(embed=embed)


class UtilitiesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.translation_cooldowns: dict[int, float] = {}

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
        color_map = {
            "red": discord.Color.red(),
            "blue": discord.Color.blue(),
            "green": discord.Color.green(),
            "yellow": discord.Color.yellow(),
            "purple": discord.Color.purple(),
            "dark": discord.Color.dark_embed(),
            "random": discord.Color.random()
        }
        chosen_color = color_map.get(color, discord.Color.blue())

        modal = CustomEmbedModal(
            color=chosen_color,
            thumbnail=thumbnail,
            image=image,
            footer_text=footer,
            footer_icon=footer_icon
        )
        await interaction.response.send_modal(modal)

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
        clean_word = word.strip().lower()
        # Check automod before deferring: the check sends its own reply when it blocks.
        if interaction.guild and await run_automod_check_for_interaction(interaction, clean_word, source_label="/def"):
            return

        await interaction.response.defer()

        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(clean_word, safe='')}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:

                    if response.status == 404:
                        return await interaction.followup.send(
                            f"<:disapprove:1517452151012589662> Could not find a definition for **{word}**. Double check your spelling!",
                            ephemeral=True
                        )

                    if response.status != 200:
                        return await interaction.followup.send(
                            "<:warning:1517452174991556758> The dictionary service is currently unavailable. Please try again later.",
                            ephemeral=True
                        )

                    data = await response.json()

            word_data = data[0]
            word_name = word_data.get("word", clean_word).title()
            phonetic = word_data.get("phonetic", "N/A")

            embed = discord.Embed(
                title=f"<:list:1517497572770451567> Dictionary Definition: {word_name}"[:256],
                description=f"**Phonetic:** `{phonetic}`",
                color=discord.Color.blurple()
            )

            meanings = word_data.get("meanings", [])

            for meaning in meanings[:3]:
                part_of_speech = meaning.get("partOfSpeech", "unknown").upper()
                definitions_list = meaning.get("definitions", [])

                def_text = ""
                for idx, d_obj in enumerate(definitions_list[:2], start=1):
                    definition = d_obj.get("definition", "No definition given.")
                    def_text += f"**{idx}.** {definition}\n"

                    example = d_obj.get("example")
                    if example:
                        def_text += f"   *\" {example} \"*\n"

                if def_text:
                    embed.add_field(name=f"<:spark:1517583248421552305> {part_of_speech}", value=_shorten(def_text, 1024), inline=False)

            embed.set_footer(text="Data sourced from Wiktionary API")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error executing /def command: {e}")
            await interaction.followup.send("<:disapprove:1517452151012589662> An internal error occurred while fetching the definition.", ephemeral=True)

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
        try:
            if action == "encode":
                text_bytes = text.encode("utf-8")
                if encoding_type == "base64":
                    result = base64.b64encode(text_bytes).decode("utf-8")
                elif encoding_type == "base32":
                    result = base64.b32encode(text_bytes).decode("utf-8")
                elif encoding_type == "base16":
                    result = base64.b16encode(text_bytes).decode("utf-8")
                elif encoding_type == "binary":
                    result = " ".join(f"{ord(char):08b}" for char in text)
                title_text = f"<:locked:1517574877257924809> {encoding_type} Encoding Complete"
                field_name = "Encoded Result:"
                color_choice = discord.Color.red()
            else:
                if encoding_type == "base64":
                    result = base64.b64decode(text.encode("utf-8")).decode("utf-8")
                elif encoding_type == "base32":
                    result = base64.b32decode(text.encode("utf-8")).decode("utf-8")
                elif encoding_type == "base16":
                    result = base64.b16decode(text.encode("utf-8")).decode("utf-8")
                elif encoding_type == "binary":
                    binary_values = text.split()
                    result = "".join(chr(int(b, 2)) for b in binary_values)
                title_text = f"<:unlocked:1517574880034558102> {encoding_type} Decoding Complete"
                field_name = "Decoded Plain Text Result:"
                color_choice = discord.Color.green()
        except Exception as e:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:disapprove:1517452151012589662> Operation failed. Please check that your input perfectly matches the formatting for {encoding_type}! Error: {e}",
                ephemeral=True
            )
            return

        if len(result) > 1000:
            result = result[:950] + "\n\n*(Truncated due to size limits...)*"
        shown_input = text if len(text) <= 1000 else text[:950] + "..."

        embed = discord.Embed(title=title_text, color=color_choice)
        embed.add_field(name="Input:", value=f"`{shown_input}`", inline=False)
        embed.add_field(name=field_name, value=f"`{result}`", inline=False)
        embed.set_footer(text=f"Processed for {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.defer(); await interaction.followup.send(embed=embed)


    @app_commands.command(name='translate', description='Translate text into another language')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(text='The message you want to translate', to_language='The language code to translate into (e.g. en, es, fr, ja)', from_language='Optional: Specify the original language code (defaults to auto-detect)')
    async def translate(self, interaction: discord.Interaction, text: str, to_language: str = 'en', from_language: str = 'auto'):
        if interaction.guild and await run_automod_check_for_interaction(interaction, text, source_label="/translate"):
            return

        user_id = interaction.user.id
        now = time.monotonic()
        last_call = self.translation_cooldowns.get(user_id, 0.0)
        if now - last_call < 3.0:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Please wait a moment before translating again. Google rate-limits translations per user.", ephemeral=True)
            return

        normalized_to = normalize_language_code(to_language, default=None, strict=True)
        normalized_from = normalize_language_code(from_language, default="auto", strict=True)

        if normalized_to is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Invalid target language. Use a valid language code or name like `fr`, `en`, or `french`.", ephemeral=True)
            return

        if normalized_from is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Invalid source language. Use a valid language code or name like `fr`, `en`, or `french`.", ephemeral=True)
            return

        if normalized_from == "auto":
            source_lang = "auto"
        else:
            source_lang = normalized_from

        if normalized_to == "auto":
            normalized_to = "en"

        self.translation_cooldowns[user_id] = now
        await interaction.response.defer(ephemeral=False)
        try:
            if Translator is None:
                await interaction.followup.send("<:disapprove:1517452151012589662> Translation is unavailable because the `googletrans` package is not installed.", ephemeral=True)
                return

            async def _translate_block() -> str:
                translator = Translator()
                result = await translator.translate(text, src=source_lang, dest=normalized_to)
                return result.text

            translated_text = await asyncio.wait_for(_translate_block(), timeout=10)
            await interaction.followup.send(content=_shorten(translated_text, 2000))
        except asyncio.TimeoutError:
            await interaction.followup.send("<:disapprove:1517452151012589662> Translation timed out. Please try again in a moment.", ephemeral=True)
        except Exception as e:
            error_text = str(e).lower()
            if "too many requests" in error_text or "rate limit" in error_text or "rate-limited" in error_text:
                await interaction.followup.send("<:disapprove:1517452151012589662> Google is rate-limiting translation requests right now. Please wait a moment and try again.", ephemeral=True)
            else:
                await interaction.followup.send(f"<:disapprove:1517452151012589662> Translation failed. Please ensure you used valid language codes or names! Error: {e}", ephemeral=True)

    @app_commands.command(name='gif', description='Convert an image attachment into a GIF file')
    @app_commands.default_permissions(attach_files=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(image='The image to convert to GIF')
    async def gif(self, interaction: discord.Interaction, image: discord.Attachment):
        await interaction.response.defer(ephemeral=True)

        if not image:
            await interaction.followup.send("<:disapprove:1517452151012589662> Please attach an image to convert.", ephemeral=True)
            return

        try:
            image_bytes = await image.read()
            # Converting (especially animated images) is CPU-heavy; keep it off the event loop.
            buffer = await asyncio.to_thread(_convert_bytes_to_gif, image_bytes)
            await interaction.followup.send(file=discord.File(buffer, filename="converted.gif"))

        except Exception as e:
            await interaction.followup.send(
                f"<:disapprove:1517452151012589662> Failed to convert the image to GIF. Please make sure the file is a valid image. Error: {e}",
                ephemeral=True
            )

    @app_commands.command(name='serverinfo', description='Display detailed information about this server')
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This command must be used in a server.", ephemeral=True)
            return
        created_at = discord_timestamp(guild.created_at)
        joined_at = discord_timestamp(interaction.user.joined_at) if getattr(interaction.user, "joined_at", None) else "Unknown"
        total_count = guild.member_count
        bot_count = len([m for m in guild.members if m.bot])
        human_count = total_count - bot_count
        owner_text = format_user_reference(guild.owner) if guild.owner else f"<@{guild.owner_id}>"

        embed = discord.Embed(title=f"Information for {guild.name}", color=discord.Color.blue())
        embed.add_field(name="<:chalice:1517579767573123092> Server Owner", value=owner_text, inline=True)
        embed.add_field(name="<:timer:1517996239583576194> Created At", value=created_at, inline=True)
        embed.add_field(name="<:plus:1518348756570079262> Joined At (user)", value=joined_at, inline=True)
        vanity = guild.vanity_url_code if guild.vanity_url_code else "-"
        embed.add_field(name="<:minus:1518348754111959150> Vanity Link", value=vanity, inline=True)
        embed.add_field(name="<:internet:1518376144246804672> Preferred Locale", value=f"{guild.preferred_locale}", inline=True)
        embed.add_field(name="<:shield:1518340640801427566> Verification Level", value=str(guild.verification_level).capitalize(), inline=True)
        boost_info = f"{guild.premium_subscription_count} (Level {guild.premium_tier})"
        embed.add_field(name="<:spark:1517583248421552305> Server Boosts", value=boost_info, inline=True)
        embed.add_field(name="<:drawer:1517497564189036574> Channels", value=f"{len(guild.channels)}", inline=True)
        embed.add_field(name="<:multi:1518348755261460661> Roles", value=f"{len(guild.roles)}", inline=True)
        embed.add_field(name="\n<:graph:1517584522877866065> Members", value=" ", inline=False)
        embed.add_field(name="<:approuve:1517452125687513158> Real Accounts", value=str(human_count), inline=True)
        embed.add_field(name="<:disapprove:1517452151012589662> Bots", value=str(bot_count), inline=True)
        embed.add_field(name="<:warning:1517452174991556758> Total", value=str(total_count), inline=True)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await interaction.response.defer(); await interaction.followup.send(embed=embed)

    @app_commands.command(name='channelinfo', description='Show configured channels for this server')
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def channelinfo(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This command must be used in a server.", ephemeral=True)
            return

        guild = interaction.guild
        guild_id = str(guild.id)

        guild_config, _ = save.get_guild_config(guild_id)
        levels = save.load_levels()
        board_data = save.load_board_data()

        def fmt_channel(cid):
            if not cid:
                return "Not set"
            try:
                cid_int = int(cid)
            except Exception:
                return str(cid)
            ch = guild.get_channel(cid_int)
            if ch is not None:
                return ch.mention
            return f"<#{cid_int}>"

        welcome = fmt_channel(guild_config.get("welcome_channel_id"))
        goodbye = fmt_channel(guild_config.get("goodbye_channel_id"))

        lvl_channel = "Not set"
        if guild_id in levels:
            lvl_channel_id = levels[guild_id].get("config", {}).get("channel_id")
            if lvl_channel_id:
                lvl_channel = fmt_channel(lvl_channel_id)

        board_entries = []
        if guild_id in board_data:
            for emoji_key, cfg in board_data[guild_id].items():
                ch_id = cfg.get("channel_id")
                required = cfg.get("required_count") or cfg.get("required") or cfg.get("required_count", None)
                channel_repr = fmt_channel(ch_id)

                req_text = f"required {required}" if required is not None else "required ?"
                board_entries.append(f"{emoji_key} in {channel_repr} ({req_text})")
        board_channels = "\n".join(board_entries) if board_entries else "None"

        counter_entries = []
        counters = guild_config.get("counter_channels", {})
        for ch_key, cfg in counters.items():
            try:
                ch = guild.get_channel(int(ch_key))
                ch_repr = ch.mention if ch else f"<#{ch_key}>"
            except Exception:
                ch_repr = str(ch_key)
            current_val = cfg.get("current_value", 0)
            counter_entries.append(f"{ch_repr}: {current_val}")
        counter_channels = "\n".join(counter_entries) if counter_entries else "None"

        admin_log_channels_list = get_admin_log_channel_mentions(guild)
        admin_log_channel = "\n".join(admin_log_channels_list) if admin_log_channels_list else "Not set"

        honeypot_channel = fmt_channel(guild_config.get("honeypot_channel_id"))

        embed = discord.Embed(title=f"<:drawer:1517497564189036574> Configured Channels for {guild.name}", color=discord.Color.blurple())
        embed.add_field(name="<:plus:1518348756570079262> Welcome Channel", value=welcome, inline=False)
        embed.add_field(name="<:minus:1518348754111959150> Goodbye Channel", value=goodbye, inline=False)
        embed.add_field(name="<:chalice:1517579767573123092> Level-up and Quest Announce Channel", value=lvl_channel, inline=False)
        embed.add_field(name="<:graph:1517584522877866065> Board Channels", value=_shorten(board_channels, 1024), inline=False)
        embed.add_field(name="<:list:1517497572770451567> Counter Channels", value=_shorten(counter_channels, 1024), inline=False)
        embed.add_field(name="<:unlocked:1517574880034558102> Admin Log Channel", value=_shorten(admin_log_channel, 1024), inline=False)
        embed.add_field(name="<:honey:1524116282075512842> Honeypot Channel", value=honeypot_channel, inline=False)
        embed.set_footer(text="Run /settings and go to channel settings to change these settings.")

        await interaction.response.defer(); await interaction.followup.send(embed=embed)

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
        if interaction.guild and await run_automod_check_for_interaction(interaction, message, source_label="/say"):
            return

        await interaction.response.defer()
        await interaction.followup.send(message)


class HelpSearchModal(discord.ui.Modal):
    def __init__(self, help_view):
        super().__init__(title='Search help')
        self.help_view = help_view
        self.query = discord.ui.TextInput(label='Command, category, or keyword', placeholder='Try: economy, ping, fun', required=True, max_length=100)
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        search_value = (self.query.value or '').strip().lower()
        defs = save.load_help_definitions()
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
        defs = save.load_help_definitions()
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
