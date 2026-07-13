from datetime import datetime, timezone, UTC

import discord
from discord.ui import Modal, TextInput, LayoutView, Button, Section, Separator, TextDisplay, Container

from LowerLeveled.messages import normalize_send_mode, safe_send
from LowerLeveled.timestamp import parse_reminder_time
from Shared.Lists import get_reminder_message_text, get_reminder_display, find_reminder_index, get_reminder_destination, \
    format_checklist_item, refresh_checklist_message, find_checklist_item_index
from Shared.User import get_user_reminders, save_user_reminders, get_user_color_value, get_user_notes, save_user_notes, \
    can_add_user_reminder, get_user_lists, save_user_lists
from Views.Settings import ChannelSelectorView
from main import PENDING_POSTPONE_REMINDERS, MAX_USER_REMINDERS, MAX_USER_NOTES, CHECKLIST_PAGE_SIZE, \
    MAX_USER_LIST_ITEMS


class ReminderPostponeModal(Modal):
    def __init__(self, user_id: str, postpone_id: str, current_time: int):
        super().__init__(title="Postpone Reminder")
        self.user_id = user_id
        self.postpone_id = postpone_id
        self.time_input = TextInput(
            label="New reminder time",
            placeholder="in 1d 30m 10s or at yy/mm/dd hh:mm",
            required=True,
            default=f"at {datetime.fromtimestamp(current_time, UTC):%y/%m/%d %H:%M}",
        )
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction):
        data = PENDING_POSTPONE_REMINDERS.get(self.postpone_id)
        if not data or str(interaction.user.id) != data["user_id"]:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This postpone link is no longer valid.", ephemeral=True)
            return

        reminder = data["reminder"]
        new_time = parse_reminder_time(self.time_input.value)
        if new_time is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Invalid reminder time. Use in 1h or at 24/12/26 18:00.", ephemeral=True)
            return

        new_reminder = {
            "name": reminder.get("name", "Reminder"),
            "description": reminder.get("description", ""),
            "when": new_time,
            "send": reminder.get("send", "dm"),
        }
        if reminder.get("channel_id"):
            new_reminder["channel_id"] = reminder["channel_id"]

        reminders = get_user_reminders(str(self.user_id))
        if len(reminders) >= MAX_USER_REMINDERS:
            await interaction.response.send_message(
                "<:disapprove:1517452151012589662> You can have up to 7 reminders at once.",
                ephemeral=True,
            )
            return

        reminders.append(new_reminder)
        save_user_reminders(str(self.user_id), reminders)
        PENDING_POSTPONE_REMINDERS.pop(self.postpone_id, None)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Reminder postponed to <t:{new_time}:F>.", ephemeral=True)


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
        ]
        if self.mention_user:
            details.append(TextDisplay(f"<@{self.user_id}>"))

        container = Container(*details, accent_color=get_user_color_value(str(self.user_id)))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("<:disapprove:1517452151012589662> Only the reminder owner can postpone this reminder.", ephemeral=True)
            return False
        return True

    async def open_postpone(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ReminderPostponeModal(self.user_id, self.postpone_id, self.reminder.get("when", int(datetime.now(timezone.utc).timestamp()))))

class NotesMenuView(LayoutView):
    def __init__(self, user_id: int, bot):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.bot = bot
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
        user = self.bot.get_user(self.user_id)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This menu is only for the original user.", ephemeral=True)
            return False
        return True


class NotesView(LayoutView):
    def __init__(self, user_id: int, note_index: int = 0, bot = None):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.note_index = max(0, min(note_index, MAX_USER_NOTES - 1))
        self.notes = get_user_notes(str(self.user_id))
        self.bot = bot
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
            owner = self.bot.get_user(self.user_id)
            owner_name = owner.display_name if owner else str(self.user_id)
            await interaction.response.send_message(
                view=SharedNoteView(self.user_id, owner_name, note_text),
                ephemeral=False,
            )

        async def cycle_note(interaction: discord.Interaction):
            new_index = (self.note_index + 1) % MAX_USER_NOTES
            await interaction.response.edit_message(view=NotesView(self.user_id, new_index))

        async def back_to_menu(interaction: discord.Interaction):
            await interaction.response.edit_message(view=NotesMenuView(self.user_id, self.bot))

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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This notes panel is only for the original user.", ephemeral=True)
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


class SharedNoteView(LayoutView):
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

class SharedChecklistView(LayoutView):
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
        self.time_input = TextInput(label="Reminder time", placeholder="in 1d 30m 10s or at yy/mm/dd hh:mm", required=True)
        self.send_input = TextInput(label="Send in channel/dm/both", placeholder="dm, channel, or both", required=True)
        self.add_item(self.name_input)
        self.add_item(self.description_input)
        self.add_item(self.time_input)
        self.add_item(self.send_input)

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip() or "Reminder"
        description = self.description_input.value.strip()
        when = parse_reminder_time(self.time_input.value)
        send = normalize_send_mode(self.send_input.value)

        if when is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Invalid reminder time. Use in 1h or at 24/12/26 18:00.", ephemeral=True)
            return

        reminder = {
            "name": name,
            "description": description,
            "when": when,
            "send": send,
        }

        if self.existing_index is None and not can_add_user_reminder(str(self.user_id)):
            await interaction.response.send_message(
                "<:disapprove:1517452151012589662> You can have up to 7 reminders at once.",
                ephemeral=True,
            )
            return

        if send in {"channel", "both"}:
            guild = interaction.guild
            if not guild:
                await interaction.response.send_message("<:disapprove:1517452151012589662> Channel reminders require server context.", ephemeral=True)
                return

            await interaction.response.send_message(
                "Select the channel for this reminder:",
                view=ChannelSelectorView(self.user_id, guild, "Select reminder channel", self.on_channel_selected, self.settings_message),
                ephemeral=True,
            )
            self.pending_reminder = reminder
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

    async def on_channel_selected(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        reminder = self.pending_reminder
        reminder["channel_id"] = channel.id
        reminders = get_user_reminders(str(self.user_id))
        if self.existing_index is None and len(reminders) >= MAX_USER_REMINDERS:
            await safe_send(
                interaction,
                "<:disapprove:1517452151012589662> You can have up to 7 reminders at once.",
                ephemeral=True,
            )
            return

        if self.existing_index is None:
            reminders.append(reminder)
        else:
            if 0 <= self.existing_index < len(reminders):
                reminders[self.existing_index] = reminder
        save_user_reminders(str(self.user_id), reminders)
        try:
            await interaction.response.edit_message(view=RemindersView(self.user_id))
        except Exception:
            try:
                await self.settings_message.edit(view=RemindersView(self.user_id))
            except Exception:
                pass
        await safe_send(interaction, f"<:approve:1517452125687513158> Reminder saved for <t:{reminder['when']}:F>.", ephemeral=True)


class RemindersView(LayoutView):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.reminders = get_user_reminders(str(user_id))
        self.build_components()


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
            await interaction.response.send_message("<:disapprove:1517452151012589662> You have no reminders yet.", ephemeral=True)
            return

        index = find_reminder_index(reminders, self.reminder_input.value)
        if index is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Reminder not found. Use number or exact name.", ephemeral=True)
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
        await interaction.response.send_message(
            "Reminder found. Click below to continue editing.",
            view=ReminderEditLaunchView(self.user_id, self.settings_message, index, reminder),
            ephemeral=True,
        )


class ReminderShareModal(Modal):
    def __init__(self, user_id: int, settings_message: discord.Message, bot):
        super().__init__(title="Share reminder")
        self.user_id = user_id
        self.settings_message = settings_message
        self.reminder_input = TextInput(label="Reminder number or name", placeholder="1 or reminder name", required=True, max_length=100)
        self.bot = bot
        self.add_item(self.reminder_input)

    async def on_submit(self, interaction: discord.Interaction):
        reminders = get_user_reminders(str(self.user_id))
        if not reminders:
            await interaction.response.send_message("<:disapprove:1517452151012589662> You have no reminders yet.", ephemeral=True)
            return

        index = find_reminder_index(reminders, self.reminder_input.value)
        if index is None:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Reminder not found. Use number or exact name.", ephemeral=True)
            return

        reminder = reminders[index]
        destination = get_reminder_destination(reminder, interaction.guild)
        reminder_text = get_reminder_message_text(reminder)
        reminder_name = reminder.get("name", "Reminder")

        owner = self.bot.get_user(self.user_id)
        creator_name = owner.display_name if owner else str(self.user_id)
        await interaction.response.send_message(
            view=SharedReminderView(self.user_id, creator_name, reminder),
            ephemeral=False,
        )


class SharedReminderView(LayoutView):
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

        self.add_item(Container(
            TextDisplay(f"<:timer:1517996239583576194> {title}"),
            TextDisplay(description),
            Separator(),
            TextDisplay(f"When: {when}"),
            TextDisplay(f"Sent in: {destination}"),
            TextDisplay(f"Reminder creator: {self.creator_name}"),
            accent_color=get_user_color_value(str(self.owner_id)),
        ))
        self.add_item(discord.ui.ActionRow(self.save_button))

    async def add_reminder(self, interaction: discord.Interaction):
        user_reminders = get_user_reminders(str(interaction.user.id))
        if len(user_reminders) >= MAX_USER_REMINDERS:
            await interaction.response.send_message(
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
            await interaction.response.send_message("<:approve:1517452125687513158> This reminder is already in your personal reminders.", ephemeral=True)
            return

        reminder_copy = self.reminder.copy()
        original_description = reminder_copy.get("description", "").strip()
        if original_description:
            reminder_copy["description"] = f"{original_description} (by {self.creator_name})"
        else:
            reminder_copy["description"] = f"by {self.creator_name}"

        user_reminders.append(reminder_copy)
        save_user_reminders(str(interaction.user.id), user_reminders)
        await interaction.response.send_message("<:approve:1517452125687513158> Reminder added to your personal reminders.", ephemeral=True)


class ReminderEditLaunchView(discord.ui.View):
    def __init__(self, user_id: int, settings_message: discord.Message, index: int, reminder: dict):
        super().__init__(timeout=120)
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
                modal.time_input.default = f"at {datetime.fromtimestamp(reminder_when, UTC):%y/%m/%d %H:%M}"
            except (OSError, OverflowError, ValueError):
                modal.time_input.default = str(reminder_when)
        else:
            modal.time_input.default = str(reminder_when)
        modal.send_input.default = self.reminder.get("send", "dm")
        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.send_message("Reminder edit cancelled.", ephemeral=True)


class RemindersView(LayoutView):
    def __init__(self, user_id: int, bot):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.reminders = get_user_reminders(str(user_id))
        self.bot = bot
        self.build_components()

    def build_components(self):
        self.clear_items()
        reminder_lines = []
        for index, reminder in enumerate(self.reminders):
            destination = get_reminder_destination(reminder, None)
            reminder_lines.append(f"{index + 1}. {reminder.get('name', 'Reminder')} : {get_reminder_display(reminder)} [{destination}]")
            if reminder.get("description"):
                reminder_lines.append(reminder.get("description", ""))
            reminder_lines.append("")

        notice = "No reminders set yet." if not reminder_lines else "\n".join(reminder_lines)

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
            await interaction.response.send_modal(ReminderShareModal(self.user_id, interaction.message, self.bot))

        async def back_to_menu(interaction: discord.Interaction):
            await interaction.response.edit_message(view=NotesMenuView(self.user_id, self.bot))

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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This reminders panel is only for the original user.", ephemeral=True)
            return False
        return True


class ChecklistView(LayoutView):
    def __init__(self, user_id: int, page: int = 0, bot = None):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.page = max(0, page)
        self.lists = get_user_lists(str(self.user_id))
        self.items = self.lists[0]
        self.bot = bot
        self.build_components()

    def build_components(self):
        self.clear_items()
        page_count = (len(self.items) + CHECKLIST_PAGE_SIZE - 1) // CHECKLIST_PAGE_SIZE
        self.page = min(self.page, max(page_count - 1, 0))
        page_items = self.items[self.page * CHECKLIST_PAGE_SIZE : (self.page + 1) * CHECKLIST_PAGE_SIZE]

        item_lines = [format_checklist_item(item, self.page * CHECKLIST_PAGE_SIZE + idx) for idx, item in enumerate(page_items)]
        if not item_lines:
            item_lines = ["No list items yet."]

        self.edit_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="checklist_edit")
        self.share_button = Button(label="Share", style=discord.ButtonStyle.success, custom_id="checklist_share", disabled=not bool(self.items))
        self.cycle_button = Button(label="Next page", style=discord.ButtonStyle.secondary, custom_id="checklist_cycle", disabled=self.page >= page_count - 1)
        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="checklist_back")

        async def edit_list(interaction: discord.Interaction):
            await interaction.response.send_message(
                view=ChecklistActionView(self.user_id, self.page, interaction.message),
                ephemeral=True,
            )

        async def share_list(interaction: discord.Interaction):
            owner = self.bot.get_user(self.user_id)
            owner_name = owner.display_name if owner else str(self.user_id)
            await interaction.response.send_message(
                view=SharedChecklistView(self.user_id, owner_name, item_lines),
                ephemeral=False,
            )

        async def cycle_page(interaction: discord.Interaction):
            await interaction.response.edit_message(view=ChecklistView(self.user_id, self.page + 1))

        async def back_to_menu(interaction: discord.Interaction):
            await interaction.response.edit_message(view=NotesMenuView(self.user_id, self.bot))

        self.edit_button.callback = edit_list
        self.share_button.callback = share_list
        self.cycle_button.callback = cycle_page
        self.back_button.callback = back_to_menu

        header_text = f"<:list:1517497572770451567> Lists for {self.bot.get_user(self.user_id).display_name if self.bot.get_user(self.user_id) else str(self.user_id)}"
        self.add_item(Container(
            TextDisplay(header_text),
            Separator(),
            TextDisplay("\n".join(item_lines)),
            accent_color=get_user_color_value(str(self.user_id)),
        ))
        self.add_item(discord.ui.ActionRow(self.edit_button, self.share_button, self.cycle_button, self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This checklist panel is only for the original user.", ephemeral=True)
            return False
        return True

class ChecklistActionView(LayoutView):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(timeout=180)
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
            await interaction.response.send_message(
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This checklist menu is only for the original user.", ephemeral=True)
            return False
        return True

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
            await interaction.response.send_message("<:disapprove:1517452151012589662> You already have the maximum of 30 items.", ephemeral=True)
            return
        color = self.color_input.value.strip().lower()
        if color == "":
            color = "none"
        if color not in {"red", "yellow", "green", "none"}:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Use red, yellow, green, or none.", ephemeral=True)
            return
        item_list.append({"content": self.content_input.value.strip(), "status": color})
        save_user_lists(str(self.user_id), lists)
        await interaction.response.send_message("<:approve:1517452125687513158> Checklist item added.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Item not found.", ephemeral=True)
            return
        new_content = self.content_input.value.strip()
        new_color = self.color_input.value.strip().lower()
        if not new_content and not new_color:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Provide new content, a mark color, or both.", ephemeral=True)
            return
        if new_content:
            item_list[index]["content"] = new_content
        if new_color:
            if new_color not in {"red", "yellow", "green", "remove"}:
                await interaction.response.send_message("<:disapprove:1517452151012589662> Use red, yellow, green, or remove.", ephemeral=True)
                return
            item_list[index]["status"] = "none" if new_color == "remove" else new_color
        save_user_lists(str(self.user_id), lists)
        await interaction.response.send_message("<:approve:1517452125687513158> Checklist item updated.", ephemeral=True)
        await refresh_checklist_message(interaction, ChecklistView(self.user_id, self.page), self.settings_message)


class ChecklistRemoveChoiceView(LayoutView):
    def __init__(self, user_id: int, page: int, settings_message: discord.Message):
        super().__init__(timeout=180)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> This checklist action is only for the original user.", ephemeral=True)
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
            await interaction.response.send_message("<:disapprove:1517452151012589662> Item not found.", ephemeral=True)
            return
        item_list.pop(index)
        save_user_lists(str(self.user_id), lists)
        await interaction.response.send_message("<:trash:1517497581058527404> Checklist item removed.", ephemeral=True)
        await refresh_checklist_message(interaction, ChecklistView(self.user_id, self.page), self.settings_message)
