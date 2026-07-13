from discord.ext.commands import Cog, hybrid_command, Context
import discord
from discord import app_commands

from Shared.AFK import set_afk_status, get_afk_reason, get_afk_status_key
from Shared.User import get_user_color_value
from Views.Settings import SettingsMenuView
from main import afk_status


async def setup(bot):
    await bot.add_cog(Settings(bot))

class Settings(Cog):
    def __init__(self, bot):
        self.bot = bot

    @hybrid_command(name="settings", description="Open a quick settings menu for your personal and guild preferences")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def settings(self, ctx: Context):
        view = SettingsMenuView(
            ctx.author.id,
            ctx.author.display_name,
            get_user_color_value(str(ctx.author.id)),
        )
        await ctx.send(view=view, ephemeral=True)

    @hybrid_command(name="afk", description="Set yourself as AFK with a reason")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.describe(reason="Why you're going AFK")
    async def afk_command(self, ctx: Context, reason: str = None):
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        member = ctx.author
        if not isinstance(member, discord.Member):
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        reason_text = (reason or "No reason provided.").strip() or "No reason provided."
        already_afk = await set_afk_status(member, reason_text)
        if already_afk:
            await ctx.send(
                f"<:afk:1525440143245180970> {member.mention} is now AFK. Reason: {reason_text}")
        else:
            current_reason = get_afk_reason(afk_status.get(get_afk_status_key(member.guild.id, member.id)))
            await ctx.send(
                f"<:warning:1517452174991556758> You are already AFK. Reason: {current_reason}", ephemeral=True)
