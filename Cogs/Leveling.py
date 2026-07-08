import random

import discord
from discord import app_commands
from discord.ext.commands import Cog, Context, hybrid_group
from discord.ext import tasks

from Shared.Leveling import add_xp, load_levels, get_xp_needed, save_levels, format_level_reward_summary
from Shared.User import get_user_color, format_user_reference
from main import COLOR_EMOJIS


async def setup(bot):
    bot.add_cog(Leveling(bot))

class Leveling(Cog):
    def __init__(self, bot):
        self.bot = bot

    @tasks.loop(minutes=2.0)
    async def voice_xp_tracker(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            for voice_channel in guild.voice_channels:
                real_members = [m for m in voice_channel.members if
                                not m.bot and not m.voice.self_deaf and not m.voice.deaf]
                if len(real_members) >= 1:
                    for member in real_members:
                        await add_xp(self.bot, member, guild, random.randint(5, 10))

    @hybrid_group(name="level", description="View your current server tier standing level rank card")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def view_level(self, ctx: Context, user: discord.Member = None):
        target = user or ctx.author
        levels = load_levels()
        g_id, u_id = str(ctx.guild.id), str(target.id)

        user_data = levels.get(g_id, {}).get("users", {}).get(u_id, {"xp": 0, "level": 0, "color": "white"})

        current_xp = user_data["xp"]
        current_lvl = user_data["level"]
        chosen_color = get_user_color(u_id) or user_data.get("color", "white") or "white"

        xp_needed = get_xp_needed(current_lvl)

        ratio = current_xp / xp_needed if xp_needed > 0 else 0
        filled_blocks = min(max(int(ratio * 10), 0), 10)
        empty_blocks = 10 - filled_blocks

        filled_emoji = COLOR_EMOJIS.get(chosen_color, "<:Square_White:1517679898414813427>")
        empty_emoji = COLOR_EMOJIS.get("black", "<:Square_Black:1517679889615032540>")

        progress_bar = (filled_emoji * filled_blocks) + (empty_emoji * empty_blocks)

        embed = discord.Embed(
            title=f"<:chalice:1517579767573123092> Rank Profile - {target.display_name}",
            color=discord.Color.dark_gray()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Current Tier", value=f"<:spark:1517583248421552305> **Level {current_lvl}**", inline=True)
        embed.add_field(name="Experience Nodes",
                        value=f"<:Vial:1517681553377857628> `{current_xp:,}` / `{xp_needed:,}` XP", inline=True)
        embed.add_field(name="Progress Metrics", value=progress_bar, inline=False)

        await ctx.send(embed=embed)

    @view_level.command(name="lvl-leaderboard", description="Display the top 10 highest-level users in this guild")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def level_leaderboard(self, ctx: Context):
        levels = load_levels()
        g_id = str(ctx.guild.id)

        users_dict = levels.get(g_id, {}).get("users", {})
        if not users_dict:
            return await ctx.send("📭 No active XP statistics logged in this server yet.",
                                                           ephemeral=True)

        sorted_users = sorted(users_dict.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)

        embed = discord.Embed(
            title=f"<:graph:1517584522877866065> Level Standings Leaderboard - {ctx.guild.name}",
            color=discord.Color.gold())

        description_text = ""
        for index, (u_id, data) in enumerate(sorted_users[:10], start=1):
            member = ctx.guild.get_member(int(u_id))
            name_str = member.display_name if member else f"User left server (`{u_id}`)"
            description_text += f"`#{index}` **{name_str}** - Lvl {data['level']} ({data['xp']} XP)\n"

        embed.description = description_text
        await ctx.send(embed=embed)

    @view_level.command(name="lvl-edit",
                      description="(Admin) Manually adjust or set a target user's level and XP indexes")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def lvl_edit(self, ctx: Context, user: discord.Member, level: int, xp: int = 0):
        levels = load_levels()
        g_id, u_id = str(ctx.guild.id), str(user.id)

        if g_id not in levels: levels[g_id] = {"config": {}, "users": {}}

        levels[g_id]["users"][u_id] = {
            "xp": max(0, xp),
            "level": max(0, level),
            "color": levels[g_id]["users"].get(u_id, {}).get("color", "white")
        }
        save_levels(levels)
        await ctx.send(
            f"<:gear:1517576939097952496> Action complete. Set {format_user_reference(user)} to **Level {level}** with **{xp} XP**.",
            ephemeral=True)

    @view_level.command(name="info-lvl-rewards", description="Show the level rewards configured for this guild")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.describe(level="Optional specific level to inspect")
    async def info_lvl_rewards(self, ctx: Context, level: int = None):
        levels = load_levels()
        g_id = str(ctx.guild.id)
        guild_data = levels.get(g_id, {})
        rewards = guild_data.get("config", {}).get("rewards", {})

        if not rewards:
            return await ctx.send("📭 No level rewards are configured for this server yet.",
                                                           ephemeral=True)

        embed = discord.Embed(
            title=f"<:box:1517581439552585759> Level Rewards - {ctx.guild.name}",
            color=discord.Color.gold()
        )

        if level is not None:
            reward_data = rewards.get(str(level))
            if not reward_data:
                return await ctx.send(
                    f"<:disapprove:1517452151012589662> No rewards are configured for level {level} in this server.",
                    ephemeral=True)

            embed.description = format_level_reward_summary(ctx.guild, str(level), reward_data)
        else:
            sorted_levels = sorted(rewards.items(), key=lambda item: int(item[0]))
            embed.description = "\n".join(
                format_level_reward_summary(ctx.guild, lvl, reward_data)
                for lvl, reward_data in sorted_levels
            )

        await ctx.send(embed=embed)

    @view_level.command(name="lvl-rewards-del", description="(Admin) Delete all rewards configured for a level")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(level="The level whose rewards should be removed")
    async def lvl_rewards_del(self, ctx: Context, level: int):
        levels = load_levels()
        g_id = str(ctx.guild.id)

        if g_id not in levels or "config" not in levels[g_id] or "rewards" not in levels[g_id]["config"]:
            return await ctx.send(
                f"<:disapprove:1517452151012589662> No rewards are configured for level {level} in this server.",
                ephemeral=True)

        rewards = levels[g_id]["config"]["rewards"]
        if str(level) not in rewards:
            return await ctx.send(
                f"<:disapprove:1517452151012589662> No rewards are configured for level {level} in this server.",
                ephemeral=True)

        del rewards[str(level)]
        save_levels(levels)

        await ctx.send(
            f"<:trash:1517497581058527404> Removed all rewards configured for level {level}.", ephemeral=True)
