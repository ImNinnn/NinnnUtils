"""Permission helper functions for command access checks.

This module is intentionally self-contained so moderation and related cogs do not
need to depend on the legacy helper runtime module for permission checks.
"""

from __future__ import annotations

from typing import Iterable

import discord


def _normalize_permission_name(permission: str | discord.Permissions) -> str:
    if isinstance(permission, discord.Permissions):
        if not permission.value:
            return ""
        return ""

    name = str(permission).strip().lower().replace(' ', '_')
    if not name:
        raise ValueError('Permission name cannot be empty.')
    return name


def member_has_permission(member: discord.Member | None, *permissions: str, allow_owner: bool = True) -> bool:
    """Return True when the selected member has all requested permissions."""
    if member is None:
        return False

    if allow_owner and getattr(member, 'guild', None) is not None and getattr(member.guild, 'owner_id', None) == member.id:
        return True

    if not isinstance(member, discord.Member):
        return False

    if not permissions:
        return True

    guild_perms = member.guild_permissions
    for permission in permissions:
        permission_name = _normalize_permission_name(permission)
        if not permission_name:
            continue
        if not hasattr(guild_perms, permission_name):
            raise AttributeError(f'Unknown Discord permission: {permission_name}')
        if not getattr(guild_perms, permission_name):
            return False
    return True


def has_permission(member: discord.Member | None, permission: str | Iterable[str], *, allow_owner: bool = True) -> bool:
    """Compatibility wrapper for older permission checks."""
    if isinstance(permission, str):
        return member_has_permission(member, permission, allow_owner=allow_owner)
    return member_has_permission(member, *tuple(permission), allow_owner=allow_owner)


def command_allowed(member: discord.Member | None, required: str | Iterable[str], *, allow_owner: bool = True) -> bool:
    """Check whether a member satisfies the required permission set for a command."""
    if isinstance(required, str):
        return member_has_permission(member, required, allow_owner=allow_owner)
    return member_has_permission(member, *tuple(required), allow_owner=allow_owner)


async def run_automod_check_for_interaction(interaction: discord.Interaction, content: str, *, source_label: str = 'message') -> bool:
    """Compatibility wrapper for guild AutoMod enforcement."""
    if not interaction or not getattr(interaction, 'guild', None):
        return False

    try:
        from helper import run_automod_check_for_content
    except Exception:
        return False

    if await run_automod_check_for_content(
        interaction.guild,
        interaction.user,
        interaction.channel,
        content,
        source_label=source_label,
    ):
        try:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send('Blocked word or phrase detected.', ephemeral=True)
        except Exception:
            pass
        return True
    return False


__all__ = [
    'command_allowed',
    'has_permission',
    'member_has_permission',
    'run_automod_check_for_interaction',
]
