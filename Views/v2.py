import discord
from discord.ui import LayoutView, Container, Separator, TextDisplay


class V2InfoContainerView(LayoutView):
    def __init__(self, title: str, description: str, accent_color: discord.Color):
        super().__init__(timeout=180)
        container = Container(
            TextDisplay(title),
            Separator(),
            TextDisplay(description),
            accent_color=accent_color,
        )
        self.add_item(container)
