from discord.ui import *
from discord.ext.commands import Context, Cog, hybrid_command
from discord import app_commands
import discord
from Views.CustomEmbed import CustomEmbedModal

async def setup(bot):
    await bot.add_cog(Embed())

class ClickMeView(LayoutView):
    def __init__(self):
        super().__init__(timeout=180)

    async def on_timeout(self):
        button: Button = self.children[1]
        button.disabled = True

class Embed(Cog):
    @hybrid_command(name="embed", description="Create a fully-loaded customized embed message using a styling menu")
    @app_commands.describe(
        color="Choose a preset theme color for the embed accent line",
        footer="Optional: Custom text at the very bottom row of the embed",
        footer_icon="Optional: Direct image URL for a tiny icon next to the footer text",
        thumbnail="Optional: Direct image URL to place as a small card in the top right",
        image="Optional: Direct image URL to place as a giant full-width display banner"
    )
    @app_commands.choices(
        color=[
            app_commands.Choice(name="🔴 Red", value="red"),
            app_commands.Choice(name="🔵 Blue", value="blue"),
            app_commands.Choice(name="🟢 Green", value="green"),
            app_commands.Choice(name="🟡 Yellow", value="yellow"),
            app_commands.Choice(name="🟣 Purple", value="purple"),
            app_commands.Choice(name="⚫ Dark Grey", value="dark"),
            app_commands.Choice(name="<:spark:1517583248421552305> Random Color", value="random")
        ]
    )
    async def embed_builder(
            self,
            ctx: Context,
            color: str = "blue",
            footer: str = None,
            footer_icon: str = None,
            thumbnail: str = None,
            image: str = None
    ):
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
        if ctx.interaction:
            await ctx.interaction.response.send_modal(modal)
        else:
            view = LayoutView(timeout=180)
            btn = Button(label="Trigger Modal")
            view.add_item(TextDisplay("Click below to construct an embed"))
            async def interact(interaction):
                await interaction.response.send_modal(modal)
            btn.callback = interact
            view.add_item(btn)

            await ctx.send(view=view)