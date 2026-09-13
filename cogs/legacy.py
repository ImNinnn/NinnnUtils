"""Legacy prefix commands and owner-only maintenance commands."""

import io
import json
import os
import time

import discord
from discord.ext import commands

import helper as main
from utils.banners import create_banner_preview


class LegacyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api = main

    async def _is_owner(self, user: discord.User | None) -> bool:
        return await self.bot.is_owner(user)

    @commands.command(name='say')
    async def say(self, ctx: commands.Context, *, message: str):
        is_bot_owner = await self._is_owner(ctx.author)
        is_server_owner = bool(ctx.guild and ctx.author == ctx.guild.owner)
        is_admin = bool(
            ctx.guild and isinstance(ctx.author, discord.Member) and (
                ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild
            )
        )

        if not (is_bot_owner or is_server_owner or is_admin):
            return await ctx.send(f"<:disapprove:1517452151012589662> this {main.PREFIX} command is restricted to the bot owner, server owner, or admins only.")

        if ctx.guild and await main.run_automod_check_for_content(ctx.guild, ctx.author, ctx.channel, message, source_label='/say'):
            return

        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        await ctx.send(message)

    @commands.command(name='json')
    async def json_cmd(self, ctx: commands.Context, file: str, target_id: str | None = None):
        if not await self._is_owner(ctx.author):
            return await ctx.send(f"<:disapprove:1517452151012589662> the {main.PREFIX} prefix is restricted to the bot owner only.")

        loaders = {
            'giveaway': main.load_giveaway_data,
            'giveaways': main.load_giveaway_data,
            'quest': main.load_quest_data,
            'quests': main.load_quest_data,
            'data': main.load_data,
            'economy': main.load_data,
            'level': main.load_levels,
            'levels': main.load_levels,
            'guild': main.load_guild_data,
            'guilds': main.load_guild_data,
            'settings': main.load_user_settings,
            'user': main.load_user_settings,
        }

        kind = (file or '').lower()
        loader = loaders.get(kind)
        if not loader:
            await ctx.send('Unknown file. Valid options: giveaway, quest, data, level, guild, settings')
            return

        try:
            data = loader()
        except Exception as exc:
            await ctx.send(f'Failed to load data: {exc}')
            return

        if target_id:
            key = str(target_id)
        else:
            if ctx.guild and kind not in {'settings', 'user'}:
                key = str(ctx.guild.id)
            else:
                key = str(ctx.author.id)

        try:
            part = data.get(key) if isinstance(data, dict) else data
        except Exception:
            part = data

        try:
            text = json.dumps(part, indent=2, default=str)
        except Exception:
            text = str(part)

        if len(text) > 1900:
            buf = io.BytesIO(text.encode('utf-8'))
            buf.seek(0)
            await ctx.send(file=discord.File(buf, filename=f'{kind}_{key}.json'))
        else:
            await ctx.send(f'```json\n{text}\n```')

    @commands.command(name='help')
    async def help_cmd(self, ctx: commands.Context):
        await main.legacy_prefix_help.callback(ctx)

    @commands.command(name='ping')
    async def ping(self, ctx: commands.Context):
        await main.legacy_prefix_ping.callback(ctx)

    @commands.command(name='stats')
    async def stats(self, ctx: commands.Context):
        await main.legacy_prefix_stats.callback(ctx)

    @commands.command(name='ver')
    async def ver(self, ctx: commands.Context, *, new_value: str = ''):
        await main.set_bot_version.callback(ctx, new_value)

    @commands.command(name='alt')
    async def alt(self, ctx: commands.Context, *, new_value: str = ''):
        await main.set_bot_alt_version.callback(ctx, new_value)

    @commands.command(name='activity')
    async def activity(self, ctx: commands.Context, *, new_value: str = ''):
        await main.set_bot_activity.callback(ctx, new_value)

    @commands.command(name='banner')
    async def banner(self, ctx: commands.Context, *args: str):
        await main.banner_preview_command.callback(ctx, *args)

    @commands.command(name='backups')
    async def backups(self, ctx: commands.Context):
        await main.backups_command.callback(ctx)

    @commands.command(name='shutdown')
    async def shutdown(self, ctx: commands.Context, *, args: str = ''):
        await main.own_shutdown.callback(ctx, args)

    @commands.command(name='servers')
    async def servers(self, ctx: commands.Context):
        await main.list_servers.callback(ctx)


async def setup(bot):
    await bot.add_cog(LegacyCog(bot))
