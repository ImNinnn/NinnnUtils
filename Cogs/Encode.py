from discord.ext.commands import Cog, Context, hybrid_command
from discord import app_commands
import base64, discord

async def setup(bot):
    await bot.add_cog(Encode(bot))

class Encode(Cog):
    def __init__(self, bot):
        self.bot = bot

    @hybrid_command(name="encode", description="Encode text with a few algos (Base64, Base32, Base16, Binary)")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        text="The text you want to process",
        encoding_type="Choose the format method"
    )
    @app_commands.choices(
        encoding_type=[
            app_commands.Choice(name="Base64", value="base64"),
            app_commands.Choice(name="Base32", value="base32"),
            app_commands.Choice(name="Base16 (Hex)", value="base16"),
            app_commands.Choice(name="Binary", value="binary")
        ],
    )
    async def encode_decode_command(self, ctx: Context, text: str, encoding_type: str):
        try:
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

            if len(result) > 1000:
                result = result[:950] + "\n\n*(Truncated due to size limits...)*"

            embed = discord.Embed(title=title_text, color=color_choice)
            embed.add_field(name="Input:", value=f"`{text}`", inline=False)
            embed.add_field(name=field_name, value=f"`{result}`", inline=False)
            embed.set_footer(text=f"Processed for {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(
                f"<:disapprove:1517452151012589662> Operation failed. Please check that your input perfectly matches the formatting for {encoding_type}! Error: {e}",
                ephemeral=True
            )

    @hybrid_command(name="decode", description="Decode text in a few algos back to normal text (Base64, Base32, Base16, Binary)")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        text="The text you want to process",
        encoding_type="Choose the format method"
    )
    @app_commands.choices(
        encoding_type=[
            app_commands.Choice(name="Base64", value="base64"),
            app_commands.Choice(name="Base32", value="base32"),
            app_commands.Choice(name="Base16 (Hex)", value="base16"),
            app_commands.Choice(name="Binary", value="binary")
        ],
    )
    async def decode_command(self, ctx, text: str, encoding_type: str):
        try:
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
            
            if len(result) > 1000:
                result = result[:950] + "\n\n*(Truncated due to size limits...)*"

            embed = discord.Embed(title=title_text, color=color_choice)
            embed.add_field(name="Input:", value=f"`{text}`", inline=False)
            embed.add_field(name=field_name, value=f"`{result}`", inline=False)
            embed.set_footer(text=f"Processed for {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(
                f"<:disapprove:1517452151012589662> Operation failed. Please check that your input perfectly matches the formatting for {encoding_type}! Error: {e}",
                ephemeral=True
            )