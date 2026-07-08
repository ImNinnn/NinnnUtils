from discord.ext.commands import Cog, hybrid_group, Context, has_permissions
from discord import app_commands
import discord
from datetime import datetime, timedelta

from LowerLeveled.owner import guild_owner_bypasses_role_checks
from Shared.Cache import clean_cache
from Shared.Errors import add_bot_error_entry
from Shared.User import format_user_reference


async def setup(bot):
    await bot.add_cog(Admin(bot))

class Admin(Cog):
    def __init__(self, bot):
        self.bot = bot

    @hybrid_group(name="adm", description="Admin Commands", invoke_without_command=True)
    async def a(self, ctx): pass

    @a.group(name="purge", description="Mass delete messages from the channel", invoke_without_command=False)
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(
        amount="Number of messages to delete",
        user="Optional: Only delete messages from this specific user"
    )
    @has_permissions(manage_messages=True)
    async def purge(self, ctx: Context, amount: int, user: discord.Member = None):
        if amount <= 0:
            await ctx.send(
                "<:disapprove:1517452151012589662> Please specify a number greater than 0.", ephemeral=True)
            return
        if amount > 100:
            await ctx.send(
                "<:warning:1517452174991556758> For safety, you can only purge up to 100 messages at a time.",
                ephemeral=True)
            return

        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=False)

        def is_user(m):
            return m.author == user if user else True

        try:
            deleted = await ctx.channel.purge(limit=amount, check=is_user, before=datetime.now())
            user_str = f" from {format_user_reference(user)}" if user else ""
            await ctx.send(
                f"<:explosive:1517578642723573880> Successfully deleted **{len(deleted)}** messages{user_str}.",
                ephemeral=False)
        except Exception as e:
            await ctx.send(f"<:disapprove:1517452151012589662> Failed to purge messages. Error: {e}",
                                            ephemeral=True)

    @a.command(name="rename", description="Rename a user or reset their nickname")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.describe(
        user="The member you want to rename",
        name="The new nickname (leave empty to reset to original name)"
    )
    @has_permissions(manage_nicknames=True)
    async def rename(self, ctx: Context, user: discord.Member, name: str = None):
        if ctx.guild.me.top_role <= user.top_role:
            await ctx.send(
                "<:disapprove:1517452151012589662> I cannot rename this user. Their role is higher than or equal to mine!",
                ephemeral=True)
            return
        try:
            old_name = user.display_name
            await user.edit(nick=name)
            if name:
                await ctx.send(
                    f"<:approve:1517452125687513158> Changed **{old_name}**'s nickname to **{name}**.")
            else:
                await ctx.send(
                    f"<:approve:1517452125687513158> Reset **{old_name}**'s nickname to their original username.")
        except discord.Forbidden:
            await ctx.send(
                "<:disapprove:1517452151012589662> I don't have the 'Manage Nicknames' permission or the user is the Server Owner.",
                ephemeral=True)
        except Exception as e:
            await ctx.send(f"<:disapprove:1517452151012589662> An error occurred: {e}",
                                                    ephemeral=True)

    @purge.command(name="nuke", description="Fully clear a channel")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_channels=True)
    @has_permissions(manage_channels=True)
    async def nuke(self, ctx: Context, archive: bool = False):
        try:
            channel = await ctx.guild.fetch_channel(ctx.channel.id)
        except discord.Forbidden:
            await ctx.send(
                "<:disapprove:1517452151012589662> I cannot 'see' this channel. Please check my permissions in this specific channel's settings.",
                ephemeral=True)
            return

        GIF_URL = "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExN2x1ZW82ZGdlZzV1MTFzNGF6ajJzZ3Bmc3I2MDlxaXp0cWpkcTY4YyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/fXhYwggfsp3yHBsdlr/giphy.gif"

        await ctx.send("<:explosive:1517578642723573880> Target locked. Nuking...",
                                                ephemeral=False)
        new_channel = await channel.clone(reason=f"Nuke by {ctx.author}")
        await new_channel.edit(position=channel.position)

        embed = discord.Embed(
            title="<:nuke:1517497573986926732> Channel Nuked",
            description=f"This is {format_user_reference(ctx.author)}'s fault, THEY DID THIS",
            color=discord.Color.red()
        )
        embed.set_image(url=GIF_URL)
        try:
            await new_channel.send(embed=embed)
        except discord.Forbidden as error:
            add_bot_error_entry(ctx.guild.id, new_channel.id, ctx.author, "nuke result message", error)

        try:
            if archive:
                everyone_role = ctx.guild.default_role
                await channel.edit(
                    name=f"{channel.name}-archived",
                    overwrites={everyone_role: discord.PermissionOverwrite(view_channel=False)},
                    reason="Channel Archived via Nuke"
                )
            else:
                await channel.delete(reason="Nuked")
        except discord.Forbidden:
            try:
                await new_channel.send(
                    "<:warning:1517452174991556758> **Warning:** I couldn't delete or hide the old channel. Check if my role is high enough!")
            except discord.Forbidden as error:
                add_bot_error_entry(ctx.guild.id, new_channel.id, ctx.channel.id, "nuke cleanup warning",
                                    error)
        except Exception as e:
            print(f"Error during nuke cleanup: {e}")

    @a.command(name="timeout", description="Timeout a member for a specific duration")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(
        member="The member to timeout",
        days="Number of days",
        hours="Number of hours",
        minutes="Number of minutes",
        seconds="Number of seconds",
        reason="Why is this user being timed out?"
    )
    @has_permissions(moderate_members=True)
    async def timeout(self, ctx: Context, member: discord.Member, days: int = 0, hours: int = 0,
                      minutes: int = 0, seconds: int = 0, reason: str = "No reason provided"):
        duration = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        if duration.total_seconds() <= 0:
            await ctx.send(
                "<:disapprove:1517452151012589662> You must specify a duration greater than 0!",
                ephemeral=True
            )
            return
        if duration.total_seconds() > 2419200:
            await ctx.send(
                "<:disapprove:1517452151012589662> Timeout cannot exceed 28 days.",
                ephemeral=True
            )
            return

        if not guild_owner_bypasses_role_checks(
                ctx) and ctx.author != member and member.top_role >= ctx.author.top_role:
            await ctx.send(
                "<:disapprove:1517452151012589662> You cannot timeout someone with an equal or higher role than yours.",
                ephemeral=True
            )
            return

        time_str = f"{days}d {hours}h {minutes}m {seconds}s"
        if not member.bot:
            try:
                dm_embed = discord.Embed(
                    title="<:hourglass:1517574046252924938> You have been timed out",
                    description=f"**Server:** {ctx.guild.name}\n**Duration:** {time_str}\n**Reason:** {reason}",
                    color=discord.Color.orange()
                )
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            await member.timeout(duration, reason=reason)
            confirm_embed = discord.Embed(
                title="<:approve:1517452125687513158> User Timed Out",
                description=f"**{format_user_reference(member)}** has been timed out for {time_str}.",
                color=discord.Color.green()
            )
            confirm_embed.add_field(name="Reason", value=reason)
            await ctx.send(embed=confirm_embed)
        except discord.Forbidden:
            await ctx.send(
                "<:disapprove:1517452151012589662> I don't have permission to timeout this user (Hierarchy issue).",
                ephemeral=True)
        except Exception as e:
            await ctx.send(f"<:disapprove:1517452151012589662> An error occurred: {e}",
                                                    ephemeral=True)

    @a.command(name="forget", description="Clear edited and deleted history of a chosen user")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.default_permissions(manage_messages=True)
    @has_permissions(manage_messages=True)
    async def adm_forget(self, ctx: Context, user: discord.Member):
        clean_cache()
        global message_cache, deleted_cache, edited_cache
        message_cache = [m for m in message_cache if m['author'].id != user.id]
        deleted_cache = [m for m in deleted_cache if m['author'].id != user.id]
        edited_cache = [m for m in edited_cache if m['author'].id != user.id]
        await ctx.send(
            f"Cleared deleted and edited history for {user.display_name}."
        )
