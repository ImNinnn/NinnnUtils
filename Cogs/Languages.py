from discord.ext.commands import Cog, Context, hybrid_group
from discord import app_commands, Embed, Color
import asyncio, aiohttp, discord
from deep_translator import GoogleTranslator

async def setup(bot):
    await bot.add_cog(Languages(bot))

class Languages(Cog):
    def __init__(self, bot):
        self.bot = bot

    @hybrid_group(name="language", description="Language utilities", invoke_without_command=True)
    async def l(self, ctx): pass

    @l.command(name="definition", description="Look up the dictionary definition of a word")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(word="The word you want to define")
    async def define_word(self, ctx: Context, word: str):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        
        clean_word = word.strip().lower()
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{clean_word}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    
                    if response.status == 404:
                        return await ctx.send(
                            f"<:disapprove:1517452151012589662> Could not find a definition for **{word}**. Double check your spelling!",
                            ephemeral=True
                        )
                    
                    if response.status != 200:
                        return await ctx.send(
                            "<:warning:1517452174991556758> The dictionary service is currently unavailable. Please try again later.", 
                            ephemeral=True
                        )
                    
                    data = await response.json()
                    
            word_data = data[0]
            word_name = word_data.get("word", clean_word).title()
            phonetic = word_data.get("phonetic", "N/A")
            
            embed = discord.Embed(
                title=f"<:list:1517497572770451567> Dictionary Definition: {word_name}",
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
                    embed.add_field(name=f"<:spark:1517583248421552305> {part_of_speech}", value=def_text, inline=False)
                    
            embed.set_footer(text="Data sourced from Wiktionary API")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"Error executing /def command: {e}")
            await ctx.send(
                "<:disapprove:1517452151012589662> An internal error occurred while fetching the definition.",
                ephemeral=True)

    @l.command(name="translate", description="Translate text into another language")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        text="The message you want to translate",
        to_language="The language code to translate into (e.g., 'en', 'es', 'fr', 'ja')",
        from_language="Optional: Specify the original language code (defaults to auto-detect)"
    )
    async def translate(self, ctx: Context, text: str, to_language: str = "en", from_language: str = "auto"):
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=False)
        try:
            translator = GoogleTranslator(source=from_language, target=to_language)
            translated_text = translator.translate(text)
            await ctx.send(content=translated_text)
        except Exception as e:
            await ctx.send(f"<:disapprove:1517452151012589662> Translation failed. Please ensure you used valid ISO language codes! Error: {e}", ephemeral=True)
