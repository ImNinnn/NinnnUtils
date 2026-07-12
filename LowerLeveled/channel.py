import discord


def _get_channel_mentions(guild: discord.Guild, channel_dict: dict) -> list[str]:
    """Generic helper to get channel mentions from a dictionary"""
    return [guild.get_channel(cid).mention for cid in channel_dict if guild.get_channel(cid) is not None]