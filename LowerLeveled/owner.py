def is_server_owner(interaction: discord.Interaction):
    return interaction.user.id == interaction.guild.owner_id

def guild_owner_bypasses_role_checks(interaction: discord.Interaction) -> bool:
    return interaction.guild is not None and interaction.user.id == interaction.guild.owner_id

