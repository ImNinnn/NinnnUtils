"""Tickets: the "Open Ticket" message, private ticket threads and their Close/Resolve/Delete buttons.

The ticket settings (channel, style, reasons, manager role) are edited in /settings.
"""

import discord
from discord.ext import commands
from discord.ui import Button, View

import save
from utils import runtime


# ---------------------------------------------------------------- stored state

def get_active_ticket_thread_entry(guild_id: str, user_id: int) -> dict | None:
    guild_config, _ = save.get_guild_config(guild_id)
    entry = guild_config.get("ticket_active_threads", {}).get(str(user_id))
    if isinstance(entry, dict):
        return entry
    if isinstance(entry, (int, str)):
        try:
            return {"thread_id": int(entry)}
        except (TypeError, ValueError):
            return None
    return None


def get_active_ticket_thread_id(guild_id: str, user_id: int) -> int | None:
    entry = get_active_ticket_thread_entry(guild_id, user_id)
    return entry.get("thread_id") if entry else None


def set_active_ticket_thread_entry(guild_id: str, user_id: int, thread_id: int | None, control_message_id: int | None = None) -> None:
    guild_config, data = save.get_guild_config(guild_id)
    active_tickets = guild_config.setdefault("ticket_active_threads", {})
    key = str(user_id)
    if thread_id is None:
        active_tickets.pop(key, None)
    else:
        entry = active_tickets.get(key)
        if isinstance(entry, dict):
            entry["thread_id"] = thread_id
            if control_message_id is not None:
                entry["control_message_id"] = control_message_id
        else:
            active_tickets[key] = {"thread_id": thread_id, "control_message_id": control_message_id}
    save.save_guild_data(data)


def clear_active_ticket(guild_id: str, user_id: int) -> None:
    set_active_ticket_thread_entry(guild_id, user_id, None)


# ---------------------------------------------------------------- announce message

def build_ticket_announce_embed(guild_id: str) -> discord.Embed:
    guild_config, _ = save.get_guild_config(guild_id)
    embed = discord.Embed(
        title="<:ticket:1533568847725203609> Open a ticket",
        description="Click the button below to create a support ticket." if guild_config.get("ticket_style", "button") == "button" else "Select a reason to open a ticket.",
        color=discord.Color.blurple(),
    )
    if guild_config.get("ticket_style") == "list":
        reasons = guild_config.get("ticket_reasons", []) or []
        if reasons:
            embed.add_field(name="Ticket reasons:", value="\n".join(f"- {reason}" for reason in reasons[:10])[:1024], inline=False)
    return embed


def build_ticket_create_view(guild_id: str) -> discord.ui.View:
    guild_config, _ = save.get_guild_config(guild_id)
    if guild_config.get("ticket_style") == "list" and guild_config.get("ticket_reasons"):
        return TicketReasonSelectMessageView(guild_id)
    return TicketCreateButtonView(guild_id)


async def refresh_ticket_announce_message(guild_id: str) -> None:
    bot = runtime.bot
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return
    guild_config, data = save.get_guild_config(guild_id)
    channel_id = guild_config.get("ticket_channel_id")
    if not channel_id:
        guild_config["ticket_announce_message_id"] = None
        save.save_guild_data(data)
        return
    channel = guild.get_channel(int(channel_id))
    if not channel or not hasattr(channel, "send"):
        return
    embed = build_ticket_announce_embed(guild_id)
    view = build_ticket_create_view(guild_id)
    message_id = guild_config.get("ticket_announce_message_id")
    try:
        if message_id:
            message = await channel.fetch_message(int(message_id))
            await message.edit(embed=embed, view=view)
            try:
                bot.add_view(view, message_id=message.id)
            except Exception:
                pass
            return
    except (discord.NotFound, discord.HTTPException, ValueError):
        pass
    try:
        message = await channel.send(embed=embed, view=view)
        # Reload: the settings panel may have saved other changes while the message was sent.
        guild_config, data = save.get_guild_config(guild_id)
        guild_config["ticket_announce_message_id"] = message.id
        save.save_guild_data(data)
        try:
            bot.add_view(view, message_id=message.id)
        except Exception:
            pass
    except (discord.Forbidden, discord.HTTPException):
        pass


class TicketCreateButtonView(View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.create_button = Button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="ticket_create_button")
        self.create_button.callback = self.on_create
        self.add_item(self.create_button)

    async def on_create(self, interaction: discord.Interaction):
        await create_ticket_for_user(interaction, self.guild_id)


class TicketReasonSelectMessageView(View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        guild_config, _ = save.get_guild_config(self.guild_id)
        reasons = guild_config.get("ticket_reasons", []) or []
        options = [discord.SelectOption(label=reason[:100], value=str(index)) for index, reason in enumerate(reasons[:10])]
        self.reason_select = discord.ui.Select(
            placeholder="Choose a ticket reason",
            options=options,
            custom_id="ticket_reason_select",
            min_values=1,
            max_values=1,
        )
        self.reason_select.callback = self.on_reason_selected
        self.add_item(self.reason_select)

    async def on_reason_selected(self, interaction: discord.Interaction):
        if not self.reason_select.values:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No reason was selected.", ephemeral=True)
            return
        reason_index = int(self.reason_select.values[0])
        guild_config, _ = save.get_guild_config(self.guild_id)
        reasons = guild_config.get("ticket_reasons", []) or []
        if reason_index < 0 or reason_index >= len(reasons):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid reason selected.", ephemeral=True)
            return
        await create_ticket_for_user(interaction, self.guild_id, reasons[reason_index])


# ---------------------------------------------------------------- ticket threads

def is_ticket_staff(member: discord.abc.User, guild_id: str) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.manage_channels:
        return True
    guild_config, _ = save.get_guild_config(guild_id)
    manager_role_id = guild_config.get("ticket_manager_role_id")
    try:
        return bool(manager_role_id) and any(role.id == int(manager_role_id) for role in member.roles)
    except (TypeError, ValueError):
        return False


class TicketThreadControlView(View):
    def __init__(self, guild_id: str, owner_id: int, thread_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.thread_id = thread_id
        self.close_button = Button(label="Close", style=discord.ButtonStyle.secondary, custom_id="ticket_close")
        self.resolve_button = Button(label="Resolve", style=discord.ButtonStyle.success, custom_id="ticket_resolve")
        self.delete_button = Button(label="Delete", style=discord.ButtonStyle.danger, custom_id="ticket_delete")
        self.close_button.callback = self.on_close
        self.resolve_button.callback = self.on_resolve
        self.delete_button.callback = self.on_delete
        self.add_item(self.close_button)
        self.add_item(self.resolve_button)
        self.add_item(self.delete_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This button must be used inside a ticket thread.", ephemeral=True)
            return False
        if interaction.user.id != self.owner_id and not is_ticket_staff(interaction.user, self.guild_id):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Only the ticket owner or staff can manage this ticket.", ephemeral=True)
            return False
        return True

    async def _remove_owner(self, thread: discord.Thread) -> None:
        owner = thread.guild.get_member(self.owner_id)
        if owner:
            try:
                await thread.remove_user(owner)
            except (discord.Forbidden, discord.HTTPException):
                pass
        clear_active_ticket(self.guild_id, self.owner_id)

    async def on_close(self, interaction: discord.Interaction):
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            return
        await interaction.response.defer(ephemeral=True)
        await self._remove_owner(thread)
        await interaction.followup.send("<:approve:1517452125687513158> Ticket closed. The owner can no longer access the thread.", ephemeral=True)
        try:
            await thread.edit(archived=True)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def on_resolve(self, interaction: discord.Interaction):
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            return
        await interaction.response.defer(ephemeral=True)
        await self._remove_owner(thread)
        await interaction.followup.send("<:approve:1517452125687513158> Ticket resolved and closed.", ephemeral=True)
        # Post before archiving: sending into an archived thread would reopen it.
        try:
            await thread.send("✅ This ticket has been resolved.")
        except (discord.Forbidden, discord.HTTPException):
            pass
        try:
            await thread.edit(archived=True)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def on_delete(self, interaction: discord.Interaction):
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            return
        clear_active_ticket(self.guild_id, self.owner_id)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:trash:1517497581058527404> Ticket deleted.", ephemeral=True)
        try:
            await thread.delete()
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't delete this thread. Please check my Manage Threads permission.", ephemeral=True)


async def create_ticket_for_user(interaction: discord.Interaction, guild_id: str, reason: str | None = None):
    if not interaction.guild or not interaction.channel:
        await interaction.response.send_message("<:disapprove:1517452151012589662> This action must be used within the configured server.", ephemeral=True)
        return
    existing_thread_id = get_active_ticket_thread_id(guild_id, interaction.user.id)
    guild = interaction.guild
    if existing_thread_id:
        existing_thread = guild.get_thread(int(existing_thread_id))
        if existing_thread and not existing_thread.archived:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> You already have an active ticket: {existing_thread.mention}", ephemeral=True)
            return
        clear_active_ticket(guild_id, interaction.user.id)
    guild_config, _ = save.get_guild_config(guild_id)
    channel_id = guild_config.get("ticket_channel_id")
    if not channel_id:
        await interaction.response.send_message("<:disapprove:1517452151012589662> Ticket channel is not configured.", ephemeral=True)
        return
    channel = guild.get_channel(int(channel_id))
    if not channel or not hasattr(channel, "create_thread"):
        await interaction.response.send_message("<:disapprove:1517452151012589662> Ticket channel is not available.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    thread_name = f"ticket-{interaction.user.name}"[:95]
    try:
        thread = await channel.create_thread(name=thread_name, type=discord.ChannelType.private_thread, invitable=False)
    except Exception:
        await interaction.followup.send("<:disapprove:1517452151012589662> Failed to create the ticket thread.", ephemeral=True)
        return
    try:
        await thread.add_user(interaction.user)
    except Exception:
        pass
    owner_id = interaction.user.id
    manager_mention = ""
    manager_role_id = guild_config.get("ticket_manager_role_id")
    manager_role = guild.get_role(int(manager_role_id)) if manager_role_id else None
    if manager_role:
        manager_mention = manager_role.mention
    ticket_title = f"<:ticket:1533568847725203609> Welcome to your ticket thread {interaction.user.name},\na staff member will be with you shortly! \n"
    thread_control_view = TicketThreadControlView(guild_id, owner_id, thread.id)
    first_message = await thread.send(
        f"{interaction.user.mention} opened a ticket. {manager_mention}",
        embed=discord.Embed(title=ticket_title, description=f"reason for ticket: {reason}" if reason else None, color=discord.Color.green()),
        view=thread_control_view,
    )
    set_active_ticket_thread_entry(guild_id, owner_id, thread.id, first_message.id)
    try:
        runtime.bot.add_view(thread_control_view, message_id=first_message.id)
    except Exception:
        pass
    await interaction.followup.send(f"<:approve:1517452125687513158> Your ticket has been opened: {thread.mention}", ephemeral=True)

    # Resets the reason picker on the announce message.
    await refresh_ticket_announce_message(guild_id)


# ---------------------------------------------------------------- cog

class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._views_restored = False

    async def cog_load(self):
        if self.bot.is_ready():
            await self.restore_ticket_views()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.restore_ticket_views()

    async def restore_ticket_views(self) -> None:
        """Re-attach the ticket buttons after a restart."""
        if self._views_restored:
            return
        self._views_restored = True
        guild_data = save.load_guild_data()
        for guild_id, guild_config in guild_data.items():
            guild = self.bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
            if not guild or not isinstance(guild_config, dict):
                continue
            self._restore_announce_view(guild, str(guild_id), guild_config)
            await self._restore_thread_views(guild, str(guild_id), guild_config)

    def _restore_announce_view(self, guild: discord.Guild, guild_id: str, guild_config: dict) -> None:
        message_id = guild_config.get("ticket_announce_message_id")
        channel_id = guild_config.get("ticket_channel_id")
        if not message_id or not channel_id:
            return
        try:
            channel = guild.get_channel(int(channel_id))
            if not channel or not hasattr(channel, "send"):
                return
            self.bot.add_view(build_ticket_create_view(guild_id), message_id=int(message_id))
        except Exception:
            pass

    async def _restore_thread_views(self, guild: discord.Guild, guild_id: str, guild_config: dict) -> None:
        active_threads = guild_config.get("ticket_active_threads")
        if not isinstance(active_threads, dict):
            return
        for owner_id_str, active_thread_entry in list(active_threads.items()):
            try:
                if isinstance(active_thread_entry, dict):
                    thread_id = active_thread_entry.get("thread_id")
                    control_message_id = active_thread_entry.get("control_message_id")
                else:
                    thread_id = active_thread_entry
                    control_message_id = None
                if not thread_id:
                    continue
                if control_message_id:
                    view = TicketThreadControlView(guild_id, int(owner_id_str), int(thread_id))
                    self.bot.add_view(view, message_id=int(control_message_id))
                    continue
                # Older entries don't store the control message: find the thread's first message.
                thread = guild.get_thread(int(thread_id))
                if thread is None:
                    thread = await guild.fetch_channel(int(thread_id))
                if not isinstance(thread, discord.Thread):
                    continue
                first_message = None
                async for message in thread.history(oldest_first=True, limit=1):
                    first_message = message
                if first_message:
                    view = TicketThreadControlView(guild_id, int(owner_id_str), thread.id)
                    self.bot.add_view(view, message_id=first_message.id)
                    set_active_ticket_thread_entry(guild_id, int(owner_id_str), thread.id, first_message.id)
            except Exception:
                continue


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
