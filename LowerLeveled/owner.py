from __future__ import annotations
import discord
from discord.ext import commands

def is_server_owner(interaction: discord.Interaction | commands.Context) -> bool:
    return interaction.user.id == interaction.guild.owner_id

def guild_owner_bypasses_role_checks(interaction: discord.Interaction | commands.Context) -> bool:
    return interaction.guild is not None and interaction.user.id == interaction.guild.owner_id

