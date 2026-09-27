"""Prefix commands: !say for server admins, and the owner-only maintenance commands (!help lists them)."""

import asyncio
import io
import json
import math
import os
import re
import sys
import time
from pathlib import Path

import discord
from discord.ext import commands
from discord.ui import Button, Container, LayoutView, Section, Separator, TextDisplay

import save
from utils import runtime
from utils.audit import add_bot_error_entry
from utils.automod import run_automod_check_for_content
from utils.banners import create_banner_preview, get_user_banner_style, normalize_banner_style
from utils.formatting import format_duration

try:
    import psutil
except ImportError:
    psutil = None

# Where !shutdown posts its notice when no channel is given.
SHUTDOWN_NOTICE_CHANNEL_ID = 1514173159052415026
BANNER_KINDS = {"welcome", "goodbye", "lvl", "level", "levelup"}


def update_env_setting(key: str, value: str) -> None:
    env_path = os.path.join(save.BASE_DIR, ".env")
    lines = []
    found = False

    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    lines.append(line)
                    continue
                if stripped.startswith(f"{key}="):
                    if any(ch.isspace() for ch in value) or any(ch in value for ch in "#=!"):
                        escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')
                        lines.append(f'{key}="{escaped_value}"\n')
                    else:
                        lines.append(f"{key}={value}\n")
                    found = True
                else:
                    lines.append(line)

    if not found:
        if any(ch.isspace() for ch in value) or any(ch in value for ch in "#=!"):
            escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}="{escaped_value}"\n')
        else:
            lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as handle:
        handle.write("".join(lines))

    os.environ[key] = value


class ServersListView(LayoutView):
    def __init__(self, user_id: int, guilds: list[discord.Guild], page: int = 1):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guilds = guilds
        self.page = page
        self.message: discord.Message | None = None
        self.guilds_per_page = 5
        self.build_components()

    def build_components(self):
        self.clear_items()
        total_servers = len(self.guilds)
        total_pages = max(1, math.ceil(total_servers / self.guilds_per_page))
        current_page = min(max(1, self.page), total_pages)
        start_index = (current_page - 1) * self.guilds_per_page
        page_guilds = self.guilds[start_index:start_index + self.guilds_per_page]

        container_items = [
            TextDisplay("💻 **Bot Servers**"),
            TextDisplay(f"Page {current_page}/{total_pages} · {total_servers} server(s) available."),
            Separator(),
        ]

        if not page_guilds:
            container_items.append(TextDisplay("No servers found."))
        else:
            for index, guild in enumerate(page_guilds, start=start_index + 1):
                row_text = f"{index}. **{guild.name}**\nMembers: {guild.member_count} · ID: `{guild.id}`"
                invite_button = Button(label="Invite", style=discord.ButtonStyle.primary, custom_id=f"server_invite_{guild.id}")

                async def invite_callback(interaction: discord.Interaction, guild_to_invite: discord.Guild = guild):
                    await self.generate_guild_invite(interaction, guild_to_invite)

                invite_button.callback = invite_callback
                container_items.append(Section(row_text, accessory=invite_button))

        self.add_item(Container(*container_items, accent_color=discord.Color.blurple()))

        prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="server_prev")
        next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="server_next")
        close_button = Button(label="Close", style=discord.ButtonStyle.danger, custom_id="server_close")
        prev_button.callback = self.open_previous_page
        next_button.callback = self.open_next_page
        close_button.callback = self.close_view
        prev_button.disabled = current_page <= 1
        next_button.disabled = current_page >= total_pages

        self.add_item(discord.ui.ActionRow(prev_button, next_button, close_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This server panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def open_previous_page(self, interaction: discord.Interaction):
        new_view = ServersListView(self.user_id, self.guilds, page=self.page - 1)
        new_view.message = interaction.message
        await interaction.response.edit_message(view=new_view)

    async def open_next_page(self, interaction: discord.Interaction):
        new_view = ServersListView(self.user_id, self.guilds, page=self.page + 1)
        new_view.message = interaction.message
        await interaction.response.edit_message(view=new_view)

    async def close_view(self, interaction: discord.Interaction):
        if interaction.message:
            await interaction.response.defer()
            await interaction.message.delete()
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Server list closed.", ephemeral=True)

    async def generate_guild_invite(self, interaction: discord.Interaction, guild: discord.Guild):
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This invite action is only for the original user.", ephemeral=True)
            return

        channel = guild.system_channel
        if channel is None:
            channel = next(
                (c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite),
                None,
            )
        if channel is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:disapprove:1517452151012589662> I could not find a valid invite channel in **{guild.name}**.",
                ephemeral=True,
            )
            return

        try:
            invite = await channel.create_invite(max_age=0, max_uses=0, unique=True)
        except Exception as exc:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:disapprove:1517452151012589662> Failed to create an invite for **{guild.name}**: {exc}",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"Invite for **{guild.name}**: {invite.url}", ephemeral=True)


class BackupListView(LayoutView):
    def __init__(self, user_id: int, page: int = 1):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.page = page
        self.message: discord.Message | None = None
        self.backup_files = save.get_backup_files()
        self.build_components()

    def build_components(self):
        self.clear_items()
        total_backups = len(self.backup_files)
        total_pages = max(1, math.ceil(total_backups / 5))
        current_page = min(max(1, self.page), total_pages)
        start_index = (current_page - 1) * 5
        page_backups = self.backup_files[start_index:start_index + 5]

        title = "Backup files"
        description = f"Page {current_page}/{total_pages} · {total_backups} backup(s) available."
        container_items = [
            TextDisplay(f"<:floppy_disk:1517577943290188033> **{title}**"),
            TextDisplay(description),
            Separator(),
        ]

        if not page_backups:
            container_items.append(TextDisplay("No backups found. Run a backup or wait for the scheduler to create one."))
        else:
            for index, backup_path in enumerate(page_backups, start=start_index + 1):
                file_label = f"{index}. {backup_path.name}"
                backup_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id=f"backup_edit_{current_page}_{index}")

                async def backup_callback(interaction: discord.Interaction, backup_file=backup_path):
                    await self.open_backup_actions(interaction, backup_file)

                backup_button.callback = backup_callback
                container_items.append(Section(f"{file_label}\n{save.format_backup_entry(backup_path)}", accessory=backup_button))

        self.add_item(Container(*container_items, accent_color=discord.Color.blurple()))

        prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="backup_prev")
        next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="backup_next")
        create_button = Button(label="Create Backup", style=discord.ButtonStyle.success, custom_id="backup_create")
        delete_all_button = Button(label="Delete All", style=discord.ButtonStyle.danger, custom_id="backup_delete_all")
        close_button = Button(label="Close", style=discord.ButtonStyle.danger, custom_id="backup_close")
        prev_button.callback = self.open_previous_page
        next_button.callback = self.open_next_page
        create_button.callback = self.create_backup
        delete_all_button.callback = self.delete_all_backups
        close_button.callback = self.close_view
        prev_button.disabled = current_page <= 1
        next_button.disabled = current_page >= total_pages

        self.add_item(discord.ui.ActionRow(prev_button, next_button, create_button, delete_all_button, close_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This backup panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def open_previous_page(self, interaction: discord.Interaction):
        new_view = BackupListView(self.user_id, page=self.page - 1)
        new_view.message = interaction.message
        await interaction.response.edit_message(view=new_view)

    async def open_next_page(self, interaction: discord.Interaction):
        new_view = BackupListView(self.user_id, page=self.page + 1)
        new_view.message = interaction.message
        await interaction.response.edit_message(view=new_view)

    async def create_backup(self, interaction: discord.Interaction):
        # Zipping can take a while: answer first and zip off the event loop.
        await interaction.response.defer(ephemeral=True)
        backup_path = await asyncio.to_thread(save.create_backup, save.BASE_DIR)
        await interaction.followup.send(f"<:approve:1517452125687513158> Created backup `{backup_path.name}`.", ephemeral=True)
        if self.message is None and interaction.message is not None:
            self.message = interaction.message
        await self.refresh()

    async def refresh(self) -> None:
        if self.message is None:
            return
        refreshed_view = BackupListView(self.user_id, page=self.page)
        refreshed_view.message = self.message
        try:
            await self.message.edit(view=refreshed_view)
        except (discord.NotFound, discord.HTTPException):
            pass

    async def close_view(self, interaction: discord.Interaction):
        if interaction.message:
            await interaction.response.defer()
            await interaction.message.delete()
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Backup list closed.", ephemeral=True)

    async def delete_all_backups(self, interaction: discord.Interaction):
        files = save.get_backup_files()
        if not files:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> There are no backups to delete.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        for backup_file in files:
            try:
                backup_file.unlink()
            except Exception:
                pass

        if self.message is None:
            self.message = interaction.message
        await self.refresh()
        await interaction.followup.send(f"<:trash:1517497581058527404> Deleted {len(files)} backup(s).", ephemeral=True)
        print(f"[backup] Deleted {len(files)} JSON backup(s)")

    async def open_backup_actions(self, interaction: discord.Interaction, backup_file: Path):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"What would you like to do with `{backup_file.name}`?",
            view=BackupActionView(self.user_id, backup_file, self),
            ephemeral=True,
        )


class BackupActionView(discord.ui.View):
    def __init__(self, user_id: int, backup_file: Path, list_view: BackupListView):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.backup_file = backup_file
        self.list_view = list_view
        self.load_button = Button(label="Load", style=discord.ButtonStyle.success, custom_id="backup_action_load")
        self.delete_button = Button(label="Delete", style=discord.ButtonStyle.danger, custom_id="backup_action_delete")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="backup_action_cancel")
        self.load_button.callback = self.load_callback
        self.delete_button.callback = self.delete_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.load_button)
        self.add_item(self.delete_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def load_callback(self, interaction: discord.Interaction):
        if not self.backup_file.exists():
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Backup file no longer exists.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            backup_before_restore = await asyncio.to_thread(save.restore_backup, self.backup_file, save.BASE_DIR)
        except Exception as e:
            await interaction.followup.send(f"<:disapprove:1517452151012589662> Failed to load backup: {e}", ephemeral=True)
            return
        await interaction.followup.send(
            f"<:approve:1517452125687513158> Loaded backup `{self.backup_file.name}` and created current backup `{backup_before_restore.name}`.",
            ephemeral=True,
        )
        await self.list_view.refresh()

    async def delete_callback(self, interaction: discord.Interaction):
        if not self.backup_file.exists():
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Backup file no longer exists.", ephemeral=True)
            return

        try:
            self.backup_file.unlink()
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                f"<:trash:1517497581058527404> Deleted backup `{self.backup_file.name}`.",
                ephemeral=True,
            )
            print(f"[backup] Deleted JSON backup: {self.backup_file.name}")
            await self.list_view.refresh()
        except Exception as e:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> Failed to delete backup: {e}", ephemeral=True)

    async def cancel_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Backup action cancelled.", view=None)


class LegacyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _is_owner(self, user: discord.User | None) -> bool:
        return await self.bot.is_owner(user)

    async def _owner_only(self, ctx: commands.Context) -> bool:
        """Tell non-owners the prefix is restricted. Returns True when the author is the owner."""
        if await self._is_owner(ctx.author):
            return True
        await ctx.send(f"<:disapprove:1517452151012589662> the {runtime.PREFIX} prefix is restricted to the bot owner only.")
        return False

    def _restart_presence(self) -> None:
        loop_cog = self.bot.get_cog('LoopCog')
        if loop_cog is not None and loop_cog.update_presence.is_running():
            loop_cog.update_presence.restart()

    async def _download_attachment_files(self, attachments):
        files = []
        for attachment in attachments:
            payload = await attachment.read()
            files.append(discord.File(io.BytesIO(payload), filename=attachment.filename, spoiler=attachment.is_spoiler()))
        return files

    async def _can_use_say(self, ctx: commands.Context) -> bool:
        if await self._is_owner(ctx.author):
            return True
        if ctx.guild is None:
            return False
        member = ctx.author
        if not isinstance(member, discord.Member):
            return False
        if member == ctx.guild.owner:
            return True
        return member.guild_permissions.administrator or member.guild_permissions.manage_guild

    @commands.command(name='say')
    async def say(self, ctx: commands.Context, *, message: str):
        if not await self._can_use_say(ctx):
            return await ctx.send(f"<:disapprove:1517452151012589662> the {runtime.PREFIX} prefix is restricted to the bot owner, server owner, or admins only.")

        raw = (message or '').strip()
        if not raw:
            return await ctx.send(
                'Usage:\n'
                '```\n'
                f'{runtime.PREFIX}say text\n'
                f'{runtime.PREFIX}say <#channel_id> text\n'
                f'{runtime.PREFIX}say X\n'
                f'{runtime.PREFIX}say X <#channel_id>\n'
                f'{runtime.PREFIX}say E text\n'
                f'{runtime.PREFIX}say E <#channel_id>\n'
                f'{runtime.PREFIX}say R\n'
                f'{runtime.PREFIX}say R <#channel_id>\n'
                f'{runtime.PREFIX}say H\n'
                '```'
            )

        parts = raw.split()
        action = 'S'
        if parts and parts[0].upper() in {'S', 'X', 'E', 'R', 'H'}:
            action = parts[0].upper()
            parts = parts[1:]

        if action == 'H':
            return await ctx.send(
                'Usage:\n'
                '```\n'
                f'{runtime.PREFIX}say text\n'
                f'{runtime.PREFIX}say <#channel_id> text\n'
                f'{runtime.PREFIX}say X\n'
                f'{runtime.PREFIX}say X <#channel_id>\n'
                f'{runtime.PREFIX}say E text\n'
                f'{runtime.PREFIX}say E <#channel_id>\n'
                f'{runtime.PREFIX}say R\n'
                f'{runtime.PREFIX}say R <#channel_id>\n'
                '```'
            )

        channel_id = None
        if parts and parts[0].startswith('<#') and parts[0].endswith('>'):
            channel_match = re.fullmatch(r'<#(\d+)>', parts[0])
            if channel_match:
                channel_id = channel_match.group(1)
                parts = parts[1:]
        elif parts and parts[0].isdigit() and len(parts[0]) >= 10:
            channel_id = parts[0]
            parts = parts[1:]

        payload = ' '.join(parts).strip()

        target_channel = ctx.channel
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None:
                return await ctx.send('Channel not found.')
            if ctx.guild is None or channel.guild != ctx.guild:
                return await ctx.send('<:disapprove:1517452151012589662> You cannot send to a channel from another server.')
            target_channel = channel

        reply_target = ctx.message.reference.resolved if ctx.message.reference else None
        if reply_target and target_channel.id != ctx.channel.id:
            reply_target = None

        if action == 'S' and not payload and not ctx.message.attachments:
            return await ctx.send('Please provide text to send.')

        if action == 'S':
            if ctx.guild and await run_automod_check_for_content(ctx.guild, ctx.author, target_channel, payload, source_label='/say'):
                return

            files = []
            if ctx.message.attachments:
                files = await self._download_attachment_files(ctx.message.attachments)

            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

            kwargs = {'files': files} if files else {}
            if reply_target is not None:
                kwargs['reference'] = reply_target
            await target_channel.send(payload, **kwargs)
            return

        if action == 'R':
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

            try:
                async for message in target_channel.history(limit=25):
                    if message.author.id == self.bot.user.id:
                        if not message.attachments:
                            return await ctx.send('No attachment found on the last bot message in that channel.')
                        await message.edit(attachments=[])
                        return
            except (discord.Forbidden, discord.HTTPException):
                return await ctx.send('Cannot update attachments in that channel.')

            return await ctx.send('No bot message found in that channel.')

        if action == 'X':
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

            try:
                async for message in target_channel.history(limit=25):
                    if message.author.id == self.bot.user.id:
                        await message.delete()
                        return
            except (discord.Forbidden, discord.HTTPException):
                return await ctx.send('Cannot delete messages in that channel.')

            return await ctx.send('No bot message found to delete in that channel.')

        if action == 'E':
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

            try:
                async for message in target_channel.history(limit=25):
                    if message.author.id == self.bot.user.id:
                        await message.edit(content=payload)
                        return
            except (discord.Forbidden, discord.HTTPException):
                return await ctx.send('Cannot edit messages in that channel.')

            return await ctx.send('No bot message found to edit in that channel.')

        return await ctx.send('Unknown action. Use S, X, E, or R.')

    @commands.command(name='json')
    async def json_cmd(self, ctx: commands.Context, file: str, target_id: str | None = None):
        if not await self._is_owner(ctx.author):
            return await ctx.send(f"<:disapprove:1517452151012589662> the {runtime.PREFIX} prefix is restricted to the bot owner only.")

        loaders = {
            'giveaway': save.load_giveaway_data,
            'giveaways': save.load_giveaway_data,
            'data': save.load_data,
            'economy': save.load_data,
            'level': save.load_levels,
            'levels': save.load_levels,
            'guild': save.load_guild_data,
            'guilds': save.load_guild_data,
            'settings': save.load_user_settings,
            'user': save.load_user_settings,
        }

        kind = (file or '').lower()
        loader = loaders.get(kind)
        if not loader:
            await ctx.send('Unknown file. Valid options: giveaway, data, level, guild, settings')
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
        prefix = (runtime.PREFIX or "!").strip() or "!"
        help_text = f"""
<:nUtils:1518376146008539146> List of owner commands (prefix `{prefix}`): ```text
{prefix}say - Make the bot say something in the current channel (server admins and owners can use this one)
{prefix}ping - Check the bot latency
{prefix}help - Shows this help menu
{prefix}ver - Shows or updates the bot version
{prefix}alt - Shows or updates the alternate version label
{prefix}activity - Shows or updates the bot activity text
{prefix}banner - Preview a banner style
{prefix}backups - List backup files
{prefix}json - shows the json entry for the server
{prefix}servers - Shows the server list
{prefix}stats - Shows runtime system stats (CPU, memory, disk, network, uptime)
{prefix}cogs - manage cogs (start, stop, restart)
{prefix}sync - re-sync all loaded slash commands
{prefix}shutdown - Shutdown the bot with an optional channel + reason
```looking for help with the / commands ? run /help !"""
        await ctx.send(help_text, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='ping')
    async def ping(self, ctx: commands.Context):
        if not await self._owner_only(ctx):
            return
        start_time = time.perf_counter()
        raw_ws_latency = self.bot.latency
        ws_latency = round(raw_ws_latency * 1000) if raw_ws_latency is not None and math.isfinite(raw_ws_latency) else 0

        async with ctx.typing():
            await asyncio.sleep(0)
            end_time = time.perf_counter()
            api_latency = round((end_time - start_time) * 1000)

        ws_text = "unknown" if raw_ws_latency is None or not math.isfinite(raw_ws_latency) else f"{ws_latency}ms"
        await ctx.send(
            f"🏓 Pong! - **WebSocket:** {ws_text} - **API Round-Trip:** {api_latency}ms",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.command(name='stats')
    async def stats(self, ctx: commands.Context):
        if not await self._owner_only(ctx):
            return

        if psutil is None:
            return await ctx.send("<:disapprove:1517452151012589662> `psutil` is not available, so process stats cannot be gathered.")

        try:
            process = psutil.Process(os.getpid())
            process_cpu = process.cpu_percent(interval=None)
            process_memory = process.memory_info()
            process_io = process.io_counters()
            uptime_seconds = max(0.0, time.monotonic() - runtime.STARTED_AT)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return await ctx.send("<:disapprove:1517452151012589662> process stats are unavailable for this bot instance.")

        stats_text = f"""```text
Process: {os.path.basename(sys.argv[0]) or 'python'}
CPU: {process_cpu:.1f}%
Memory: {process_memory.rss / (1024 ** 2):.1f} MiB
Threads: {process.num_threads()}
Disk read: {process_io.read_bytes / (1024 ** 2):.1f} MiB
Disk write: {process_io.write_bytes / (1024 ** 2):.1f} MiB
Uptime: {format_duration(uptime_seconds)}
```"""
        await ctx.send(stats_text, allowed_mentions=discord.AllowedMentions.none())

    async def _env_value_command(self, ctx: commands.Context, new_value: str, env_key: str, label: str) -> None:
        if not await self._owner_only(ctx):
            return
        if not new_value.strip():
            await ctx.send(f"Current {label}: `{os.getenv(env_key) or ''}`")
            return
        cleaned_value = new_value.strip()
        update_env_setting(env_key, cleaned_value)
        self._restart_presence()
        await ctx.send(f"Updated {env_key} in .env to `{cleaned_value}`.")

    @commands.command(name='ver')
    async def ver(self, ctx: commands.Context, *, new_value: str = ''):
        await self._env_value_command(ctx, new_value, "BOT_VERSION", "version")

    @commands.command(name='alt')
    async def alt(self, ctx: commands.Context, *, new_value: str = ''):
        await self._env_value_command(ctx, new_value, "BOT_VERSION_ALTERNATE", "alternate version")

    @commands.command(name='activity')
    async def activity(self, ctx: commands.Context, *, new_value: str = ''):
        await self._env_value_command(ctx, new_value, "ACTIVITY", "activity")

    @commands.command(name='banner')
    async def banner(self, ctx: commands.Context, *args: str):
        if not await self._owner_only(ctx):
            return

        style_choice = None
        kind_choice = "welcome"
        for arg in (arg.lower() for arg in args):
            if arg in BANNER_KINDS:
                kind_choice = arg
            elif style_choice is None:
                style_choice = arg

        style_name = normalize_banner_style(style_choice or get_user_banner_style(str(ctx.author.id)))
        style_label = "Admin" if style_name == "admin" else (style_name if style_name == "1000" else style_name.title())
        kind_label = "Welcome" if kind_choice == "welcome" else "Goodbye" if kind_choice == "goodbye" else "Level"

        preview = await create_banner_preview(ctx.author, kind=kind_choice, style_override=style_name)
        if preview is None:
            return await ctx.send(f"<:disapprove:1517452151012589662> No banner found for style `{style_label}` and kind `{kind_label}`.")

        await ctx.send(f"Banner preview: `{style_label}` / `{kind_label}`", file=preview)

    @commands.command(name='backups')
    async def backups(self, ctx: commands.Context):
        if not await self._owner_only(ctx):
            return
        view = BackupListView(ctx.author.id)
        message = await ctx.send(view=view)
        view.message = message

    @commands.command(name='shutdown')
    async def shutdown(self, ctx: commands.Context, *, args: str = ''):
        if not await self._owner_only(ctx):
            return

        channel = None
        reason = "No reason provided"

        if args:
            parts = args.split(maxsplit=1)
            if parts and parts[0].startswith("#"):
                channel_name = parts[0].lstrip("#")
                channel = discord.utils.get(ctx.guild.text_channels, name=channel_name) if ctx.guild else None
                if len(parts) > 1:
                    reason = parts[1]
            else:
                reason = args

        if channel is None:
            channel = self.bot.get_channel(SHUTDOWN_NOTICE_CHANNEL_ID)
        if channel is None and isinstance(ctx.channel, discord.TextChannel):
            channel = ctx.channel
        shutdown_embed = discord.Embed(
            title="Bot Shutdown Initiated",
            description=f"🔌 {reason}"[:4096],
            color=discord.Color.light_gray()
        )

        if channel is not None:
            try:
                sent_msg = await channel.send(embed=shutdown_embed)
                if channel.type == discord.ChannelType.news:
                    try:
                        await sent_msg.publish()
                    except Exception:
                        pass
            except discord.Forbidden as error:
                add_bot_error_entry(ctx.guild.id if ctx.guild else None, channel.id, ctx.author, "shutdown notice", error)
                await ctx.send(f"<:disapprove:1517452151012589662> Could not send the shutdown notice to {channel.mention}.")
                return
            except Exception as e:
                await ctx.send(f"<:disapprove:1517452151012589662> Could not send the shutdown notice to {channel.mention}. Error: {e}")
                return

        loop_cog = self.bot.get_cog('LoopCog')
        if loop_cog is not None and loop_cog.update_presence.is_running():
            loop_cog.update_presence.cancel()
            await asyncio.sleep(1)

        response_text = "Going to sleep..."
        if channel is not None:
            response_text = "<:nUtils:1518376146008539146> Bot is shutting down."

        await ctx.send(response_text)

        shutdown_activity = discord.Activity(type=discord.ActivityType.watching, name="App is shutting down!!! !! !")
        sleep_activity = discord.Activity(type=discord.ActivityType.watching, name="App is sleeping... zZzZzZ")
        for shard_id in self.bot.shards:
            await self.bot.change_presence(activity=shutdown_activity, status=discord.Status.dnd, shard_id=shard_id)
        await asyncio.sleep(10)
        for shard_id in self.bot.shards:
            await self.bot.change_presence(activity=sleep_activity, status=discord.Status.idle, shard_id=shard_id)
        await self.bot.close()

    @commands.command(name='servers')
    async def servers(self, ctx: commands.Context):
        if not await self._owner_only(ctx):
            return
        guilds = sorted(self.bot.guilds, key=lambda g: g.name.lower())
        view = ServersListView(ctx.author.id, guilds)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot):
    await bot.add_cog(LegacyCog(bot))
