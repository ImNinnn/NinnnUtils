import discord
from discord.ext.commands import Context
from main import bot_error_cache
from datetime import datetime, timezone

bot_error_cache = bot_error_cache

def add_bot_error(guild_id: int | None, channel_id: int | None, user, command_name: str, error: Exception, interaction: discord.Interaction = None):
    """Unified error logging. If interaction is provided, extracts guild/channel/user/command from it."""
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

    bot_error_cache.append({
        "guild_id": interaction.guild.id,
        "channel_id": interaction.channel.id,
        "user": interaction.user if isinstance(interaction, discord.Interaction) else interaction.author,
        "command_name": command_name,
        "error_type": type(error).__name__,
        "error_message": str(error) or "No error message provided",
        "time": datetime.now(timezone.utc),
    })

    if len(bot_error_cache) > 10:
        bot_error_cache = bot_error_cache[-10:]


def add_bot_error_entry(guild_id: int | None, channel_id: int | None, user, source: str, error: Exception):
    """Backwards compatibility wrapper for add_bot_error"""
    add_bot_error(guild_id, channel_id, user, source, error)
