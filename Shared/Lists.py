import discord


def find_reminder_index(reminders: list[dict], identifier: str) -> int | None:
    identifier_text = str(identifier).strip()
    if identifier_text.isdigit():
        index = int(identifier_text) - 1
        if 0 <= index < len(reminders):
            return index
    for index, reminder in enumerate(reminders):
        if str(reminder.get("name", "")).strip().lower() == identifier_text.lower():
            return index
    return None

def find_checklist_item_index(item_list: list[dict], identifier: str) -> int | None:
    identifier_text = str(identifier).strip()
    if identifier_text.isdigit():
        index = int(identifier_text) - 1
        if 0 <= index < len(item_list):
            return index
    for index, item in enumerate(item_list):
        if str(item.get("content", "")).strip().lower() == identifier_text.lower():
            return index
    return None

def format_checklist_item(item: dict, index: int) -> str:
    status = item.get("status", "none")
    emoji = {
        "red": "<:disapprove:1517452151012589662>",
        "green": "<:approve:1517452125687513158>",
        "yellow": "<:warning:1517452174991556758>",
    }.get(status, "")
    content = item.get("content", "")
    return f"{index + 1}. {emoji} {content}".strip()


def get_total_checklist_items(lists: list[list[dict]]) -> int:
    return sum(len(item_list) for item_list in lists)


def get_reminder_display(reminder: dict) -> str:
    when = reminder.get("when")
    if isinstance(when, int):
        return f"<t:{when}:R>"
    return str(when)


def get_reminder_destination(reminder: dict, guild: discord.Guild | None = None) -> str:
    send_mode = reminder.get("send", "dm")
    if send_mode == "channel":
        channel_id = reminder.get("channel_id")
        if channel_id and guild:
            channel = guild.get_channel(channel_id)
            return channel.mention if channel else f"<#{channel_id}>"
        return "channel"
    if send_mode == "both":
        channel_id = reminder.get("channel_id")
        if channel_id and guild:
            channel = guild.get_channel(channel_id)
            channel_text = channel.mention if channel else f"<#{channel_id}>"
        else:
            channel_text = "channel"
        return f"{channel_text} and DM"
    return "DM"


def get_reminder_message_text(reminder: dict) -> str:
    description = reminder.get("description", "").strip()
    if description:
        return description
    return "No description provided."

async def refresh_checklist_message(interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
    if settings_message is None:
        settings_message = interaction.message
        if settings_message is None:
            try:
                settings_message = await interaction.original_response()
            except (discord.NotFound, discord.HTTPException):
                settings_message = None
    if settings_message is None:
        return
    try:
        await settings_message.edit(view=view)
        return
    except (discord.NotFound, discord.HTTPException):
        pass
    try:
        await interaction.followup.edit_message(message_id=settings_message.id, view=view)
        return
    except Exception:
        pass
    try:
        await interaction.edit_original_response(view=view)
    except Exception:
        pass
