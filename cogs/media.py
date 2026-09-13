"""Media-generation commands."""

import discord
from discord import app_commands
from discord.ext import commands

from utils.banners import create_banner_preview


async def _safe_followup(interaction: discord.Interaction, *, content: str | None = None, file=None, embed=None, ephemeral: bool = False):
    payload = {}
    if content is not None:
        payload['content'] = content
    if file is not None:
        payload['file'] = file
    if embed is not None:
        payload['embed'] = embed

    if interaction.response.is_done():
        return await interaction.followup.send(ephemeral=ephemeral, **payload)

    try:
        if file is not None or embed is not None:
            return await interaction.response.send_message(ephemeral=ephemeral, **payload)
        return await interaction.response.send_message(content=content or '', ephemeral=ephemeral)
    except Exception:
        return await interaction.followup.send(ephemeral=ephemeral, **payload)


class MediaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='avatar', description='Get the profile picture of a user')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.describe(user='The user to get the avatar from')
    async def avatar(self, interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user
        embed = discord.Embed(title=f"{user.name}'s Avatar", color=discord.Color.blue())
        embed.set_image(url=user.display_avatar.url)
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)

    @app_commands.command(name='banner', description='Get the profile banner of a user')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.describe(user='The user to get the banner from')
    @app_commands.describe(kind='Optional: preview type to generate')
    @app_commands.choices(
        kind=[
            app_commands.Choice(name='User banner', value='user'),
            app_commands.Choice(name='Welcome preview', value='welcome'),
            app_commands.Choice(name='Goodbye preview', value='goodbye'),
            app_commands.Choice(name='Levelup preview', value='level'),
            app_commands.Choice(name='Quest preview', value='quest'),
        ]
    )
    async def banner(self, interaction: discord.Interaction, user: discord.Member = None, kind: str = 'user'):
        user = user or interaction.user
        kind = (kind or 'user').lower()

        if kind == 'user':
            full_user = await self.bot.fetch_user(user.id)
            if full_user.banner:
                embed = discord.Embed(title=f"{user.name}'s Banner", color=discord.Color.blue())
                embed.set_image(url=full_user.banner.url)
                await _safe_followup(interaction, embed=embed)
                return

            await _safe_followup(interaction, content=f"{user.name} does not have a banner.", ephemeral=True)
            return

        try:
            file = await create_banner_preview(user, kind)
            if file:
                await _safe_followup(interaction, file=file)
                return
        except Exception:
            pass

        await _safe_followup(interaction, content=f"Unable to generate {kind} banner preview for {user.display_name}.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(MediaCog(bot))
