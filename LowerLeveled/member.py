import discord


def resolve_member_from_input(guild: discord.Guild, member_input: str | discord.Member | discord.User | None) -> discord.Member | None:
    if not guild:
        return None

    if isinstance(member_input, discord.Member):
        return member_input

    if isinstance(member_input, discord.User):
        return guild.get_member(member_input.id)

    if not member_input:
        return None

    value = str(member_input).strip()
    if not value:
        return None

    if value.startswith("<@") and value.endswith(">"):
        value = value[2:-1].lstrip("!")

    if value.isdigit():
        return guild.get_member(int(value))

    return guild.get_member_named(value) or discord.utils.find(
        lambda member: member.name.lower() == value.lower() or member.display_name.lower() == value.lower(),
        guild.members,
    )