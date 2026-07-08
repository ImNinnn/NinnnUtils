import discord
from LowerLeveled.owner import guild_owner_bypasses_role_checks


def validate_role_selection(interaction: discord.Interaction, role: discord.Role | None, role_label: str) -> str | None:
    if role is None:
        return None
    if not guild_owner_bypasses_role_checks(interaction) and interaction.user.top_role <= role:
        return f"<:disapprove:1517452151012589662> You cannot configure a {role_label} that is equal or higher than your highest role."
    if interaction.guild.me.top_role <= role:
        return "<:disapprove:1517452151012589662> I cannot assign that role because it is equal or higher than my highest role."
    return None