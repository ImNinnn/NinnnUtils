import asyncio

from discord.ext.commands import Cog, hybrid_group, Context, has_permissions
from discord import app_commands
import discord
from datetime import datetime, timedelta

from LowerLeveled.member import resolve_member_from_input
from LowerLeveled.owner import guild_owner_bypasses_role_checks
from LowerLeveled.timestamp import parse_duration_to_seconds
from LowerLeveled.validate import validate_role_selection
from Shared.Cache import clean_cache
from Shared.Errors import add_bot_error_entry
from Shared.Guilds import save_guild_data
from Shared.Moderation import get_guild_warnings, send_warning_dm, apply_warning_sanctions, add_guild_warning, \
    get_guild_automod_config
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
        member="The username, mention, or ID of the member to timeout",
        days="Number of days",
        hours="Number of hours",
        minutes="Number of minutes",
        seconds="Number of seconds",
        reason="Why is this user being timed out?"
    )
    @has_permissions(moderate_members=True)
    async def timeout(self, ctx: Context, member: discord.Member | None = None, days: int = 0,
                      hours: int = 0, minutes: int = 0, seconds: int = 0, reason: str = "No reason provided"):
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

        target_member = resolve_member_from_input(ctx.guild, member)
        if target_member is None:
            await ctx.send(
                "<:disapprove:1517452151012589662> I couldn't find that user in this server.", ephemeral=True)
            return

        if target_member == ctx.author:
            await ctx.send("<:disapprove:1517452151012589662> You cannot timeout yourself.",
                                                    ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(
                ctx) and ctx.author != member and member.top_role >= ctx.author.top_role:
            await ctx.send(
                "<:disapprove:1517452151012589662> You cannot timeout someone with an equal or higher role than yours.",
                ephemeral=True
            )
            return

        time_str = f"{days}d {hours}h {minutes}m {seconds}s"
        if not target_member.bot:
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
            await target_member.timeout(duration, reason=reason)
            confirm_embed = discord.Embed(
                title="<:approve:1517452125687513158> User Timed Out",
                description=f"**{format_user_reference(target_member)}** has been timed out for {time_str}.",
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

    @a.command(name="kick", description="Kick a member from the server")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(
        member="The username, mention, or ID of the member to kick",
        reason="Why is this user being kicked?"
    )
    @has_permissions(kick_members=True)
    async def kick(self, ctx: Context, member: discord.Member | None = None,
                   reason: str = "No reason provided"):
        target_member = resolve_member_from_input(ctx.guild, member)
        if target_member is None:
            await ctx.send(
                "<:disapprove:1517452151012589662> I couldn't find that user in this server.", ephemeral=True)
            return

        if target_member == ctx.author:
            await ctx.send("<:disapprove:1517452151012589662> You cannot kick yourself.",
                                                    ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(
                ctx) and ctx.author != target_member and target_member.top_role >= ctx.author.top_role:
            await ctx.send(
                "<:disapprove:1517452151012589662> You cannot kick someone with an equal or higher role than yours.",
                ephemeral=True)
            return

        if not target_member.bot:
            try:
                dm_embed = discord.Embed(
                    title="<:warning:1517452174991556758> You have been kicked",
                    description=f"**Server:** {ctx.guild.name}\n**Reason:** {reason}",
                    color=discord.Color.orange()
                )
                await target_member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            await target_member.kick(reason=reason)
            confirm_embed = discord.Embed(
                title="<:approuve:1517452125687513158> User Kicked",
                description=f"**{format_user_reference(target_member)}** has been kicked from the server.",
                color=discord.Color.green()
            )
            confirm_embed.add_field(name="Reason", value=reason)
            await ctx.send(embed=confirm_embed)
        except discord.Forbidden:
            await ctx.send(
                "<:disapprove:1517452151012589662> I don't have permission to kick this user (Hierarchy issue).",
                ephemeral=True)
        except Exception as e:
            await ctx.send(f"<:disapprove:1517452151012589662> An error occurred: {e}",
                                                    ephemeral=True)

    @a.command(name="ban", description="Ban a member from the server")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(
        member="The username, mention, or ID of the member to ban",
        reason="Why is this user being banned?",
        delete_days="How many days of recent messages to delete (0-7)"
    )
    @has_permissions(ban_members=True)
    async def ban(self, ctx: Context, member: discord.Member | None = None,
                  reason: str = "No reason provided", delete_days: int = 0):
        if delete_days < 0 or delete_days > 7:
            await ctx.send(
                "<:disapprove:1517452151012589662> Delete days must be between 0 and 7.", ephemeral=True)
            return

        target_member = resolve_member_from_input(ctx.guild, member)
        if target_member is None:
            await ctx.send(
                "<:disapprove:1517452151012589662> I couldn't find that user in this server.", ephemeral=True)
            return

        if target_member == ctx.author:
            await ctx.send("<:disapprove:1517452151012589662> You cannot ban yourself.", ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(
                ctx) and ctx.author != target_member and target_member.top_role >= ctx.author.top_role:
            await ctx.send(
                "<:disapprove:1517452151012589662> You cannot ban someone with an equal or higher role than yours.",
                ephemeral=True)
            return

        if not target_member.bot:
            try:
                dm_embed = discord.Embed(
                    title="<:dissaprouve:1517452151012589662> You have been banned",
                    description=f"**Server:** {ctx.guild.name}\n**Reason:** {reason}",
                    color=discord.Color.red()
                )
                await target_member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            await target_member.ban(reason=reason, delete_message_days=delete_days)
            confirm_embed = discord.Embed(
                title="<:approuve:1517452125687513158> User Banned",
                description=f"**{format_user_reference(target_member)}** has been banned from the server.",
                color=discord.Color.green()
            )
            confirm_embed.add_field(name="Reason", value=reason)
            if delete_days > 0:
                confirm_embed.add_field(name="Deleted Messages", value=f"{delete_days} day(s)", inline=True)
            await ctx.send(embed=confirm_embed)
        except discord.Forbidden:
            await ctx.send(
                "<:disapprove:1517452151012589662> I don't have permission to ban this user (Hierarchy issue).",
                ephemeral=True)
        except Exception as e:
            await ctx.send(f"<:disapprove:1517452151012589662> An error occurred: {e}",
                                                    ephemeral=True)

    @a.group(name="warn", description="Add or remove a warning for a user", invoke_without_command=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(moderate_members=True)
    #@app_commands.describe(
    #    member="The user to warn or remove a warning from",
    #    action="Whether to add or remove the warning",
    #    reason="The warning reason or removal note"
    #)
    @has_permissions(moderate_members=True)
    #@app_commands.choices(
    #    action=[app_commands.Choice(name="Add", value="add"), app_commands.Choice(name="Remove", value="remove"),
    #            app_commands.Choice(name="Clear", value="clear")])
    async def w(
            self,
            ctx: Context
    ):
        """pass"""
        """if member == ctx.author:
            await ctx.send("<:disapprove:1517452151012589662> You cannot warn yourself.",
                                                    ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(ctx) and member.top_role >= ctx.author.top_role:
            await ctx.send(
                "<:disapprove:1517452151012589662> You cannot manage warnings for someone with an equal or higher role than yours.",
                ephemeral=True)
            return

        user_warnings, data = get_guild_warnings(str(ctx.guild.id), member.id)

        if action == "add":
            warnings, data = await add_guild_warning(
                str(ctx.guild.id),
                member.id,
                reason,
                moderator_id=ctx.author.id,
                moderator_name=str(ctx.author),
            )

            if not member.bot:
                await send_warning_dm(member, ctx.guild, reason, total_warnings=len(warnings))

            total = len(warnings)
            await apply_warning_sanctions(member, ctx.guild, total)
            confirm_embed = discord.Embed(
                title="<:warning:1517452174991556758> Warning added",
                description=f"**{format_user_reference(member)}** has been warned.",
                color=discord.Color.orange()
            )
            confirm_embed.add_field(name="Reason", value=reason, inline=False)
            confirm_embed.add_field(name="Total warnings", value=str(total), inline=True)
            await ctx.send(embed=confirm_embed)
            return

        if action == "remove":
            if not user_warnings:
                await interaction.response.send_message(
                    f"<:disapprove:1517452151012589662> **{format_user_reference(member)}** has no warnings to remove.",
                    ephemeral=True)
                return

            removed = user_warnings.pop()
            save_guild_data(data)

            automod, automod_data = get_guild_automod_config(str(interaction.guild.id))
            sanction_state = automod.setdefault("warning_sanction_state", {})
            sanction_state[str(member.id)] = {"last_applied_warns": len(user_warnings)}
            save_guild_data(automod_data)

            if not member.bot:
                try:
                    dm_embed = discord.Embed(
                        title="<:warning:1517452174991556758> A warning has been removed",
                        description=f"**Server:** {interaction.guild.name}\n**Note:** {reason}",
                        color=discord.Color.green()
                    )
                    await member.send(embed=dm_embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass

            total = len(user_warnings)
            confirm_embed = discord.Embed(
                title="<:warning:1517452174991556758> Warning removed",
                description=f"A warning has been removed from **{format_user_reference(member)}**.",
                color=discord.Color.green()
            )
            confirm_embed.add_field(name="Removed warning reason", value=removed.get("reason", "No reason provided"),
                                    inline=False)
            confirm_embed.add_field(name="Note", value=reason, inline=False)
            confirm_embed.add_field(name="Remaining warnings", value=str(total), inline=True)
            await interaction.response.send_message(embed=confirm_embed)
            return

        if action == "clear":
            if not user_warnings:
                await interaction.response.send_message(
                    f"<:disapprove:1517452151012589662> **{format_user_reference(member)}** has no warnings to clear.",
                    ephemeral=True)
                return

            count = len(user_warnings)
            user_warnings.clear()
            save_guild_data(data)

            automod, automod_data = get_guild_automod_config(str(interaction.guild.id))
            sanction_state = automod.setdefault("warning_sanction_state", {})
            sanction_state.pop(str(member.id), None)
            save_guild_data(automod_data)

            if not member.bot:
                try:
                    dm_embed = discord.Embed(
                        title="<:warning:1517452174991556758> All warnings cleared",
                        description=f"**Server:** {interaction.guild.name}\n**Note:** {reason}",
                        color=discord.Color.green()
                    )
                    await member.send(embed=dm_embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass

            confirm_embed = discord.Embed(
                title="<:warning:1517452174991556758> Warnings cleared",
                description=f"All warnings have been cleared from **{format_user_reference(member)}**.",
                color=discord.Color.green()
            )
            confirm_embed.add_field(name="Cleared warnings", value=str(count), inline=True)
            confirm_embed.add_field(name="Note", value=reason, inline=False)
            await interaction.response.send_message(embed=confirm_embed)
            return
            """

        await ctx.send(
            "<:disapprove:1517452151012589662> Invalid action. Choose add, remove, or clear.", ephemeral=True)

    @w.command(name="add", description="Add a warning to a user")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(
        member="The user to warn",
        reason="The warning reason"
    )
    @has_permissions(moderate_members=True)
    async def wadd(self, ctx: Context, member: discord.Member, reason: str):
        if member == ctx.author:
            await ctx.send("<:disapprove:1517452151012589662> You cannot warn yourself.", ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(ctx) and member.top_role >= ctx.author.top_role:
            await ctx.send("<:disapprove:1517452151012589662> You cannot manage warnings for someone with an equal or higher role than yours.", ephemeral=True)
            return

        user_warnings, data = get_guild_warnings(str(ctx.guild.id), member.id)

        warnings, data = await add_guild_warning(
            str(ctx.guild.id),
            member.id,
            reason,
            moderator_id=ctx.author.id,
            moderator_name=str(ctx.author),
        )

        if not member.bot:
            await send_warning_dm(member, ctx.guild, reason, total_warnings=len(warnings))

        total = len(warnings)
        await apply_warning_sanctions(member, ctx.guild, total)
        confirm_embed = discord.Embed(
            title="<:warning:1517452174991556758> Warning added",
            description=f"**{format_user_reference(member)}** has been warned.",
            color=discord.Color.orange()
        )
        confirm_embed.add_field(name="Reason", value=reason, inline=False)
        confirm_embed.add_field(name="Total warnings", value=str(total), inline=True)
        await ctx.send(embed=confirm_embed)
        return

    @w.command(name="remove", description="Add a warning to a user")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(
        member="The user to remove the warning from",
        reason="The removal note"
    )
    @has_permissions(moderate_members=True)
    async def wrem(self, ctx: Context, member: discord.Member, reason: str):
        if member == ctx.author:
            await ctx.send("<:disapprove:1517452151012589662> You cannot warn yourself.",
                                                    ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(ctx) and member.top_role >= ctx.author.top_role:
            await ctx.send(
                "<:disapprove:1517452151012589662> You cannot manage warnings for someone with an equal or higher role than yours.",
                ephemeral=True)
            return

        user_warnings, data = get_guild_warnings(str(ctx.guild.id), member.id)

        if not user_warnings:
            await ctx.send(f"<:disapprove:1517452151012589662> **{format_user_reference(member)}** has no warnings to remove.", ephemeral=True)
            return

        removed = user_warnings.pop()
        save_guild_data(data)

        automod, automod_data = get_guild_automod_config(str(ctx.guild.id))
        sanction_state = automod.setdefault("warning_sanction_state", {})
        sanction_state[str(member.id)] = {"last_applied_warns": len(user_warnings)}
        save_guild_data(automod_data)

        if not member.bot:
            try:
                dm_embed = discord.Embed(
                    title="<:warning:1517452174991556758> A warning has been removed",
                    description=f"**Server:** {ctx.guild.name}\n**Note:** {reason}",
                    color=discord.Color.green()
                )
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        total = len(user_warnings)
        confirm_embed = discord.Embed(
            title="<:warning:1517452174991556758> Warning removed",
            description=f"A warning has been removed from **{format_user_reference(member)}**.",
            color=discord.Color.green()
        )
        confirm_embed.add_field(name="Removed warning reason", value=removed.get("reason", "No reason provided"), inline=False)
        confirm_embed.add_field(name="Note", value=reason, inline=False)
        confirm_embed.add_field(name="Remaining warnings", value=str(total), inline=True)
        await ctx.send(embed=confirm_embed)
        return

    @w.command(name="clear", description="Add a warning to a user")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(
        member="The user to remove the warning from",
        reason="The removal note"
    )
    @has_permissions(moderate_members=True)
    async def wclr(self, ctx: Context, member: discord.Member, reason: str):
        if member == ctx.author:
            await ctx.send("<:disapprove:1517452151012589662> You cannot warn yourself.",
                                                    ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(ctx) and member.top_role >= ctx.author.top_role:
            await ctx.send(
                "<:disapprove:1517452151012589662> You cannot manage warnings for someone with an equal or higher role than yours.",
                ephemeral=True)
            return

        user_warnings, data = get_guild_warnings(str(ctx.guild.id), member.id)

        if not user_warnings:
            await ctx.send(
                f"<:disapprove:1517452151012589662> **{format_user_reference(member)}** has no warnings to clear.",
                ephemeral=True)
            return

        count = len(user_warnings)
        user_warnings.clear()
        save_guild_data(data)

        automod, automod_data = get_guild_automod_config(str(ctx.guild.id))
        sanction_state = automod.setdefault("warning_sanction_state", {})
        sanction_state.pop(str(member.id), None)
        save_guild_data(automod_data)

        if not member.bot:
            try:
                dm_embed = discord.Embed(
                    title="<:warning:1517452174991556758> All warnings cleared",
                    description=f"**Server:** {ctx.guild.name}\n**Note:** {reason}",
                    color=discord.Color.green()
                )
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        confirm_embed = discord.Embed(
            title="<:warning:1517452174991556758> Warnings cleared",
            description=f"All warnings have been cleared from **{format_user_reference(member)}**.",
            color=discord.Color.green()
        )
        confirm_embed.add_field(name="Cleared warnings", value=str(count), inline=True)
        confirm_embed.add_field(name="Note", value=reason, inline=False)
        await ctx.send(embed=confirm_embed)
        return

    @a.command()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(
        member="The user whose warnings you want to view"
    )
    @has_permissions(moderate_members=True)
    async def warns_adm(
            self,
            ctx: Context,
            member: discord.Member
    ):
        """Shows warning for an user"""
        if member == ctx.author:
            await ctx.send(
                "<:disapprove:1517452151012589662> You cannot view warnings for yourself with this command.",
                ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(ctx) and member.top_role >= ctx.author.top_role:
            await ctx.send(
                "<:disapprove:1517452151012589662> You cannot view warnings for someone with an equal or higher role than yours.",
                ephemeral=True)
            return

        user_warnings, _ = get_guild_warnings(str(ctx.guild.id), member.id)
        if not user_warnings:
            await ctx.send(
                f"<:approve:1517452125687513158> **{format_user_reference(member)}** has no warnings.", ephemeral=False)
            return

        embed = discord.Embed(
            title=f"Warnings for {member.display_name}",
            description=f"Total warnings: **{len(user_warnings)}**",
            color=discord.Color.orange()
        )

        for index, warn_entry in enumerate(user_warnings[-10:], start=max(1, len(user_warnings) - 9)):
            raw_timestamp = warn_entry.get("timestamp")
            timestamp = "Unknown time"
            if raw_timestamp:
                try:
                    dt = datetime.fromisoformat(raw_timestamp)
                    timestamp = discord.utils.format_dt(dt, style="f")
                except Exception:
                    timestamp = raw_timestamp
            reason = warn_entry.get("reason", "No reason provided")
            moderator = warn_entry.get("moderator_name", "Unknown moderator")
            embed.add_field(
                name=f"Warn {index}",
                value=f"**Reason:** {reason}\n**Moderator:** {moderator}\n**Time:** {timestamp}",
                inline=False
            )

        if len(user_warnings) > 10:
            embed.set_footer(text=f"Showing the last 10 of {len(user_warnings)} warnings")

        await ctx.send(embed=embed, ephemeral=False)

    @a.group(name="role", description="Give or remove a role from members")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_roles=True)
    @has_permissions(manage_roles=True)
    async def r(self, ctx): pass

    @r.command(name="add", description="Give a role to members")
    async def radd(
        self,
        ctx: Context,

        member: discord.Member,
        role: discord.Role,
        reason: str
    ):
        role_error = validate_role_selection(ctx, role, "role")
        if role_error:
            await ctx.send(role_error, ephemeral=True)
            return

        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send(
                "<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(
                ctx) and ctx.author != member and member.top_role >= ctx.author.top_role:
            await ctx.send(
                "<:disapprove:1517452151012589662> You cannot modify the roles of someone with an equal or higher role than yours.",
                ephemeral=True)
            return

        try:
            if role in member.roles:
                await ctx.send(
                    f"<:warning:1517452174991556758> **{format_user_reference(member)}** already has **{role.name}**.",
                    ephemeral=True)
                return
            await member.add_roles(role, reason=f"Role admin by {ctx.author} - {reason}")
            await ctx.send(
                f"<:approve:1517452125687513158> Added **{role.name}** to **{format_user_reference(member)}**.",
                ephemeral=False)
        except discord.Forbidden:
            await ctx.send(
                "<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).",
                ephemeral=True)
        except Exception as e:
            await ctx.send(f"<:disapprove:1517452151012589662> An error occurred: {e}",
                                                    ephemeral=True)

    @r.command(name="remove", description="Give a role to members")
    async def rrem(
        self,
        ctx: Context,

        member: discord.Member,
        role: discord.Role,
        reason: str
    ):
        role_error = validate_role_selection(ctx, role, "role")
        if role_error:
            await ctx.send(role_error, ephemeral=True)
            return

        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send(
                "<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(
                ctx) and ctx.author != member and member.top_role >= ctx.author.top_role:
            await ctx.send(
                "<:disapprove:1517452151012589662> You cannot modify the roles of someone with an equal or higher role than yours.",
                ephemeral=True)
            return

        try:
            if role not in member.roles:
                await ctx.send(
                    f"<:warning:1517452174991556758> **{format_user_reference(member)}** does not have **{role.name}**.",
                    ephemeral=True)
                return
            await member.remove_roles(role, reason=f"Role admin by {ctx.author} - {reason}")
            await ctx.send(
                f"<:approve:1517452125687513158> Removed **{role.name}** from **{format_user_reference(member)}**.",
                ephemeral=False)

        except discord.Forbidden:
            await ctx.send(
                "<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).",
                ephemeral=True)
        except Exception as e:
            await ctx.send(f"<:disapprove:1517452151012589662> An error occurred: {e}",
                                                    ephemeral=True)

    @r.command(name="temp", description="Grant or remove a temporary role from a user")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.describe(
        action="Whether to grant or remove the temporary role",
        member="The user to update",
        role="The temporary role to grant or remove",
        duration="How long the temporary role should last (for example 30m, 2h, 1d)",
        reason="Why this temporary role change is being made"
    )
    @app_commands.choices(
        action=[app_commands.Choice(name="Grant", value="grant"), app_commands.Choice(name="Remove", value="remove")])
    @has_permissions(manage_roles=True)
    async def temp_role_adm(
            self,
            ctx: Context,
            action: str,
            member: discord.Member,
            role: discord.Role,
            duration: str = None,
            reason: str = "No reason provided",
    ):
        role_error = validate_role_selection(ctx, role, "temporary role")
        if role_error:
            await ctx.send(role_error, ephemeral=True)
            return

        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send(
                "<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
            return

        if not guild_owner_bypasses_role_checks(
                ctx) and ctx.send != member and member.top_role >= ctx.author.top_role:
            await ctx.send(
                "<:disapprove:1517452151012589662> You cannot modify the roles of someone with an equal or higher role than yours.",
                ephemeral=True)
            return

        if action == "grant":
            if not duration:
                await ctx.send(
                    "<:disapprove:1517452151012589662> Please provide a duration like 30m, 2h, or 1d.", ephemeral=True)
                return

            duration_seconds = parse_duration_to_seconds(duration)
            if duration_seconds is None or duration_seconds <= 0:
                await ctx.send(
                    "<:disapprove:1517452151012589662> Please provide a valid duration like 30m, 2h, or 1d.",
                    ephemeral=True)
                return

            try:
                if role in member.roles:
                    await ctx.send(
                        f"<:warning:1517452174991556758> **{format_user_reference(member)}** already has **{role.name}**.",
                        ephemeral=True)
                    return
                await member.add_roles(role, reason=f"Temporary role admin by {ctx.author} - {reason}")

                async def remove_temp_role():
                    await asyncio.sleep(duration_seconds)
                    try:
                        await member.remove_roles(role,
                                                  reason=f"Temporary role expired after {duration} (admin command)")
                    except (discord.Forbidden, discord.HTTPException):
                        pass

                asyncio.create_task(remove_temp_role())
                await ctx.send(
                    f"<:approve:1517452125687513158> Granted **{role.name}** to **{format_user_reference(member)}** for {duration}.",
                    ephemeral=False)
            except discord.Forbidden:
                await ctx.send(
                    "<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).",
                    ephemeral=True)
            except Exception as e:
                await ctx.send(f"<:disapprove:1517452151012589662> An error occurred: {e}",
                                                        ephemeral=True)
            return

        try:
            if role not in member.roles:
                await ctx.send(
                    f"<:warning:1517452174991556758> **{format_user_reference(member)}** does not have **{role.name}**.",
                    ephemeral=True)
                return
            await member.remove_roles(role, reason=f"Temporary role admin removal by {ctx.author} - {reason}")
            await ctx.send(
                f"<:approve:1517452125687513158> Removed **{role.name}** from **{format_user_reference(member)}**.",
                ephemeral=False)
        except discord.Forbidden:
            await ctx.send(
                "<:disapprove:1517452151012589662> I don't have permission to manage that role (Hierarchy issue).",
                ephemeral=True)
        except Exception as e:
            await ctx.send(f"<:disapprove:1517452151012589662> An error occurred: {e}",
                                                    ephemeral=True)

    @r.command(name="for", description="Add or remove a role from all members who have a target role")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.describe(
        action="Whether to add or remove the role",
        role="The role to add or remove",
        target_role="The role filter; members with this role will be affected (use @everyone for everyone)"
    )
    @app_commands.choices(
        action=[app_commands.Choice(name="Add", value="add"), app_commands.Choice(name="Remove", value="remove")])
    async def adm_role_for(
            self,
            ctx: Context,
            action: str,
            role: discord.Role,
            target_role: discord.Role,
    ):
        role_error = validate_role_selection(ctx, role, "role")
        if role_error:
            await ctx.send(role_error, ephemeral=True)
            return

        if role is None or target_role is None:
            await ctx.send("<:disapprove:1517452151012589662> Both role options are required.",
                                                    ephemeral=True)
            return

        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send(
                "<:disapprove:1517452151012589662> I don't have permission to manage roles.", ephemeral=True)
            return

        await ctx.defer(ephemeral=False)

        try:
            await ctx.guild.chunk(cache=True)
        except Exception:
            pass

        affected_members = [member for member in ctx.guild.members if target_role in member.roles]
        if not affected_members:
            await ctx.send(
                f"<:warning:1517452174991556758> No members with the role **{target_role.name}** were found.",
                ephemeral=False)
            return

        updated = 0
        skipped = 0
        failed = 0
        processed = 0
        stop_progress_updates = asyncio.Event()

        def build_progress_embed() -> discord.Embed:
            progress_percent = (processed / len(affected_members) * 100) if affected_members else 100.0
            action_text = "adding" if action == "add" else "removing"
            embed = discord.Embed(
                title="<:gear:1517576939097952496> Role Update In Progress",
                description=f"{action_text.capitalize()} role **{role.name}** from members with **{target_role.name}**...",
                color=discord.Color.blurple()
            )
            embed.add_field(name="<:list:1517497572770451567> Processed",
                            value=f"{processed}/{len(affected_members)} ({progress_percent:.1f}%)", inline=True)
            embed.add_field(name="<:approuve:1517452125687513158> Updated", value=str(updated), inline=True)
            embed.add_field(name="<:warning:1517452174991556758> Skipped", value=str(skipped), inline=True)
            embed.add_field(name="<:dissaprouve:1517452151012589662> Failed", value=str(failed), inline=True)
            return embed

        async def update_progress_message(message: discord.Message):
            while not stop_progress_updates.is_set():
                await asyncio.sleep(10)
                if stop_progress_updates.is_set():
                    break
                try:
                    await message.edit(embed=build_progress_embed())
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    break

        progress_message = await ctx.send(embed=build_progress_embed(), ephemeral=False)
        progress_task = asyncio.create_task(update_progress_message(progress_message))

        try:
            for member in affected_members:
                try:
                    if action == "add":
                        if role not in member.roles:
                            await member.add_roles(role, reason=f"Role mass update by {ctx.author}")
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        if role in member.roles:
                            await member.remove_roles(role, reason=f"Role mass update by {ctx.author}")
                            updated += 1
                        else:
                            skipped += 1
                except discord.Forbidden:
                    failed += 1
                except Exception:
                    failed += 1
                finally:
                    processed += 1
        finally:
            stop_progress_updates.set()
            if progress_task:
                try:
                    await progress_task
                except Exception:
                    pass

        action_text = "added to" if action == "add" else "removed from"
        embed = discord.Embed(
            title="<:gear:1517576939097952496> Role Update Complete",
            description=f"The role **{role.name}** was {action_text} **{target_role.name}** members.",
            color=discord.Color.green() if action == "add" else discord.Color.orange()
        )
        embed.add_field(name="<:graph:1517584522877866065> Affected Members", value=str(len(affected_members)),
                        inline=True)
        embed.add_field(name="<:approuve:1517452125687513158> Updated", value=str(updated), inline=True)
        embed.add_field(name="<:warning:1517452174991556758> Skipped", value=str(skipped), inline=True)
        if failed:
            embed.add_field(name="<:dissaprouve:1517452151012589662> Failed", value=str(failed), inline=True)

        try:
            await progress_message.edit(content=f"<:approve:1517452125687513158> Finished updating roles.", embed=embed)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            await ctx.send(embed=embed, ephemeral=False)
