def add_bot_error(interaction: discord.Interaction, error: Exception):
    global bot_error_cache

    if interaction.guild is None:
        return

    command_name = getattr(getattr(interaction, "command", None), "qualified_name", None)
    if not command_name:
        command_name = getattr(getattr(interaction, "command", None), "name", "unknown command")

    bot_error_cache.append({
        "guild_id": interaction.guild.id,
        "channel_id": interaction.channel_id,
        "user": interaction.user,
        "command_name": command_name,
        "error_type": type(error).__name__,
        "error_message": str(error) or "No error message provided",
        "time": datetime.now(timezone.utc),
    })

    if len(bot_error_cache) > 10:
        bot_error_cache = bot_error_cache[-10:]


def add_bot_error_entry(guild_id: int | None, channel_id: int | None, user, source: str, error: Exception):
    global bot_error_cache

    if guild_id is None:
        return

    bot_error_cache.append({
        "guild_id": guild_id,
        "channel_id": channel_id,
        "user": user,
        "command_name": source,
        "error_type": type(error).__name__,
        "error_message": str(error) or "No error message provided",
        "time": datetime.now(timezone.utc),
    })

    if len(bot_error_cache) > 10:
        bot_error_cache = bot_error_cache[-10:]

