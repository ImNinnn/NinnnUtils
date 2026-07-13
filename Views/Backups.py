import math
import zipfile
from pathlib import Path

import discord
from discord.ui import *

from Shared.Backups import get_backup_files, format_backup_entry, create_backup
from main import BASE_DIR, OWN_PASSWORD


class BackupListView(LayoutView):
    def __init__(self, user_id: int, page: int = 1):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.page = page
        self.message: discord.Message | None = None
        self.backup_files = get_backup_files()
        self.build_components()

    def build_components(self):
        self.clear_items()
        total_backups = len(self.backup_files)
        total_pages = max(1, math.ceil(total_backups / 5))
        current_page = min(max(1, self.page), total_pages)
        start_index = (current_page - 1) * 5
        page_backups = self.backup_files[start_index:start_index + 5]

        title = "Backup files"
        description = f"Page {current_page}/{total_pages} · {total_backups} backup(s) available."
        container_items = [
            TextDisplay(f"<:floppy_disk:1517577943290188033> **{title}**"),
            TextDisplay(description),
            Separator(),
        ]

        if not page_backups:
            container_items.append(Section("No backups found. Run a backup or wait for the scheduler to create one."))
        else:
            for index, backup_path in enumerate(page_backups, start=start_index + 1):
                file_label = f"{index}. {backup_path.name}"
                backup_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id=f"backup_edit_{current_page}_{index}")

                async def backup_callback(interaction: discord.Interaction, backup_file=backup_path):
                    await self.open_backup_actions(interaction, backup_file)

                backup_button.callback = backup_callback
                container_items.append(Section(f"{file_label}\n{format_backup_entry(backup_path)}", accessory=backup_button))

        self.add_item(Container(*container_items, accent_color=discord.Color.blurple()))

        prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="backup_prev")
        next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="backup_next")
        create_button = Button(label="Create Backup", style=discord.ButtonStyle.success, custom_id="backup_create")
        close_button = Button(label="Close", style=discord.ButtonStyle.danger, custom_id="backup_close")
        prev_button.callback = self.open_previous_page
        next_button.callback = self.open_next_page
        create_button.callback = self.create_backup
        close_button.callback = self.close_view
        prev_button.disabled = current_page <= 1
        next_button.disabled = current_page >= total_pages

        self.add_item(discord.ui.ActionRow(prev_button, next_button, create_button, close_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This backup panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def open_previous_page(self, interaction: discord.Interaction):
        new_view = BackupListView(self.user_id, page=self.page - 1)
        new_view.message = interaction.message
        await interaction.response.edit_message(view=new_view)

    async def open_next_page(self, interaction: discord.Interaction):
        new_view = BackupListView(self.user_id, page=self.page + 1)
        new_view.message = interaction.message
        await interaction.response.edit_message(view=new_view)

    async def create_backup(self, interaction: discord.Interaction):
        backup_path = create_backup(BASE_DIR)
        await interaction.response.send_message(f"<:approve:1517452125687513158> Created backup `{backup_path.name}`.", ephemeral=True)
        if self.message is None and interaction.message is not None:
            self.message = interaction.message
        if self.message:
            refreshed_view = BackupListView(self.user_id, page=self.page)
            refreshed_view.message = self.message
            await self.message.edit(view=refreshed_view)

    async def close_view(self, interaction: discord.Interaction):
        if interaction.message:
            await interaction.message.delete()
        else:
            await interaction.response.send_message("Backup list closed.", ephemeral=True)

    async def open_backup_actions(self, interaction: discord.Interaction, backup_file: Path):
        await interaction.response.send_message(
            f"What would you like to do with `{backup_file.name}`?",
            view=BackupActionView(self.user_id, backup_file, self),
            ephemeral=True,
        )


class BackupActionView(discord.ui.View):
    def __init__(self, user_id: int, backup_file: Path, list_view: BackupListView):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.backup_file = backup_file
        self.list_view = list_view
        self.load_button = Button(label="Load", style=discord.ButtonStyle.success, custom_id="backup_action_load")
        self.delete_button = Button(label="Delete", style=discord.ButtonStyle.danger, custom_id="backup_action_delete")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="backup_action_cancel")
        self.load_button.callback = self.load_callback
        self.delete_button.callback = self.delete_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.load_button)
        self.add_item(self.delete_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def load_callback(self, interaction: discord.Interaction):
        modal = BackupPasswordModal(self.user_id, self.backup_file, "load", self.list_view)
        await interaction.response.send_modal(modal)

    async def delete_callback(self, interaction: discord.Interaction):
        modal = BackupPasswordModal(self.user_id, self.backup_file, "delete", self.list_view)
        await interaction.response.send_modal(modal)

    async def cancel_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Backup action cancelled.", view=None)


class BackupPasswordModal(Modal):
    def __init__(self, user_id: int, backup_file: Path, action: str, list_view: BackupListView):
        super().__init__(title=f"Confirm {action.title()} Backup")
        self.user_id = user_id
        self.backup_file = backup_file
        self.action = action
        self.list_view = list_view
        self.password_input = TextInput(label="Owner password", style=discord.TextStyle.short, placeholder="Enter OWN_PASSWORD from .env", required=True, min_length=1)
        self.add_item(self.password_input)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("<:disapprove:1517452151012589662> This password prompt is only for the original user.", ephemeral=True)
            return

        if not OWN_PASSWORD:
            await interaction.response.send_message("<:disapprove:1517452151012589662> OWN_PASSWORD is not configured in .env.", ephemeral=True)
            return

        if self.password_input.value != OWN_PASSWORD:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Incorrect password.", ephemeral=True)
            return

        if self.action == "load":
            await self.perform_load(interaction)
        elif self.action == "delete":
            await self.perform_delete(interaction)
        else:
            await interaction.response.send_message("<:disapprove:1517452151012589662> Unknown action.", ephemeral=True)

    async def perform_load(self, interaction: discord.Interaction):
        if not self.backup_file.exists():
            await interaction.response.send_message("<:disapprove:1517452151012589662> Backup file no longer exists.", ephemeral=True)
            return

        try:
            backup_before_restore = create_backup(BASE_DIR)
            with zipfile.ZipFile(self.backup_file, 'r') as zf:
                zf.extractall(path=BASE_DIR)
            await interaction.response.send_message(
                f"<:approve:1517452125687513158> Loaded backup `{self.backup_file.name}` and created current backup `{backup_before_restore.name}`.",
                ephemeral=True,
            )
            if self.list_view.message:
                await self.list_view.message.edit(view=BackupListView(self.user_id, page=self.list_view.page))
        except Exception as e:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> Failed to load backup: {e}", ephemeral=True)

    async def perform_delete(self, interaction: discord.Interaction):
        if not self.backup_file.exists():
            await interaction.response.send_message("<:disapprove:1517452151012589662> Backup file no longer exists.", ephemeral=True)
            return

        try:
            self.backup_file.unlink()
            await interaction.response.send_message(
                f"<:trash:1517497581058527404> Deleted backup `{self.backup_file.name}`.",
                ephemeral=True,
            )
            if self.list_view.message:
                await self.list_view.message.edit(view=BackupListView(self.user_id, page=self.list_view.page))
        except Exception as e:
            await interaction.response.send_message(f"<:disapprove:1517452151012589662> Failed to delete backup: {e}", ephemeral=True)
