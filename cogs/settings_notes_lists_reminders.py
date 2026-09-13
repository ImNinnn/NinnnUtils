"""Settings, notes, list, and reminder management commands."""

import discord
from discord import app_commands
from discord.ext import commands

import helper as main


class SettingsNotesListsRemindersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='settings', description='Open a quick settings menu for your personal and guild preferences')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def settings(self, interaction: discord.Interaction):
        view = main.SettingsMenuView(
            interaction.user.id,
            interaction.user.display_name,
            main.get_user_color_value(str(interaction.user.id)),
        )
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(view=view, ephemeral=True)

    @app_commands.command(name='notes-lists-reminders', description='Manage your notes, checklists, and reminders')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def notes_lists_reminders(self, interaction: discord.Interaction):
        view = main.NotesMenuView(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(SettingsNotesListsRemindersCog(bot))
