from discord import app_commands
from discord.ext.commands import Cog, Context, hybrid_command

from LowerLeveled.timestamp import discord_timestamp
from Shared.Cache import *
from Shared.Guilds import *
from Shared.User import *
from Shared.Errors import *
from datetime import datetime, timezone

from Views.Deleted import DeletedMessagesView
from Views.v2 import V2InfoContainerView
from main import message_cache, deleted_cache, edited_cache
import discord

async def setup(bot):
    await bot.add_cog(Ghosts(bot))

class Ghosts(Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_message_delete(self, message):
        global message_cache, deleted_cache
        clean_cache()

        for msg in message_cache:
            if msg['id'] == message.id:
                deleted_msg = msg.copy()
                deleted_msg['deleted_at'] = datetime.now(timezone.utc)

                history_enabled = True
                ghost_enabled = False
                if message.guild:
                    guild_config, _ = get_guild_config(str(message.guild.id))
                    history_enabled = guild_config.get("edit_delete_history_enabled", True)
                    ghost_enabled = guild_config.get("ghost_ping_enabled", False)

                if history_enabled:
                    deleted_cache.append(deleted_msg)
                    deleted_cache = trim_cache(deleted_cache, max_len=10)
                if message.guild and not ghost_enabled:
                    break

                if msg['mentions'] and not msg['author'].bot:
                    pinged_users = [user for user in msg['mentions'] if user.id != msg['author'].id]
                    
                    if pinged_users:
                        settings = load_user_settings()
                        mentions_str = " ".join([format_user_reference(user, settings) for user in pinged_users])
                        author_str = format_user_reference(msg['author'], settings)
                        
                        embed = discord.Embed(
                            title="<:ghost:1517497569939558470> Ghost Ping Detected!",
                            description=f"{mentions_str}, you were pinged by {author_str} but the message was deleted.",
                            color=discord.Color.red()
                        )
                        if msg['content']:
                            embed.add_field(name="<:list:1517497572770451567> Deleted Content:", value=msg['content'], inline=False)
                        
                        embed.timestamp = msg['created_at']
                        
                        channel = self.bot.get_channel(msg['channel'])
                        if channel:
                            try:
                                await channel.send(embed=embed)
                            except discord.Forbidden as error:
                                add_bot_error_entry(message.guild.id if message.guild else None, msg['channel'], msg['author'], "ghost ping notification", error)
                break

    @Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot:
            return

        if before.content == after.content:
            return

        global message_cache, edited_cache
        clean_cache()

        history_enabled = True
        if before.guild:
            guild_config, _ = get_guild_config(str(before.guild.id))
            history_enabled = guild_config.get("edit_delete_history_enabled", True)

        for msg in message_cache:
            if msg['id'] == before.id:
                if history_enabled:
                    edited_msg = msg.copy()
                    
                    edited_msg['author_id'] = before.author.id
                    edited_msg['old_content'] = before.content if before.content else "*(Empty original content)*"
                    edited_msg['new_content'] = after.content if after.content else "*(Empty edited content)*"
                    edited_msg['jump_url'] = after.jump_url
                    edited_msg['edited_at'] = datetime.now(timezone.utc)
                    
                    edited_cache.append(edited_msg)
                    edited_cache = trim_cache(edited_cache, max_len=10)
                
                msg['content'] = after.content
                break

    @hybrid_command(name="deleted", description="View recently deleted messages and media")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def deleted(self, ctx: Context, user: discord.Member = None):
        clean_cache()
        guild_config, _ = get_guild_config(str(ctx.guild.id))
        if not guild_config.get("edit_delete_history_enabled", True):
            await ctx.send(
                "<:disapprove:1517452151012589662> Deleted message history is disabled for this server.")
            return
        channel_msgs = [m for m in deleted_cache if m['channel'] == ctx.channel.id]
        if user:
            channel_msgs = [m for m in channel_msgs if m['author'].id == user.id]
        if not channel_msgs:
            await ctx.send("No deleted messages found in this channel recently.")
            return

        description_lines = []
        media_only_messages = []

        for m in channel_msgs:
            media_indicator = "<:image:1517497571470348539> " if m['media'] else ""
            if m['media']:
                media_only_messages.append(m)
            content_text = m['content'] if m['content'] else "*[Media or Embed]*"
            description_lines.append(
                f"{media_indicator}**{m['author'].display_name}**: {content_text}\n-# Sent at {discord_timestamp(m['created_at'])}")

        full_description = "\n\n".join(description_lines)

        if media_only_messages:
            media_only_messages.sort(key=lambda x: x['time'], reverse=True)
            view = DeletedMessagesView(full_description, media_only_messages, ctx.author)
            message = await ctx.send(view=view)
            view.message = message
        else:
            view = V2InfoContainerView(
                "<:trash:1517497581058527404> Recent deleted messages:",
                full_description,
                discord.Color.red(),
            )
            await ctx.send(view=view)

    @hybrid_command(name="edited", description="Show recently edited messages in this channel")
    @app_commands.describe(user="Optional: Only show edited messages from a specific user")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def edited_command(self, ctx: Context, user: discord.Member = None):
        global edited_cache
        clean_cache()
        guild_config, _ = get_guild_config(str(ctx.guild.id))
        if not guild_config.get("edit_delete_history_enabled", True):
            await ctx.send(
                "<:disapprove:1517452151012589662> Edited message history is disabled for this server.")
            return

        channel_edited = [m for m in edited_cache if m['channel'] == ctx.channel.id]

        if user:
            channel_edited = [m for m in channel_edited if m['author_id'] == user.id]

        if not channel_edited:
            await ctx.send("No messages have been edited in this channel recently.")
            return

        text_layout = ""
        for msg in channel_edited[:7]:
            text_layout += f"**{msg['author'].display_name}**: ~~{msg['old_content']}~~ ➔ {msg['new_content']}\n-# Edited at {discord_timestamp(msg['edited_at'])} | [Jump to Message]({msg['jump_url']})\n\n"

        title_text = "<:edit:1517497568421085256> Recently Edited Messages"

        view = V2InfoContainerView(
            title_text,
            text_layout,
            discord.Color.orange(),
        )
        await ctx.send(view=view)

    @hybrid_command(name="forget", description="Clear your messages from the bot's memory")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def forget(self, ctx: Context):
        clean_cache()
        global message_cache, deleted_cache, edited_cache

        message_cache = [m for m in message_cache if m['author'].id != interaction.user.id]
        deleted_cache = [m for m in deleted_cache if m['author'].id != interaction.user.id]
        edited_cache = [m for m in edited_cache if m['author'].id != interaction.user.id]

        await ctx.send("I've wiped your messages, edits, and media from my memory!",
                                                ephemeral=True)
