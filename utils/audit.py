"""Shared audit logging: admin log channels, webhook delivery and the bot error log.

Used by several cogs and by the settings panels, so it lives outside any single cog.
"""

import asyncio
import os
from datetime import datetime, timezone

import discord

import save
from utils import runtime
from utils.formatting import format_user_reference

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Kept when this module is reloaded by the cog manager.
_KEEP_ON_RELOAD = ("webhook_cache", "bot_error_cache")

webhook_cache: dict[str, discord.Webhook] = {}
bot_error_cache: list[dict] = []



def prune_history_entries(cache: list, *, key, max_items: int) -> list:
    if not cache:
        return []

    grouped: dict[object, list[dict]] = {}
    for entry in cache:
        grouped.setdefault(key(entry), []).append(entry)

    pruned: list[dict] = []
    for group_entries in grouped.values():
        pruned.extend(group_entries[-max_items:])

    pruned.sort(key=lambda entry: entry.get("time") or entry.get("created_at") or entry.get("edited_at") or entry.get("deleted_at") or datetime.now(timezone.utc))
    return pruned


# ---------------------------------------------------------------- admin log channels

def get_guild_admin_log_channel_ids(guild: discord.Guild) -> list[int]:
    guild_config, _ = save.get_guild_config(str(guild.id))
    channel_ids = []
    for channel_id in guild_config.get("admin_log_channels", {}):
        try:
            channel_id = int(channel_id)
        except (TypeError, ValueError):
            continue
        if guild.get_channel(channel_id) is not None:
            channel_ids.append(channel_id)
    return channel_ids


def get_admin_log_channel_mentions(guild: discord.Guild) -> list[str]:
    return [guild.get_channel(channel_id).mention for channel_id in get_guild_admin_log_channel_ids(guild)]


def _save_admin_log_channel_ids(guild: discord.Guild, channel_ids: list[int]) -> None:
    _, data = save.get_guild_config(str(guild.id))
    data[str(guild.id)]["admin_log_channels"] = {str(channel_id): True for channel_id in channel_ids}
    save.save_guild_data(data)


def add_admin_log_channel(guild: discord.Guild, channel_id: int) -> None:
    channel_ids = get_guild_admin_log_channel_ids(guild)
    if channel_id not in channel_ids:
        channel_ids.append(channel_id)
    _save_admin_log_channel_ids(guild, channel_ids)


def remove_admin_log_channel(guild: discord.Guild, channel_id: int) -> bool:
    guild_config, _ = save.get_guild_config(str(guild.id))
    if str(channel_id) not in guild_config.get("admin_log_channels", {}):
        return False
    _save_admin_log_channel_ids(guild, [cid for cid in get_guild_admin_log_channel_ids(guild) if cid != channel_id])
    return True


# ---------------------------------------------------------------- webhook delivery

async def get_or_create_webhook(channel: discord.TextChannel, guild_id: int) -> discord.Webhook | None:
    cache_key = f"{guild_id}:{channel.id}"
    if cache_key in webhook_cache:
        try:
            webhook = webhook_cache[cache_key]
            await webhook.fetch()
            return webhook
        except (discord.NotFound, discord.Forbidden):
            del webhook_cache[cache_key]

    try:
        me = channel.guild.me
        if me is None:
            return None

        webhook_name = f"{me.name} [logs]"
        avatar_bytes = None
        avatar_path = os.path.join(BASE_DIR, "log_pfp.png")
        if os.path.exists(avatar_path):
            try:
                with open(avatar_path, "rb") as f:
                    avatar_bytes = f.read()
            except Exception:
                pass

        webhooks = await channel.webhooks()
        for webhook in webhooks:
            if webhook.name == webhook_name:
                webhook_cache[cache_key] = webhook
                return webhook

        webhook = await channel.create_webhook(
            name=webhook_name,
            avatar=avatar_bytes,
            reason="Audit logging system"
        )
        print(f"[bot] Created new webhook: {webhook_name} in {channel.name}")
        webhook_cache[cache_key] = webhook
        return webhook
    except (discord.Forbidden, discord.HTTPException):
        return None


async def send_audit_log(guild: discord.Guild, event_type: str, embed: discord.Embed | None = None, content: str = "") -> None:
    if event_type == "discord_audit_log":
        return
    if not guild:
        return

    try:
        for ch_id in get_guild_admin_log_channel_ids(guild):
            try:
                channel = guild.get_channel(ch_id)
                if not channel or not isinstance(channel, discord.TextChannel):
                    continue

                webhook = await get_or_create_webhook(channel, guild.id)
                if not webhook:
                    continue

                if embed:
                    await webhook.send(embed=embed, content=content if content else None)
                else:
                    await webhook.send(content=content if content else "(No audit data)")
            except Exception:
                pass
    except Exception:
        pass


# ---------------------------------------------------------------- bot error log

def _format_bot_error_user(user) -> str:
    if user is None:
        return "Unknown"
    try:
        return format_user_reference(user)
    except Exception:
        return getattr(user, "name", str(user))


async def _dispatch_bot_error_log(guild_id: int, channel_id: int | None, user, command_name: str, error: Exception, timestamp: datetime) -> None:
    guild = runtime.bot.get_guild(guild_id) if runtime.bot is not None else None
    if guild is None:
        return

    embed = discord.Embed(
        title="<:warning:1517452174991556758> Bot Error",
        color=discord.Color.orange()
    )
    embed.add_field(name="Command", value=str(command_name or "unknown"), inline=True)
    embed.add_field(name="User", value=_format_bot_error_user(user), inline=True)
    if channel_id:
        embed.add_field(name="Channel", value=f"<#{channel_id}>", inline=True)
    embed.add_field(name="Error Type", value=type(error).__name__, inline=True)
    embed.add_field(name="Message", value=(str(error) or "No error message provided")[:1024], inline=False)
    embed.timestamp = timestamp
    await send_audit_log(guild, "bot_error", embed=embed)


def add_bot_error(guild_id: int | None, channel_id: int | None, user, command_name: str, error: Exception, interaction: discord.Interaction = None):
    global bot_error_cache

    if interaction is not None:
        if interaction.guild is None:
            return
        guild_id = interaction.guild.id
        channel_id = interaction.channel_id
        user = interaction.user
        command_name = getattr(getattr(interaction, "command", None), "qualified_name", None)
        if not command_name:
            command_name = getattr(getattr(interaction, "command", None), "name", "unknown command")

    if guild_id is None:
        return

    timestamp = datetime.now(timezone.utc)
    bot_error_cache.append({
        "guild_id": guild_id,
        "channel_id": channel_id,
        "user": user,
        "command_name": command_name,
        "error_type": type(error).__name__,
        "error_message": str(error) or "No error message provided",
        "time": timestamp,
    })

    bot_error_cache = prune_history_entries(bot_error_cache, key=lambda entry: entry.get("guild_id"), max_items=25)

    try:
        asyncio.get_running_loop().create_task(_dispatch_bot_error_log(guild_id, channel_id, user, command_name, error, timestamp))
    except RuntimeError:
        pass


def add_bot_error_entry(guild_id: int | None, channel_id: int | None, user, source: str, error: Exception):
    add_bot_error(guild_id, channel_id, user, source, error)
