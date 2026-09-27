"""Message history, audit log events, and the bot error log."""

import traceback
from collections import OrderedDict
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Container, MediaGallery, Separator, TextDisplay

import save
from utils import audit
from utils.automod import is_honeypot_channel
from utils.formatting import discord_timestamp, format_user_reference
from utils.views import TimeoutDisabledLayoutView, V2InfoContainerView

MESSAGE_CACHE_LIMIT = 20000


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 3] + "..."


class DeletedMessagesView(TimeoutDisabledLayoutView):
    def __init__(self, full_description: str, media_messages: list, requester):
        super().__init__(timeout=600)
        self.full_description = full_description
        self.messages = media_messages
        self.requester = requester
        self.index = 0
        self.mode = "messages"
        self.build_components()

    def build_components(self):
        self.clear_items()

        if self.mode == "messages":
            container_items = [
                TextDisplay("<:trash:1517497581058527404> Recent deleted messages"),
                Separator(),
                TextDisplay(self.full_description),
            ]
            if self.messages:
                container_items.append(Separator())
                container_items.append(TextDisplay(f"<:image:1517497571470348539> {len(self.messages)} attachment(s) available. Press Media to browse them."))

            container = Container(*container_items, accent_color=discord.Color.red())
            self.add_item(container)

            if self.messages:
                self.media_button = Button(label="Media", style=discord.ButtonStyle.primary, custom_id="deleted_media_switch")

                async def media_callback(interaction: discord.Interaction):
                    if interaction.user != self.requester:
                        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Only the person who ran the command can switch views!", ephemeral=True)
                        return
                    self.mode = "media"
                    self.build_components()
                    await interaction.response.edit_message(view=self)

                self.media_button.callback = media_callback
                self.add_item(discord.ui.ActionRow(self.media_button))

        else:
            current_msg = self.messages[self.index]
            content_text = current_msg.get('content') or "*[Attachment only]*"
            attachment_url = current_msg.get('attachment_url')
            attachment_name = current_msg.get('attachment_name') or "attachment"
            is_image = bool(current_msg.get('is_image'))

            container_items = [
                TextDisplay("<:image:1517497571470348539> Deleted media viewer"),
                Separator(),
                TextDisplay(f"**{current_msg['author'].display_name}** - deleted at {discord_timestamp(current_msg['created_at'])}"),
                TextDisplay(f"{content_text}"),
            ]

            if attachment_url:
                if is_image:
                    gallery = MediaGallery()
                    gallery.add_item(media=attachment_url, description=f"{current_msg['author'].display_name} - deleted at {discord_timestamp(current_msg['created_at'])}")
                    container_items.extend([Separator(), gallery])
                else:
                    container_items.extend([Separator(), TextDisplay(f"Attachment: [{attachment_name}]({attachment_url})")])
            else:
                container_items.extend([Separator(), TextDisplay("No attachment available for this message.")])

            container_items.append(Separator())
            container_items.append(TextDisplay(f"Attachment {self.index + 1}/{len(self.messages)}"))

            container = Container(*container_items, accent_color=discord.Color.red())
            self.add_item(container)

            self.prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="deleted_media_prev")
            self.messages_button = Button(label="Messages", style=discord.ButtonStyle.primary, custom_id="deleted_messages_switch")
            self.next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="deleted_media_next")

            async def prev_callback(interaction: discord.Interaction):
                if interaction.user != self.requester:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Only the person who ran the command can change media pages!", ephemeral=True)
                    return
                if self.index > 0:
                    self.index -= 1
                    self.build_components()
                    await interaction.response.edit_message(view=self)

            async def messages_callback(interaction: discord.Interaction):
                if interaction.user != self.requester:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Only the person who ran the command can switch views!", ephemeral=True)
                    return
                self.mode = "messages"
                self.build_components()
                await interaction.response.edit_message(view=self)

            async def next_callback(interaction: discord.Interaction):
                if interaction.user != self.requester:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Only the person who ran the command can change media pages!", ephemeral=True)
                    return
                if self.index < len(self.messages) - 1:
                    self.index += 1
                    self.build_components()
                    await interaction.response.edit_message(view=self)

            self.prev_button.callback = prev_callback
            self.messages_button.callback = messages_callback
            self.next_button.callback = next_callback
            self.update_button_states()
            self.add_item(discord.ui.ActionRow(self.prev_button, self.messages_button, self.next_button))

    def update_button_states(self):
        self.prev_button.disabled = (self.index == 0)
        self.next_button.disabled = (self.index == len(self.messages) - 1)


class WherePingView(TimeoutDisabledLayoutView):
    def __init__(self, entries: list[dict], target_user: discord.User | discord.Member):
        super().__init__(timeout=600)
        self.entries = list(entries)
        self.target_user = target_user
        self.build_components()

    def build_components(self):
        self.clear_items()

        lines = []
        for index, entry in enumerate(self.entries[:7], start=1):
            author_name = getattr(entry['author'], 'display_name', getattr(entry['author'], 'name', 'Unknown'))
            channel_text = f"<#{entry['channel_id']}>"
            content_text = entry.get('content') or "*[No text content]*"
            if len(content_text) > 220:
                content_text = content_text[:217] + "..."
            mention_name = entry.get('mention_name') or getattr(entry['mention'], 'display_name', getattr(entry['mention'], 'name', 'Unknown'))
            if entry.get('mention_type') == 'role':
                mention_text = f"@{mention_name}"
            else:
                mention_text = f"**{mention_name}**"
            lines.append(
                f"{index}. **{author_name}** pinged {mention_text} in {channel_text}\n"
                f"-# {content_text}\n"
                f"-# At {discord_timestamp(entry['created_at'])} | [Jump to Message]({entry['jump_url']})"
            )

        body = "\n\n".join(lines) if lines else "No recent ping entries found for this user."
        container = Container(
            TextDisplay(f"<:bell:1517497562184024275> Where {self.target_user.display_name} was pinged"),
            Separator(),
            TextDisplay(body),
            accent_color=discord.Color.gold(),
        )
        self.add_item(container)


class LogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_cache: OrderedDict[int, dict] = OrderedDict()
        self.deleted_cache: list[dict] = []
        self.edited_cache: list[dict] = []
        self.where_ping_cache: list[dict] = []
        self._previous_tree_error = None

    async def cog_load(self):
        self._previous_tree_error = self.bot.tree.on_error
        self.bot.tree.on_error = self.on_app_command_error

    async def cog_unload(self):
        if self._previous_tree_error is not None:
            self.bot.tree.on_error = self._previous_tree_error

    # ---------------------------------------------------------------- cache helpers

    def clean_cache(self):
        self.deleted_cache = audit.prune_history_entries(self.deleted_cache, key=lambda entry: entry.get("channel"), max_items=10)
        self.edited_cache = audit.prune_history_entries(self.edited_cache, key=lambda entry: entry.get("channel"), max_items=10)
        self.where_ping_cache = audit.prune_history_entries(self.where_ping_cache, key=lambda entry: (entry.get("guild_id"), entry.get("mention_id")), max_items=10)

    def forget_user(self, user_id: int) -> None:
        self.clean_cache()
        self.message_cache = OrderedDict((mid, m) for mid, m in self.message_cache.items() if m['author'].id != user_id)
        self.deleted_cache = [m for m in self.deleted_cache if m['author'].id != user_id]
        self.edited_cache = [m for m in self.edited_cache if m['author'].id != user_id]
        self.where_ping_cache = [entry for entry in self.where_ping_cache if entry.get('mention', None) and entry['mention'].id != user_id]

    def _add_where_ping(self, message: discord.Message, mention, mention_type: str, mention_name: str, now: datetime) -> None:
        self.where_ping_cache.append({
            'id': message.id,
            'guild_id': message.guild.id,
            'channel_id': message.channel.id,
            'channel': message.channel.id,
            'author': message.author,
            'mention': mention,
            'mention_id': mention.id,
            'mention_type': mention_type,
            'mention_name': mention_name,
            'content': message.content,
            'jump_url': message.jump_url,
            'time': now,
            'created_at': now,
        })

    # ---------------------------------------------------------------- listeners

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild and is_honeypot_channel(message.guild, message.channel):
            return

        self.clean_cache()

        attachment_url = None
        attachment_name = None
        is_image = False
        if message.attachments:
            attachment = message.attachments[0]
            attachment_url = attachment.url
            attachment_name = attachment.filename or "attachment"
            is_image = bool(attachment.content_type and attachment.content_type.startswith("image/"))
        now = datetime.now(timezone.utc)
        self.message_cache[message.id] = {
            'id': message.id,
            'channel': message.channel.id,
            'author': message.author,
            'content': message.content or "",
            'media': attachment_url,
            'attachment_url': attachment_url,
            'attachment_name': attachment_name,
            'is_image': is_image,
            'mentions': message.mentions,
            'time': now,
            'created_at': now
        }
        while len(self.message_cache) > MESSAGE_CACHE_LIMIT:
            self.message_cache.popitem(last=False)

        if message.guild:
            for mention in message.mentions:
                if mention.id == message.author.id or getattr(mention, "bot", False):
                    continue
                self._add_where_ping(message, mention, 'user', getattr(mention, 'display_name', getattr(mention, 'name', 'Unknown')), now)
            for role in message.role_mentions:
                self._add_where_ping(message, role, 'role', getattr(role, 'name', 'Unknown role'), now)
            self.where_ping_cache = audit.prune_history_entries(self.where_ping_cache, key=lambda entry: (entry.get("guild_id"), entry.get("mention_id")), max_items=10)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        self.clean_cache()

        msg = self.message_cache.get(message.id)
        if msg is None:
            return

        deleted_msg = msg.copy()
        deleted_msg['deleted_at'] = datetime.now(timezone.utc)

        history_enabled = True
        ghost_enabled = False
        if message.guild:
            guild_config, _ = save.get_guild_config(str(message.guild.id))
            history_enabled = guild_config.get("edit_delete_history_enabled", True)
            ghost_enabled = guild_config.get("ghost_ping_enabled", False)

        if history_enabled:
            self.deleted_cache.append(deleted_msg)
            self.deleted_cache = audit.prune_history_entries(self.deleted_cache, key=lambda entry: entry.get("channel"), max_items=10)

        if message.guild and not message.author.bot:
            content_preview = (message.content or "")[:1024]
            embed = discord.Embed(
                title="<:trash:1517497581058527404> Message Deleted",
                color=discord.Color.red()
            )
            embed.add_field(name="User", value=format_user_reference(message.author), inline=True)
            embed.add_field(name="Channel", value=message.channel.mention if hasattr(message.channel, 'mention') else str(message.channel), inline=True)
            embed.add_field(name="Content", value=content_preview or "*[Empty or Media]*", inline=False)

            if message.attachments:
                attachment_links = []
                for attachment in message.attachments[:5]:
                    name = attachment.filename or "attachment"
                    attachment_links.append(f"[{name}]({attachment.url})")
                if attachment_links:
                    embed.add_field(name="Attachment(s)", value="\n".join(attachment_links)[:1024], inline=False)
                    first_attachment = message.attachments[0]
                    if first_attachment.content_type and first_attachment.content_type.startswith("image/"):
                        embed.set_image(url=first_attachment.url)

            embed.add_field(name="Message ID", value=message.id, inline=True)
            embed.timestamp = datetime.now(timezone.utc)
            await audit.send_audit_log(message.guild, "message_delete", embed=embed)

        if message.guild and not ghost_enabled:
            return

        if msg['mentions'] and not msg['author'].bot:
            pinged_users = [
                user for user in msg['mentions']
                if user.id != msg['author'].id and not getattr(user, "bot", False)
            ]

            if pinged_users:
                settings = save.load_user_settings()
                mentions_str = " ".join([format_user_reference(user, settings) for user in pinged_users])
                author_str = format_user_reference(msg['author'], settings)

                embed = discord.Embed(
                    title="<:ghost:1517497569939558470> Ghost Ping Detected!",
                    description=f"{mentions_str}, you were pinged by {author_str} but the message was deleted.",
                    color=discord.Color.red()
                )
                if msg['content']:
                    embed.add_field(name="<:list:1517497572770451567> Deleted Content:", value=_shorten(msg['content'], 1024), inline=False)

                embed.timestamp = msg['created_at']

                channel = self.bot.get_channel(msg['channel'])
                if channel:
                    try:
                        await channel.send(embed=embed)
                    except (discord.Forbidden, discord.HTTPException) as error:
                        audit.add_bot_error_entry(message.guild.id if message.guild else None, msg['channel'], msg['author'], "ghost ping notification", error)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot:
            return

        if before.content == after.content:
            return

        self.clean_cache()

        msg = self.message_cache.get(before.id)
        if msg is None:
            return

        history_enabled = True
        if before.guild:
            guild_config, _ = save.get_guild_config(str(before.guild.id))
            history_enabled = guild_config.get("edit_delete_history_enabled", True)

        if history_enabled:
            edited_msg = msg.copy()

            edited_msg['author_id'] = before.author.id
            edited_msg['old_content'] = before.content if before.content else "*(Empty original content)*"
            edited_msg['new_content'] = after.content if after.content else "*(Empty edited content)*"
            edited_msg['jump_url'] = after.jump_url
            edited_msg['edited_at'] = datetime.now(timezone.utc)

            self.edited_cache.append(edited_msg)
            self.edited_cache = audit.prune_history_entries(self.edited_cache, key=lambda entry: entry.get("channel"), max_items=10)

        if before.guild and not before.author.bot:
            old_preview = (before.content or "")[:750]
            new_preview = (after.content or "")[:750]
            embed = discord.Embed(
                title="<:edit:1517497568421085256> Message Edited",
                color=discord.Color.orange()
            )
            embed.add_field(name="User", value=format_user_reference(before.author), inline=True)
            embed.add_field(name="Channel", value=before.channel.mention if hasattr(before.channel, 'mention') else str(before.channel), inline=True)
            embed.add_field(name="Before", value=old_preview or "*[Empty]*", inline=False)
            embed.add_field(name="After", value=new_preview or "*[Empty]*", inline=False)
            embed.add_field(name="Message ID", value=before.id, inline=True)
            embed.timestamp = datetime.now(timezone.utc)
            await audit.send_audit_log(before.guild, "message_edit", embed=embed)

        msg['content'] = after.content

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or not member.guild or before.channel == after.channel:
            return

        embed = discord.Embed(
            title="<:play:1517497576855965716> Voice Channel Update",
            color=discord.Color.blue()
        )
        embed.add_field(name="User", value=format_user_reference(member), inline=True)

        if before.channel and after.channel:
            embed.add_field(name="From", value=before.channel.mention, inline=True)
            embed.add_field(name="To", value=after.channel.mention, inline=True)
            embed.description = "Member moved voice channels"
        elif before.channel:
            embed.add_field(name="Left", value=before.channel.mention, inline=True)
            embed.description = "Member left voice channel"
        elif after.channel:
            embed.add_field(name="Joined", value=after.channel.mention, inline=True)
            embed.description = "Member joined voice channel"

        embed.timestamp = datetime.now(timezone.utc)
        await audit.send_audit_log(member.guild, "voice_update", embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        audit.remove_admin_log_channel(channel.guild, channel.id)

    # ---------------------------------------------------------------- error handler

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        original_error = getattr(error, "original", error)

        async def reply(text: str):
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(text, ephemeral=True)

        try:
            if isinstance(error, app_commands.CommandOnCooldown):
                retry_after = error.retry_after
                if retry_after >= 60:
                    minutes = int(retry_after // 60)
                    seconds = int(retry_after % 60)
                    if seconds > 0:
                        message_text = f"<:hourglass:1517574046252924938> This command is on cooldown. Please wait **{minutes}m {seconds}s** before trying again."
                    else:
                        message_text = f"<:hourglass:1517574046252924938> This command is on cooldown. Please wait **{minutes}m** before trying again."
                else:
                    retry_after = round(retry_after, 1)
                    message_text = f"<:hourglass:1517574046252924938> This command is on cooldown. Please wait **{retry_after}s** before trying again."
                await reply(message_text)
            elif isinstance(error, app_commands.MissingPermissions):
                perms = ", ".join(error.missing_permissions)
                await reply(f"<:disapprove:1517452151012589662> You lack the required permissions to run this: `{perms}`")
            elif isinstance(error, app_commands.BotMissingPermissions):
                perms = ", ".join(error.missing_permissions)
                await reply(f"<:disapprove:1517452151012589662> I am missing the required permissions to run this: `{perms}`")
            elif isinstance(original_error, discord.Forbidden):
                await reply("<:disapprove:1517452151012589662> I am missing the permissions required to complete that action.")
            else:
                command_name = getattr(getattr(interaction, "command", None), "qualified_name", None) or getattr(getattr(interaction, "command", None), "name", "unknown command")
                audit.add_bot_error(
                    getattr(interaction, "guild_id", None),
                    getattr(interaction, "channel_id", None),
                    getattr(interaction, "user", None),
                    command_name,
                    original_error,
                    interaction=interaction,
                )
                print(f"Ignored exception in command tree [{command_name}]: {type(original_error).__name__}: {original_error}")
                print("".join(traceback.format_exception(type(original_error), original_error, original_error.__traceback__)))
                await reply("<:disapprove:1517452151012589662> An unexpected error occurred while executing this command.")
        except (discord.NotFound, discord.HTTPException):
            # The interaction expired or the reply itself failed; nothing left to tell the user.
            pass

    # ---------------------------------------------------------------- commands

    @app_commands.command(name="deleted", description="View recently deleted messages and media")
    @app_commands.describe(user="Optional user filter")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def deleted(self, interaction: discord.Interaction, user: discord.Member = None):
        self.clean_cache()
        guild_config, _ = save.get_guild_config(str(interaction.guild.id))
        if not guild_config.get("edit_delete_history_enabled", True):
            await interaction.response.defer(); await interaction.followup.send("<:disapprove:1517452151012589662> Deleted message history is disabled for this server.")
            return
        channel_msgs = [m for m in self.deleted_cache if m['channel'] == interaction.channel_id]
        if user:
            channel_msgs = [m for m in channel_msgs if m['author'].id == user.id]
        channel_msgs = channel_msgs[-10:]
        if not channel_msgs:
            await interaction.response.defer(); await interaction.followup.send("No deleted messages found in this channel recently.")
            return

        description_lines = []
        attachment_messages = []

        for m in channel_msgs:
            has_attachment = bool(m.get('attachment_url'))
            attachment_indicator = "<:image:1517497571470348539> " if has_attachment else ""
            if has_attachment:
                attachment_messages.append(m)
            content_text = _shorten(m.get('content'), 300) if m.get('content') else "*[Attachment or Embed]*"
            description_lines.append(f"{attachment_indicator}**{m['author'].display_name}**: {content_text}\n-# Sent at {discord_timestamp(m['created_at'])}")

        full_description = "\n\n".join(description_lines)

        if attachment_messages:
            attachment_messages = attachment_messages[-3:]
            attachment_messages.sort(key=lambda x: x['time'], reverse=True)
            view = DeletedMessagesView(full_description, attachment_messages, interaction.user)
            await interaction.response.defer(); await interaction.followup.send(view=view)
            view.message = await interaction.original_response()
        else:
            view = V2InfoContainerView(
                "<:trash:1517497581058527404> Recent deleted messages:",
                full_description,
                discord.Color.red(),
            )
            await interaction.response.defer(); await interaction.followup.send(view=view)

    @app_commands.command(name="edited", description="Show recently edited messages in this channel")
    @app_commands.describe(user="Optional: Only show edited messages from a specific user")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def edited(self, interaction: discord.Interaction, user: discord.Member = None):
        self.clean_cache()
        guild_config, _ = save.get_guild_config(str(interaction.guild.id))
        if not guild_config.get("edit_delete_history_enabled", True):
            await interaction.response.defer(); await interaction.followup.send("<:disapprove:1517452151012589662> Edited message history is disabled for this server.")
            return

        channel_edited = [m for m in self.edited_cache if m['channel'] == interaction.channel_id]

        if user:
            channel_edited = [m for m in channel_edited if m['author_id'] == user.id]
        channel_edited = channel_edited[-10:]

        if not channel_edited:
            await interaction.response.defer(); await interaction.followup.send("No messages have been edited in this channel recently.")
            return

        text_layout = ""
        for msg in channel_edited[:10]:
            text_layout += f"**{msg['author'].display_name}**: ~~{_shorten(msg['old_content'], 150)}~~ ➔ {_shorten(msg['new_content'], 150)}\n-# Edited at {discord_timestamp(msg['edited_at'])} | [Jump to Message]({msg['jump_url']})\n\n"

        title_text = "<:edit:1517497568421085256> Recently Edited Messages"

        view = V2InfoContainerView(
            title_text,
            text_layout,
            discord.Color.orange(),
        )
        await interaction.response.defer(); await interaction.followup.send(view=view)

    @app_commands.command(name="where-ping", description="Show where a user has been pinged recently")
    @app_commands.describe(user="The user to look up")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def where_ping(self, interaction: discord.Interaction, user: discord.Member = None):
        self.clean_cache()
        target_user = user or interaction.user
        entries = []
        for entry in self.where_ping_cache:
            if entry.get('guild_id') != interaction.guild_id:
                continue
            if entry.get('mention_type') == 'user' and entry.get('mention_id') == target_user.id:
                entries.append(entry)
            elif entry.get('mention_type') == 'role' and isinstance(target_user, discord.Member):
                if target_user.get_role(entry.get('mention_id')) is not None:
                    entries.append(entry)
        entries.sort(key=lambda entry: entry['time'], reverse=True)
        entries = entries[:10]

        if not entries:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"No recent ping history was found for {target_user.display_name}.", ephemeral=True)
            return

        view = WherePingView(entries, target_user)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(view=view, ephemeral=True)

    @app_commands.command(name="errors", description="Show recent bot errors in this server")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def errors(self, interaction: discord.Interaction):
        guild_errors = [entry for entry in audit.bot_error_cache if entry.get("guild_id") == interaction.guild_id]
        if not guild_errors:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("No bot errors have been recorded for this server recently.", ephemeral=True)
            return

        recent_errors = list(reversed(guild_errors[-25:]))
        description_lines = []

        for entry in recent_errors:
            channel_id = entry.get("channel_id")
            if channel_id:
                channel_text = f"<#{channel_id}>"
            else:
                channel_text = "Unknown channel"

            user_obj = entry.get("user")
            user_text = getattr(user_obj, "display_name", getattr(user_obj, "name", "Unknown user"))
            error_message = entry.get("error_message", "No error message provided")
            if len(error_message) > 180:
                error_message = error_message[:177] + "..."

            description_lines.append(
                f"**{entry.get('command_name', 'unknown command')}** in {channel_text} by {user_text}\n"
                f"-# {entry.get('error_type', 'Error')}: {error_message}\n"
                f"-# At {discord_timestamp(entry['time'])}"
            )

        view = V2InfoContainerView(
            "<:warning:1517452174991556758> Recent Bot Errors",
            f"Showing latest {len(recent_errors)} of {len(guild_errors)} error(s).\n\n" + "\n\n".join(description_lines),
            discord.Color.red(),
        )
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(view=view, ephemeral=True)

    @app_commands.command(name="forget", description="Clear your messages from the bot's memory")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def forget(self, interaction: discord.Interaction):
        self.forget_user(interaction.user.id)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("I've wiped your messages, edits, media, and ping history from my memory!", ephemeral=True)

    @app_commands.command(name="forget_adm", description="Clear edited and deleted history of a chosen user")
    @app_commands.describe(user="User whose history should be cleared")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.default_permissions(manage_messages=True)
    async def forget_adm(self, interaction: discord.Interaction, user: discord.Member):
        self.forget_user(user.id)
        await interaction.response.defer(); await interaction.followup.send(
            f"Cleared deleted, edited, and ping history for {user.display_name}."
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(LogsCog(bot))
