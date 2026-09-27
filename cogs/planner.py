"""Planner: personal notes, a checklist and reminders (/notes-lists-reminders), plus reminder delivery."""

import asyncio
import re
import uuid
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, Container, LayoutView, Modal, Section, Separator, TextDisplay, TextInput

from save import load_user_settings, save_user_settings
from utils import runtime
from utils.formatting import parse_duration_to_seconds
from utils.permissions import run_automod_check_for_interaction
from utils.user_settings import get_user_color_value, get_user_settings_entry, parse_utc_offset
from utils.views import TimeoutDisabledLayoutView, TimeoutDisabledView, safe_send


MAX_USER_NOTES = 3
MAX_USER_REMINDERS = 7
MAX_USER_LIST_ITEMS = 30


def can_add_user_reminder(user_id: str) -> bool:
    return len(get_user_reminders(user_id)) < MAX_USER_REMINDERS


def get_user_notes(user_id: str) -> list[str]:
    settings = load_user_settings()
    notes = get_user_settings_entry(settings, user_id).get("notes")
    if isinstance(notes, list):
        return [str(note) for note in notes[:MAX_USER_NOTES]]
    return []


def save_user_notes(user_id: str, notes: list[str]) -> None:
    settings = load_user_settings()
    user_settings = get_user_settings_entry(settings, user_id)
    user_settings["notes"] = [str(note) for note in notes[:MAX_USER_NOTES]]
    save_user_settings(settings)


def get_user_reminders(user_id: str) -> list[dict]:
    settings = load_user_settings()
    reminders = get_user_settings_entry(settings, user_id).get("reminders")
    if isinstance(reminders, list):
        valid_reminders = []
        for reminder in reminders:
            if isinstance(reminder, dict) and "name" in reminder and "when" in reminder:
                valid_reminders.append(reminder)
        return valid_reminders
    return []


def save_user_reminders(user_id: str, reminders: list[dict]) -> None:
    settings = load_user_settings()
    get_user_settings_entry(settings, user_id)["reminders"] = reminders
    save_user_settings(settings)


def get_user_lists(user_id: str) -> list[list[dict]]:
    settings = load_user_settings()
    lists = get_user_settings_entry(settings, user_id).get("lists")
    if not isinstance(lists, list) or len(lists) < 1:
        return [[]]
    first_list = lists[0]
    if isinstance(first_list, list):
        return [[item for item in first_list if isinstance(item, dict)]]
    return [[]]


def save_user_lists(user_id: str, lists: list[list[dict]]) -> None:
    settings = load_user_settings()
    user_settings = get_user_settings_entry(settings, user_id)
    normalized = []
    first_list = lists[0] if lists and isinstance(lists[0], list) else []
    normalized.append(first_list[:MAX_USER_LIST_ITEMS])
    user_settings["lists"] = normalized
    save_user_settings(settings)


MIN_REPEAT_SECONDS = 60
# Components v2 messages hold at most 4000 characters of text.
MAX_PANEL_TEXT = 3500


def _utc_naive(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)


def fit_lines(lines: list[str], limit: int = MAX_PANEL_TEXT) -> list[str]:
    """Shorten long lines only when all of them together would not fit in one message."""
    if sum(len(line) + 1 for line in lines) <= limit:
        return lines
    per_line = max(20, limit // max(1, len(lines)) - 1)
    return [line if len(line) <= per_line else line[:per_line - 1] + "…" for line in lines]


def parse_reminder_time(value: str, user_id: str | None = None) -> int | None:
    if not value:
        return None

    text = value.strip()
                                                          
    if text.lower().startswith("in "):
        text = text[3:].strip()
    elif text.lower().startswith("at "):
        text = text[3:].strip()

                                                                                           
    if re.fullmatch(r'(?:\d+[dhms]\s*)+', text.lower()):
        seconds = parse_duration_to_seconds(text)
        if seconds is None or seconds <= 0:
            return None
        return int(datetime.now(timezone.utc).timestamp()) + seconds

                                                                                     
    offs = None
    if user_id is not None:
        try:
            settings = load_user_settings()
            entry = get_user_settings_entry(settings, str(user_id))
            off = entry.get("timezone_offset")
            offs = parse_utc_offset(off) if off else None
        except Exception:
            offs = None

    now_utc = datetime.now(timezone.utc)

                                                                           
    m_time = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if m_time:
        hour = int(m_time.group(1))
        minute = int(m_time.group(2))
                              
        if offs is not None:
            now_local = (now_utc + offs)
        else:
            now_local = now_utc
        try:
            candidate_local = datetime(now_local.year, now_local.month, now_local.day, hour, minute)
        except ValueError:
            return None
                                                 
        if offs is not None:
            candidate_utc = candidate_local - offs
        else:
            candidate_utc = candidate_local
        candidate_utc = candidate_utc.replace(tzinfo=timezone.utc)
        if candidate_utc <= now_utc:
            candidate_local = candidate_local + timedelta(days=1)
            if offs is not None:
                candidate_utc = (candidate_local - offs).replace(tzinfo=timezone.utc)
            else:
                candidate_utc = candidate_local.replace(tzinfo=timezone.utc)
        return int(candidate_utc.timestamp())

                                                                                                         
    m_date = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?:\s+(\d{1,2}):(\d{2}))?", text)
    if m_date:
        day = int(m_date.group(1))
        month = int(m_date.group(2))
        year_group = m_date.group(3)
        hour = int(m_date.group(4)) if m_date.group(4) else 0
        minute = int(m_date.group(5)) if m_date.group(5) else 0

                                                                 
        if year_group:
            y = int(year_group)
            if y < 100:
                y += 2000
            try:
                reminder_local = datetime(y, month, day, hour, minute)
            except ValueError:
                return None
            if offs is not None:
                reminder_utc = reminder_local - offs
            else:
                reminder_utc = reminder_local
            reminder_utc = reminder_utc.replace(tzinfo=timezone.utc)
            if reminder_utc <= now_utc:
                return None
            return int(reminder_utc.timestamp())
        else:
                                                                            
            if offs is not None:
                now_local = (now_utc + offs)
            else:
                now_local = now_utc
            year = now_local.year
            try:
                candidate_local = datetime(year, month, day, hour, minute)
            except ValueError:
                return None
            if offs is not None:
                candidate_utc = (candidate_local - offs).replace(tzinfo=timezone.utc)
            else:
                candidate_utc = candidate_local.replace(tzinfo=timezone.utc)
            if candidate_utc <= now_utc:
                try:
                    candidate_local = datetime(year + 1, month, day, hour, minute)
                except ValueError:
                    return None
                if offs is not None:
                    candidate_utc = (candidate_local - offs).replace(tzinfo=timezone.utc)
                else:
                    candidate_utc = candidate_local.replace(tzinfo=timezone.utc)
                if candidate_utc <= now_utc:
                    return None
            return int(candidate_utc.timestamp())

    return None


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


def get_reminder_display(reminder: dict) -> str:
    when = reminder.get("when")
    if isinstance(when, int):
        return f"<t:{when}:R>"
    return str(when)


def format_repeat_interval(seconds: int | None) -> str:
    if not isinstance(seconds, int) or seconds <= 0:
        return "Never"

    total = int(seconds)
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs or not parts:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")

    if not parts:
        return "Never"
    return "Every " + " ".join(parts)


def get_reminder_repeat_text(reminder: dict) -> str:
    repeat = reminder.get("repeat")
    if isinstance(repeat, int) and repeat > 0:
        return format_repeat_interval(repeat)
    return "Never"


def get_reminder_destination(reminder: dict, guild: discord.Guild | None = None) -> str:
    return ""


def get_reminder_message_text(reminder: dict) -> str:
    description = reminder.get("description", "").strip()
    if description:
        return description
    return "No description provided."


PENDING_POSTPONE_REMINDERS: dict[str, dict] = {}


class ReminderPostponeModal(Modal):
    def __init__(self, user_id: str, postpone_id: str, current_time: int):
        super().__init__(title="Postpone Reminder")
        self.user_id = user_id
        self.postpone_id = postpone_id
        self.time_input = TextInput(
            label="New reminder time",
            placeholder="Examples: 1h, 30m, 10:00, 20/02, 20/02 23:00, 20/02/2010 23:00",
            required=True,
                                                              
            default=(lambda ts, uid: (
                (_utc_naive(ts) + (parse_utc_offset(get_user_settings_entry(load_user_settings(), str(uid)).get('timezone_offset')) if get_user_settings_entry(load_user_settings(), str(uid)).get('timezone_offset') else timedelta(0))).strftime('%d/%m/%Y %H:%M')
            ))(current_time, self.user_id),
        )
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction):
        data = PENDING_POSTPONE_REMINDERS.get(self.postpone_id)
        if not data or str(interaction.user.id) != data["user_id"]:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This postpone link is no longer valid.", ephemeral=True)
            return

        reminder = data["reminder"]
        new_time = parse_reminder_time(self.time_input.value, self.user_id)
        if new_time is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid reminder time. Examples: '1h', '30m', '10:00', '20/02', '20/02 23:00', '20/02/2010 23:00'.", ephemeral=True)
            return

        new_reminder = {
            "name": reminder.get("name", "Reminder"),
            "description": reminder.get("description", ""),
            "when": new_time,
            "send": reminder.get("send", "dm"),
        }
        # No "repeat": a repeating reminder is still in the list and keeps repeating by itself.
        if reminder.get("channel_id"):
            new_reminder["channel_id"] = reminder["channel_id"]

        reminders = get_user_reminders(str(self.user_id))
        if len(reminders) >= MAX_USER_REMINDERS:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                "<:disapprove:1517452151012589662> You can have up to 7 reminders at once.",
                ephemeral=True,
            )
            return

        reminders.append(new_reminder)
        save_user_reminders(str(self.user_id), reminders)
        PENDING_POSTPONE_REMINDERS.pop(self.postpone_id, None)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Reminder postponed to <t:{new_time}:F>.", ephemeral=True)


class ReminderNotificationView(LayoutView):
    def __init__(self, user_id: str, postpone_id: str, reminder: dict, mention_user: bool):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.postpone_id = postpone_id
        self.reminder = reminder
        self.mention_user = mention_user
        self.build_components()

    def build_components(self):
        reminder_label = f"<:timer:1517996239583576194> {self.reminder.get('name', 'Reminder')}"
        self.postpone_button = Button(label="Postpone", style=discord.ButtonStyle.secondary, custom_id=f"reminder_postpone:{self.postpone_id}")
        self.postpone_button.callback = self.open_postpone

        details = [
            Section(reminder_label, accessory=self.postpone_button),
            Separator(),
            TextDisplay(get_reminder_message_text(self.reminder)),
            TextDisplay(f"{get_reminder_display(self.reminder)}"),
            TextDisplay(f"Repeats: {get_reminder_repeat_text(self.reminder)}"),
        ]
        if self.mention_user:
            details.append(TextDisplay(f"<@{self.user_id}>"))

        container = Container(*details, accent_color=get_user_color_value(str(self.user_id)))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != int(self.user_id):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Only the reminder owner can postpone this reminder.", ephemeral=True)
            return False
        return True

    async def open_postpone(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ReminderPostponeModal(self.user_id, self.postpone_id, self.reminder.get("when", int(datetime.now(timezone.utc).timestamp()))))


async def deliver_reminder(user_id: str, reminder: dict):
    user = runtime.bot.get_user(int(user_id)) if user_id.isdigit() else None
    if not user:
        try:
            user = await runtime.bot.fetch_user(int(user_id))
        except Exception:
            user = None

    postpone_id = uuid.uuid4().hex
    PENDING_POSTPONE_REMINDERS[postpone_id] = {
        "user_id": str(user_id),
        "reminder": reminder,
    }

    if user:
        try:
            await user.send(view=ReminderNotificationView(str(user_id), postpone_id, reminder, mention_user=False))
        except Exception:
            pass


                                                                                      


def is_valid_send_mode(value: str) -> bool:
    return str(value).strip().lower() == "dm"


def get_notes_header(user_id: int) -> str:
    user = runtime.bot.get_user(user_id)
    return f"<:edit:1517497568421085256> Notes for {user.display_name if user else str(user_id)}"


def get_reminders_header(user_id: int) -> str:
    user = runtime.bot.get_user(user_id)
    return f"<:timer:1517996239583576194> Reminders for {user.display_name if user else str(user_id)}"


class NotesMenuView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.notes_button = Button(label="Open", style=discord.ButtonStyle.primary, custom_id="notes_menu_notes")
        self.reminders_button = Button(label="Open", style=discord.ButtonStyle.primary, custom_id="notes_menu_reminders")
        self.checklists_button = Button(label="Open", style=discord.ButtonStyle.primary, custom_id="notes_menu_checklists")

        async def open_notes(interaction: discord.Interaction):
            await interaction.response.edit_message(view=NotesView(self.user_id))

        async def open_reminders(interaction: discord.Interaction):
            await interaction.response.edit_message(view=RemindersView(self.user_id))

        async def open_checklists(interaction: discord.Interaction):
            await interaction.response.edit_message(view=ChecklistView(self.user_id))

        self.notes_button.callback = open_notes
        self.reminders_button.callback = open_reminders
        self.checklists_button.callback = open_checklists
        user = runtime.bot.get_user(self.user_id)
        username = user.display_name if user else str(self.user_id)
        self.add_item(Container(
            TextDisplay(f"<:gear:1517576939097952496> **Notes menu for {username}**"),
            Separator(),
            Section("<:edit:1517497568421085256> Notes", accessory=self.notes_button),
            Section("<:list:1517497572770451567> Checklists", accessory=self.checklists_button),            
            Section("<:timer:1517996239583576194> Reminders", accessory=self.reminders_button),
            Separator(),
            TextDisplay("Found a bug ? Report it in the [support server](https://discord.gg/FSBPvc9zqY)"),
            accent_color=get_user_color_value(str(self.user_id)),
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This menu is only for the original user.", ephemeral=True)
            return False
        return True


class NotesView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, note_index: int = 0):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.note_index = max(0, min(note_index, MAX_USER_NOTES - 1))
        self.notes = get_user_notes(str(self.user_id))
        self.build_components()

    def build_components(self):
        self.clear_items()
        current_note = self.notes[self.note_index] if self.note_index < len(self.notes) else ""
        note_text = current_note or "*No note written yet.*"

        self.edit_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="notes_edit")
        self.share_button = Button(label="Share", style=discord.ButtonStyle.success, custom_id="notes_share", disabled=not bool(current_note.strip()))
        self.cycle_button = Button(label="Next note", style=discord.ButtonStyle.secondary, custom_id="notes_cycle")
        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="notes_back")

        async def edit_note(interaction: discord.Interaction):
            await interaction.response.send_modal(NoteEditModal(self.user_id, self.note_index, current_note))

        async def share_note(interaction: discord.Interaction):
            if interaction.guild and await run_automod_check_for_interaction(interaction, note_text, source_label="/share-note"):
                return
            owner = runtime.bot.get_user(self.user_id)
            owner_name = owner.display_name if owner else str(self.user_id)
            await interaction.response.defer(); await interaction.followup.send(
                view=SharedNoteView(self.user_id, owner_name, note_text),
                ephemeral=False,
            )

        async def cycle_note(interaction: discord.Interaction):
            new_index = (self.note_index + 1) % MAX_USER_NOTES
            await interaction.response.edit_message(view=NotesView(self.user_id, new_index))

        async def back_to_menu(interaction: discord.Interaction):
            await interaction.response.edit_message(view=NotesMenuView(self.user_id))

        self.edit_button.callback = edit_note
        self.share_button.callback = share_note
        self.cycle_button.callback = cycle_note
        self.back_button.callback = back_to_menu

        self.add_item(Container(
            TextDisplay(get_notes_header(self.user_id)),
            Separator(),
            TextDisplay(note_text),
            accent_color=get_user_color_value(str(self.user_id)),
        ))
        self.add_item(discord.ui.ActionRow(self.edit_button, self.share_button, self.cycle_button, self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This notes panel is only for the original user.", ephemeral=True)
            return False
        return True


class NoteEditModal(Modal):
    def __init__(self, user_id: int, note_index: int, current_text: str = ""):
        super().__init__(title="Edit Note")
        self.user_id = user_id
        self.note_index = note_index
        self.note_input = TextInput(
            label="Note",
            style=discord.TextStyle.long,
            default=current_text,
            required=False,
            max_length=1000,
        )
        self.add_item(self.note_input)

    async def on_submit(self, interaction: discord.Interaction):
        notes = get_user_notes(str(self.user_id))
        while len(notes) < MAX_USER_NOTES:
            notes.append("")
        notes[self.note_index] = self.note_input.value.strip()
        save_user_notes(str(self.user_id), notes)
        await interaction.response.edit_message(view=NotesView(self.user_id, self.note_index))


class SharedNoteView(TimeoutDisabledLayoutView):
    def __init__(self, owner_id: int, owner_name: str, note_text: str):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.owner_name = owner_name
        self.note_text = note_text
        self.build_components()

    def build_components(self):
        self.clear_items()
        title = f"<:edit:1517497568421085256> {self.owner_name}'s Note"
        self.add_item(Container(
            TextDisplay(title),
            Separator(),
            TextDisplay(self.note_text or "*No note written yet.*"),
            accent_color=get_user_color_value(str(self.owner_id)),
        ))


class SharedChecklistView(TimeoutDisabledLayoutView):
    def __init__(self, owner_id: int, owner_name: str, item_lines: list[str]):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.owner_name = owner_name
        self.item_lines = item_lines or ["No list items yet."]
        self.build_components()

    def build_components(self):
        self.clear_items()
        title = f"<:list:1517497572770451567> {self.owner_name}'s Checklist"
        self.add_item(Container(
            TextDisplay(title),
            Separator(),
            TextDisplay("\n".join(self.item_lines)),
            accent_color=get_user_color_value(str(self.owner_id)),
        ))


class ReminderModal(Modal):
    def __init__(self, user_id: int, settings_message: discord.Message, existing_index: int | None = None):
        title = "Edit Reminder" if existing_index is not None else "Create Reminder"
        super().__init__(title=title)
        self.user_id = user_id
        self.settings_message = settings_message
        self.existing_index = existing_index
        self.name_input = TextInput(label="Reminder name", placeholder="Brief title", required=True, max_length=100)
        self.description_input = TextInput(label="Reminder description", style=discord.TextStyle.long, required=False, max_length=400)
        self.time_input = TextInput(label="Reminder time", placeholder="Examples: 1h, 30m, 10:00, 20/02, 20/02 23:00, 20/02/2010 23:00", required=True)
        self.repeat_input = TextInput(label="Repeat interval (optional)", placeholder="Examples: 2h, 30d 20m — leave blank for no repeat", required=False)
        self.add_item(self.name_input)
        self.add_item(self.description_input)
        self.add_item(self.time_input)
        self.add_item(self.repeat_input)

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip() or "Reminder"
        description = self.description_input.value.strip()
        when = parse_reminder_time(self.time_input.value, str(self.user_id))
        repeat_seconds = None
        repeat_value = (self.repeat_input.value or "").strip()
        if repeat_value:
            repeat_seconds = parse_duration_to_seconds(repeat_value)
            if repeat_seconds is None:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid repeat interval. Examples: '1h', '30m', '2d 3h'.", ephemeral=True)
                return
            if 0 < repeat_seconds < MIN_REPEAT_SECONDS:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> The repeat interval must be at least 1 minute.", ephemeral=True)
                return

                                                                                   
        if self.existing_index is not None and repeat_seconds is None:
            try:
                existing_reminders = get_user_reminders(str(self.user_id))
                if 0 <= self.existing_index < len(existing_reminders):
                    existing_repeat = existing_reminders[self.existing_index].get("repeat")
                    if isinstance(existing_repeat, int) and existing_repeat > 0:
                        repeat_seconds = int(existing_repeat)
            except Exception:
                pass

        if when is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid reminder time. Examples: '1h', '30m', '10:00', '20/02', '20/02 23:00', '20/02/2010 23:00'.", ephemeral=True)
            return

        reminder = {
            "name": name,
            "description": description,
            "when": when,
            "send": "dm",
        }
        if repeat_seconds:
            reminder["repeat"] = int(repeat_seconds)

        if self.existing_index is None and not can_add_user_reminder(str(self.user_id)):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                "<:disapprove:1517452151012589662> You can have up to 7 reminders at once.",
                ephemeral=True,
            )
            return

        reminders = get_user_reminders(str(self.user_id))
        if self.existing_index is None:
            reminders.append(reminder)
            saved_text = f"<:approve:1517452125687513158> Reminder saved for <t:{when}:F>."
        else:
            if 0 <= self.existing_index < len(reminders):
                reminders[self.existing_index] = reminder
            saved_text = f"<:approve:1517452125687513158> Reminder updated for <t:{when}:F>."
        save_user_reminders(str(self.user_id), reminders)
        try:
            await interaction.response.edit_message(view=RemindersView(self.user_id))
        except Exception:
            try:
                await self.settings_message.edit(view=RemindersView(self.user_id))
            except Exception:
                pass
        await safe_send(interaction, saved_text, ephemeral=True)


class ReminderActionModal(Modal):
    def __init__(self, user_id: int, settings_message: discord.Message, action: str):
        title = "Edit reminder" if action == "edit" else "Delete reminder"
        super().__init__(title=title)
        self.user_id = user_id
        self.settings_message = settings_message
        self.action = action
        self.reminder_input = TextInput(label="Reminder number or name", placeholder="1 or reminder name", required=True, max_length=100)
        self.add_item(self.reminder_input)

    async def on_submit(self, interaction: discord.Interaction):
        reminders = get_user_reminders(str(self.user_id))
        if not reminders:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You have no reminders yet.", ephemeral=True)
            return

        index = find_reminder_index(reminders, self.reminder_input.value)
        if index is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Reminder not found. Use number or exact name.", ephemeral=True)
            return

        if self.action == "delete":
            reminders.pop(index)
            save_user_reminders(str(self.user_id), reminders)
            try:
                await interaction.response.edit_message(view=RemindersView(self.user_id))
            except Exception:
                try:
                    await self.settings_message.edit(view=RemindersView(self.user_id))
                except Exception:
                    pass
            await safe_send(interaction, "<:trash:1517497581058527404> Reminder deleted.", ephemeral=True)
            return

        reminder = reminders[index]
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Reminder found. Click below to continue editing.",
            view=ReminderEditLaunchView(self.user_id, self.settings_message, index, reminder),
            ephemeral=True,
        )


class ReminderShareModal(Modal):
    def __init__(self, user_id: int, settings_message: discord.Message):
        super().__init__(title="Share reminder")
        self.user_id = user_id
        self.settings_message = settings_message
        self.reminder_input = TextInput(label="Reminder number or name", placeholder="1 or reminder name", required=True, max_length=100)
        self.add_item(self.reminder_input)

    async def on_submit(self, interaction: discord.Interaction):
        reminders = get_user_reminders(str(self.user_id))
        if not reminders:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You have no reminders yet.", ephemeral=True)
            return

        index = find_reminder_index(reminders, self.reminder_input.value)
        if index is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Reminder not found. Use number or exact name.", ephemeral=True)
            return

        reminder = reminders[index]

        owner = runtime.bot.get_user(self.user_id)
        creator_name = owner.display_name if owner else str(self.user_id)
        reminder_text = f"{reminder.get('name', '')} {reminder.get('description', '')}"
        if interaction.guild and await run_automod_check_for_interaction(interaction, reminder_text, source_label="/share-reminder"):
            return
        await interaction.response.defer(); await interaction.followup.send(
            view=SharedReminderView(self.user_id, creator_name, reminder),
            ephemeral=False,
        )


class SharedReminderView(TimeoutDisabledLayoutView):
    def __init__(self, owner_id: int, creator_name: str, reminder: dict):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.creator_name = creator_name
        self.reminder = reminder
        self.save_button = Button(label="Add to personal reminders", style=discord.ButtonStyle.primary, custom_id="shared_reminder_add")
        self.save_button.callback = self.add_reminder
        self.build_components()

    def build_components(self):
        self.clear_items()
        title = self.reminder.get("name", "Reminder")
        description = self.reminder.get("description", "").strip() or "No description provided."
        when = get_reminder_display(self.reminder)
        destination = get_reminder_destination(self.reminder, None)

        repeat_text = get_reminder_repeat_text(self.reminder)
        info_lines = [
            TextDisplay(f"When: {when}"),
            TextDisplay(f"Repeats: {repeat_text}"),
        ]
        if destination:
            info_lines.insert(1, TextDisplay(f"Destination: {destination}"))
        info_lines.append(TextDisplay(f"Reminder creator: {self.creator_name}"))

        self.add_item(Container(
            TextDisplay(f"<:timer:1517996239583576194> {title}"),
            TextDisplay(description),
            Separator(),
            *info_lines,
            accent_color=get_user_color_value(str(self.owner_id)),
        ))
        self.add_item(discord.ui.ActionRow(self.save_button))

    async def add_reminder(self, interaction: discord.Interaction):
        user_reminders = get_user_reminders(str(interaction.user.id))
        if len(user_reminders) >= MAX_USER_REMINDERS:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                "<:disapprove:1517452151012589662> You can have up to 7 reminders at once.",
                ephemeral=True,
            )
            return

        if any(
            existing.get("name") == self.reminder.get("name")
            and existing.get("when") == self.reminder.get("when")
            and existing.get("send") == self.reminder.get("send")
            and existing.get("description", "") == self.reminder.get("description", "")
            and existing.get("channel_id") == self.reminder.get("channel_id")
            for existing in user_reminders
        ):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> This reminder is already in your personal reminders.", ephemeral=True)
            return

        reminder_copy = self.reminder.copy()
        original_description = reminder_copy.get("description", "").strip()
        if original_description:
            reminder_copy["description"] = f"{original_description} (by {self.creator_name})"
        else:
            reminder_copy["description"] = f"by {self.creator_name}"

        user_reminders.append(reminder_copy)
        save_user_reminders(str(interaction.user.id), user_reminders)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Reminder added to your personal reminders.", ephemeral=True)


class ReminderEditLaunchView(TimeoutDisabledView):
    def __init__(self, user_id: int, settings_message: discord.Message, index: int, reminder: dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.settings_message = settings_message
        self.index = index
        self.reminder = reminder

        self.open_button = Button(label="Open edit modal", style=discord.ButtonStyle.primary, custom_id="open_reminder_edit")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_reminder_edit")

        self.open_button.callback = self.open_edit
        self.cancel_button.callback = self.cancel

        self.add_item(self.open_button)
        self.add_item(self.cancel_button)

    async def open_edit(self, interaction: discord.Interaction):
        modal = ReminderModal(self.user_id, self.settings_message, existing_index=self.index)
        modal.name_input.default = self.reminder.get("name", "")
        modal.description_input.default = self.reminder.get("description", "")
        reminder_when = self.reminder.get("when")
        if isinstance(reminder_when, int):
            try:
                                                                   
                offs = None
                try:
                    settings = load_user_settings()
                    entry = get_user_settings_entry(settings, str(self.user_id))
                    off = entry.get("timezone_offset")
                    offs = parse_utc_offset(off) if off else None
                except Exception:
                    offs = None
                utc_dt = _utc_naive(reminder_when)
                if offs is not None:
                    local_dt = utc_dt + offs
                else:
                    local_dt = utc_dt
                modal.time_input.default = f"{local_dt:%d/%m/%Y %H:%M}"
            except (OSError, OverflowError, ValueError):
                modal.time_input.default = str(reminder_when)
        else:
            modal.time_input.default = str(reminder_when)
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Reminder edit cancelled.", ephemeral=True)


class RemindersView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.reminders = get_user_reminders(str(user_id))
        self.build_components()

    def build_components(self):
        self.clear_items()
        reminder_lines = []
        for index, reminder in enumerate(self.reminders):
            reminder_lines.append(f"{index + 1}. {reminder.get('name', 'Reminder')} : {get_reminder_display(reminder)}")
            repeat_text = get_reminder_repeat_text(reminder)
            reminder_lines.append(f"Repeats: {repeat_text}")
            if reminder.get("description"):
                reminder_lines.append(reminder.get("description", ""))
            reminder_lines.append("")

        notice = "No reminders set yet." if not reminder_lines else "\n".join(fit_lines(reminder_lines))

        self.create_button = Button(label="Create", style=discord.ButtonStyle.success, custom_id="reminder_create")
        self.edit_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="reminder_edit", disabled=not bool(self.reminders))
        self.delete_button = Button(label="Delete", style=discord.ButtonStyle.danger, custom_id="reminder_delete", disabled=not bool(self.reminders)) 
        self.share_button = Button(label="Share", style=discord.ButtonStyle.success, custom_id="reminder_share", disabled=not bool(self.reminders))
        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="reminder_back")

        async def create_reminder(interaction: discord.Interaction):
            await interaction.response.send_modal(ReminderModal(self.user_id, interaction.message))        

        async def edit_reminder(interaction: discord.Interaction):
            await interaction.response.send_modal(ReminderActionModal(self.user_id, interaction.message, action="edit"))

        async def delete_reminder(interaction: discord.Interaction):
            await interaction.response.send_modal(ReminderActionModal(self.user_id, interaction.message, action="delete"))

        async def share_reminder(interaction: discord.Interaction):
            await interaction.response.send_modal(ReminderShareModal(self.user_id, interaction.message))

        async def back_to_menu(interaction: discord.Interaction):
            await interaction.response.edit_message(view=NotesMenuView(self.user_id))

        self.create_button.callback = create_reminder
        self.edit_button.callback = edit_reminder
        self.delete_button.callback = delete_reminder
        self.share_button.callback = share_reminder
        self.back_button.callback = back_to_menu

        self.add_item(Container(
            TextDisplay(get_reminders_header(self.user_id)),
            Separator(),
            TextDisplay(notice),
            accent_color=get_user_color_value(str(self.user_id)),
        ))
        self.add_item(discord.ui.ActionRow(self.create_button, self.edit_button, self.delete_button, self.share_button, self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This reminders panel is only for the original user.", ephemeral=True)
            return False
        return True


class ChecklistView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, page: int = 0):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.page = max(0, page)
        self.lists = get_user_lists(str(self.user_id))
        self.items = self.lists[0] if self.lists and isinstance(self.lists[0], list) else []
        self.build_components()

    def build_components(self):
        self.clear_items()
        item_lines = fit_lines([format_checklist_item(item, idx) for idx, item in enumerate(self.items)])
        if not item_lines:
            item_lines = ["No list items yet."]

        self.edit_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="checklist_edit")
        self.share_button = Button(label="Share", style=discord.ButtonStyle.success, custom_id="checklist_share", disabled=not bool(self.items))
        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="checklist_back")

        async def edit_list(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                view=ChecklistActionView(self.user_id, self.page, interaction.message),
                ephemeral=True,
            )

        async def share_list(interaction: discord.Interaction):
            share_text = "\n".join(item_lines)
            if interaction.guild and await run_automod_check_for_interaction(interaction, share_text, source_label="/share-list"):
                return
            owner = runtime.bot.get_user(self.user_id)
            owner_name = owner.display_name if owner else str(self.user_id)
            await interaction.response.defer(); await interaction.followup.send(
                view=SharedChecklistView(self.user_id, owner_name, item_lines),
                ephemeral=False,
            )

        async def back_to_menu(interaction: discord.Interaction):
            await interaction.response.edit_message(view=NotesMenuView(self.user_id))

        self.edit_button.callback = edit_list
        self.share_button.callback = share_list
        self.back_button.callback = back_to_menu

        header_text = f"<:list:1517497572770451567> Lists for {runtime.bot.get_user(self.user_id).display_name if runtime.bot.get_user(self.user_id) else str(self.user_id)}"
        self.add_item(Container(
            TextDisplay(header_text),
            Separator(),
            TextDisplay("\n".join(item_lines)),
            accent_color=get_user_color_value(str(self.user_id)),
        ))
        self.add_item(discord.ui.ActionRow(self.edit_button, self.share_button, self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This checklist panel is only for the original user.", ephemeral=True)
            return False
        return True


class ChecklistActionView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.page = page
        self.settings_message = settings_message
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="checklist_add")
        self.mark_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="checklist_edit")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="checklist_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="checklist_cancel")

        async def add_item(interaction: discord.Interaction):
            await interaction.response.send_modal(ChecklistAddModal(self.user_id, self.page, self.settings_message))

        async def mark_item(interaction: discord.Interaction):
            await interaction.response.send_modal(ChecklistMarkModal(self.user_id, self.page, self.settings_message))

        async def remove_item(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                view=ChecklistRemoveChoiceView(self.user_id, self.page, self.settings_message),
                ephemeral=True,
            )

        async def cancel(interaction: discord.Interaction):
            self.add_button.disabled = True
            self.mark_button.disabled = True
            self.remove_button.disabled = True
            self.cancel_button.disabled = True
            await interaction.response.edit_message(view=self)

        self.add_button.callback = add_item
        self.mark_button.callback = mark_item
        self.remove_button.callback = remove_item
        self.cancel_button.callback = cancel

        self.add_item(discord.ui.ActionRow(self.add_button, self.mark_button, self.remove_button, self.cancel_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This checklist menu is only for the original user.", ephemeral=True)
            return False
        return True


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


class ChecklistAddModal(Modal):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(title="Add checklist item")
        self.user_id = user_id
        self.page = page
        self.settings_message = settings_message
        self.content_input = TextInput(label="Item content", style=discord.TextStyle.long, required=True, max_length=200)
        self.color_input = TextInput(label="Mark color", placeholder="red, yellow, green, none", required=False, max_length=10)
        self.add_item(self.content_input)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        lists = get_user_lists(str(self.user_id))
        item_list = lists[0]
        if len(item_list) >= MAX_USER_LIST_ITEMS:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You already have the maximum of 30 items.", ephemeral=True)
            return
        color = self.color_input.value.strip().lower()
        if color == "":
            color = "none"
        if color not in {"red", "yellow", "green", "none"}:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Use red, yellow, green, or none.", ephemeral=True)
            return
        item_list.append({"content": self.content_input.value.strip(), "status": color})
        save_user_lists(str(self.user_id), lists)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Checklist item added.", ephemeral=True)
        await refresh_checklist_message(interaction, ChecklistView(self.user_id, self.page), self.settings_message)


class ChecklistMarkModal(Modal):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(title="Edit checklist item")
        self.user_id = user_id
        self.page = page
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item ID or name to edit", required=True, max_length=100)
        self.content_input = TextInput(label="New content", style=discord.TextStyle.long, required=False, max_length=200)
        self.color_input = TextInput(label="Mark color", placeholder="red, yellow, green, remove", required=False, max_length=10)
        self.add_item(self.item_input)
        self.add_item(self.content_input)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        lists = get_user_lists(str(self.user_id))
        item_list = lists[0]
        index = find_checklist_item_index(item_list, self.item_input.value)
        if index is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Item not found.", ephemeral=True)
            return
        new_content = self.content_input.value.strip()
        new_color = self.color_input.value.strip().lower()
        if not new_content and not new_color:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Provide new content, a mark color, or both.", ephemeral=True)
            return
        if new_content:
            item_list[index]["content"] = new_content
        if new_color:
            if new_color not in {"red", "yellow", "green", "remove"}:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Use red, yellow, green, or remove.", ephemeral=True)
                return
            item_list[index]["status"] = "none" if new_color == "remove" else new_color
        save_user_lists(str(self.user_id), lists)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Checklist item updated.", ephemeral=True)
        await refresh_checklist_message(interaction, ChecklistView(self.user_id, self.page), self.settings_message)


class ChecklistRemoveChoiceView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.page = page
        self.settings_message = settings_message
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="checklist_remove_single")
        self.clear_button = Button(label="Clear all", style=discord.ButtonStyle.secondary, custom_id="checklist_clear_all")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="checklist_remove_cancel")

        async def remove_single(interaction: discord.Interaction):
            await interaction.response.send_modal(ChecklistRemoveModal(self.user_id, self.page, self.settings_message))

        async def clear_all(interaction: discord.Interaction):
            lists = get_user_lists(str(self.user_id))
            lists[0] = []
            save_user_lists(str(self.user_id), lists)
            await refresh_checklist_message(interaction, ChecklistView(self.user_id, self.page), self.settings_message)
            self.remove_button.disabled = True
            self.clear_button.disabled = True
            self.cancel_button.disabled = True
            await interaction.response.edit_message(view=self)

        async def cancel(interaction: discord.Interaction):
            self.remove_button.disabled = True
            self.clear_button.disabled = True
            self.cancel_button.disabled = True
            await interaction.response.edit_message(view=self)

        self.remove_button.callback = remove_single
        self.clear_button.callback = clear_all
        self.cancel_button.callback = cancel
        self.add_item(discord.ui.ActionRow(self.remove_button, self.clear_button, self.cancel_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This checklist action is only for the original user.", ephemeral=True)
            return False
        return True


class ChecklistRemoveModal(Modal):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(title="Remove checklist item")
        self.user_id = user_id
        self.page = page
        self.settings_message = settings_message
        self.item_input = TextInput(label="Item ID or name to remove", required=True, max_length=100)
        self.add_item(self.item_input)

    async def on_submit(self, interaction: discord.Interaction):
        lists = get_user_lists(str(self.user_id))
        item_list = lists[0]
        index = find_checklist_item_index(item_list, self.item_input.value)
        if index is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Item not found.", ephemeral=True)
            return
        item_list.pop(index)
        save_user_lists(str(self.user_id), lists)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:trash:1517497581058527404> Checklist item removed.", ephemeral=True)
        await refresh_checklist_message(interaction, ChecklistView(self.user_id, self.page), self.settings_message)


class PlannerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # bot.py loads cogs before logging in, so the loop starts on ready (or right away on a reload).
    async def cog_load(self):
        if self.bot.is_ready():
            self.start_tasks()

    async def cog_unload(self):
        self.reminders_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        self.start_tasks()

    def start_tasks(self) -> None:
        if not self.reminders_loop.is_running():
            self.reminders_loop.start()

    @tasks.loop(seconds=10)
    async def reminders_loop(self):
        await self.check_reminders()

    @reminders_loop.before_loop
    async def before_reminders_loop(self):
        await self.bot.wait_until_ready()

    async def check_reminders(self) -> None:
        try:
            settings = load_user_settings()
            if not settings:
                return
            now_ts = int(datetime.now(timezone.utc).timestamp())
            users = settings.get('users')
            if not isinstance(users, dict):
                return
            # No await between loading and saving, so edits made meanwhile can't be lost.
            reminders_changed = False
            for user_id, user_settings in list(users.items()):
                reminders = user_settings.get('reminders') if isinstance(user_settings, dict) else None
                if not isinstance(reminders, list):
                    continue

                remaining_reminders = []
                for reminder in reminders:
                    if not isinstance(reminder, dict):
                        continue
                    when = reminder.get('when')
                    if isinstance(when, int) and when <= now_ts:
                        # Deliver a copy: a repeating reminder is moved to its next time below.
                        asyncio.get_running_loop().create_task(deliver_reminder(str(user_id), dict(reminder)))
                        reminders_changed = True
                        repeat = reminder.get('repeat')
                        if isinstance(repeat, int) and repeat > 0:
                            next_when = when + max(repeat, MIN_REPEAT_SECONDS)
                            while next_when <= now_ts:
                                next_when += max(repeat, MIN_REPEAT_SECONDS)
                            reminder['when'] = int(next_when)
                            remaining_reminders.append(reminder)
                    else:
                        remaining_reminders.append(reminder)

                if len(remaining_reminders) != len(reminders):
                    user_settings['reminders'] = remaining_reminders

            if reminders_changed:
                save_user_settings(settings)
        except Exception as error:
            print(f"[planner] reminder check failed: {type(error).__name__}: {error}")

    @app_commands.command(name='notes-lists-reminders', description='Manage your notes, checklists, and reminders')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def notes_lists_reminders(self, interaction: discord.Interaction):
        view = NotesMenuView(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PlannerCog(bot))
