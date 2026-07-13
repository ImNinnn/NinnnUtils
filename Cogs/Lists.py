import uuid
from datetime import datetime, timezone

from discord import app_commands
from discord.ext.commands import Cog, hybrid_command, Context
from discord.ext import tasks

from Shared.User import load_user_settings, save_user_settings
from Views.Lists import ReminderNotificationView, NotesMenuView
from main import PENDING_POSTPONE_REMINDERS


async def setup(bot):
    bot.add_cog(Lists(bot))

class Lists(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def deliver_reminder(self, user_id: str, reminder: dict):
        user = self.bot.get_user(int(user_id)) if user_id.isdigit() else None
        if not user:
            try:
                user = await self.bot.fetch_user(int(user_id))
            except Exception:
                user = None

        postpone_id = uuid.uuid4().hex
        PENDING_POSTPONE_REMINDERS[postpone_id] = {
            "user_id": str(user_id),
            "reminder": reminder,
        }

        send_mode = reminder.get("send", "dm")
        if send_mode in {"dm", "both"} and user:
            try:
                await user.send(view=ReminderNotificationView(str(user_id), postpone_id, reminder, mention_user=False))
            except Exception:
                pass

        if send_mode in {"channel", "both"}:
            channel_id = reminder.get("channel_id")
            if channel_id:
                channel = self.bot.get_channel(int(channel_id)) if isinstance(channel_id, int) else None
                if channel:
                    try:
                        await channel.send(
                            view=ReminderNotificationView(str(user_id), postpone_id, reminder, mention_user=True))
                    except Exception:
                        pass

    @tasks.loop(minutes=1)
    async def reminder_loop(self):
        settings = load_user_settings()
        if not settings:
            return

        now = int(datetime.now(timezone.utc).timestamp())
        changed = False

        users = settings.get("users")
        if not isinstance(users, dict):
            return

        for user_id, user_settings in list(users.items()):
            reminders = user_settings.get("reminders")
            if not isinstance(reminders, list):
                continue

            remaining_reminders = []
            for reminder in reminders:
                if not isinstance(reminder, dict):
                    continue
                when = reminder.get("when")
                if isinstance(when, int) and when <= now:
                    await self.deliver_reminder(user_id, reminder)
                    changed = True
                else:
                    remaining_reminders.append(reminder)

            if len(remaining_reminders) != len(reminders):
                user_settings["reminders"] = remaining_reminders

        if changed:
            save_user_settings(settings)

    @reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

    def get_list_title(self, list_index: int) -> str:
        return f"List {list_index + 1}" if 0 <= list_index < 3 else "List"

    def get_list_header(self, user_id: int, list_index: int) -> str:
        return f"<:list:1517497572770451567> Lists for {self.bot.get_user(user_id).display_name if self.bot.get_user(user_id) else str(user_id)}"

    def get_notes_header(self, user_id: int) -> str:
        user = self.bot.get_user(user_id)
        return f"<:edit:1517497568421085256> Notes for {user.display_name if user else str(user_id)}"

    def get_reminders_header(self, user_id: int) -> str:
        user = self.bot.get_user(user_id)
        return f"<:timer:1517996239583576194> Reminders for {user.display_name if user else str(user_id)}"

    @hybrid_command(name="lists", description="Manage your notes, checklists, and reminders")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def notes(self, ctx: Context):
        view = NotesMenuView(ctx.author.id)
        await ctx.send(view=view, ephemeral=True)
