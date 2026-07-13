import time

import discord

from Shared.Errors import add_bot_error_entry
from main import AFK_PREFIX, afk_status, AFK_MESSAGE_WINDOW_SECONDS


def get_afk_status_key(guild_id: int | str, user_id: int | str) -> str:
    return f"{guild_id}:{user_id}"


def build_afk_nickname(display_name: str) -> str:
    base_nickname = display_name.strip()
    if not base_nickname:
        base_nickname = "AFK"

    if len(base_nickname) + len(AFK_PREFIX) + 1 <= 32:
        return f"{AFK_PREFIX} {base_nickname}"

    max_base_length = max(0, 32 - len(AFK_PREFIX) - 1)
    return f"{AFK_PREFIX} {base_nickname[:max_base_length].rstrip()}"


async def set_afk_status(member: discord.Member, reason: str | None = None) -> bool:
    key = get_afk_status_key(member.guild.id, member.id)
    reason_text = (reason or "No reason provided.").strip() or "No reason provided."

    existing_state = afk_status.get(key)
    if existing_state:
        existing_state["reason"] = reason_text
        existing_state["message_times"] = [ts for ts in existing_state.get("message_times", []) if time.time() - ts <= AFK_MESSAGE_WINDOW_SECONDS]
        return False

    original_nickname = getattr(member, "display_name", None)
    afk_status[key] = {
        "reason": reason_text,
        "original_nickname": original_nickname,
        "message_times": [],
    }

    me = getattr(member.guild, "me", None)
    can_manage_nicknames = bool(me and me.guild_permissions.manage_nicknames)

    if not can_manage_nicknames:
        add_bot_error_entry(
            member.guild.id,
            None,
            member,
            "afk nickname update",
            PermissionError("Bot lacks manage_nicknames permission to update AFK nickname")
        )
        return True

    try:
        await member.edit(nick=build_afk_nickname(original_nickname or member.name), reason=f"AFK status enabled: {reason_text}")
    except (discord.Forbidden, discord.HTTPException) as error:
        add_bot_error_entry(member.guild.id, None, member, "afk nickname update", error)

    return True

async def clear_afk_status(member: discord.Member, channel: discord.abc.Messageable | None = None) -> None:
    key = get_afk_status_key(member.guild.id, member.id)
    state = afk_status.pop(key, None)
    if not state:
        return

    original_nickname = state.get("original_nickname")
    me = getattr(member.guild, "me", None)
    if me and me.guild_permissions.manage_nicknames:
        try:
            await member.edit(nick=original_nickname or None, reason="AFK status removed")
        except (discord.Forbidden, discord.HTTPException):
            pass

    if channel is not None:
        try:
            await channel.send(f"<:approve:1517452125687513158> **{member.display_name}** is no longer AFK.")
        except (discord.Forbidden, discord.HTTPException):
            pass


def get_afk_reason(entry: dict | None) -> str:
    if not entry:
        return "No reason provided."
    reason = entry.get("reason")
    return str(reason or "No reason provided.")
