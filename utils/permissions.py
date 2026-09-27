"""Permission and role-hierarchy checks shared by the cogs."""

from __future__ import annotations

from typing import Iterable

import discord

# Re-exported for the cogs that import it from here.
from utils.automod import run_automod_check_for_interaction


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


def guild_owner_bypasses_role_checks(interaction: discord.Interaction) -> bool:
    return interaction.guild is not None and interaction.user.id == interaction.guild.owner_id


def validate_role_selection(interaction: discord.Interaction, role: discord.Role | None, role_label: str) -> str | None:
    if role is None:
        return None
    if not guild_owner_bypasses_role_checks(interaction) and interaction.user.top_role <= role:
        return f"<:disapprove:1517452151012589662> You cannot configure a {role_label} that is equal or higher than your highest role."
    if interaction.guild.me.top_role <= role:
        return "<:disapprove:1517452151012589662> I cannot assign that role because it is equal or higher than my highest role."
    return None


__all__ = [
    'guild_owner_bypasses_role_checks',
    'validate_role_selection',
    'command_allowed',
    'has_permission',
    'member_has_permission',
    'run_automod_check_for_interaction',
]
