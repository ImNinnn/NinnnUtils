"""Giveaways: /giveaway_adm, the entry button, and drawing winners when a giveaway ends."""

import asyncio
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, Container, LayoutView, Section, Separator, TextDisplay, View

import save
from utils import runtime
from utils.audit import add_bot_error_entry
from utils.economy import get_user_data, inventory_add
from utils.formatting import format_user_reference, parse_duration_to_seconds
from utils.permissions import validate_role_selection


class LeaveGiveawayConfirmView(View):
    def __init__(self, giveaway_id: str, original_message, user_id: str):
        super().__init__(timeout=600)
        self.giveaway_id = giveaway_id
        self.original_message = original_message
        self.user_id = user_id

    @discord.ui.button(label="Leave giveaway", style=discord.ButtonStyle.danger)
    async def confirm_leave(self, interaction: discord.Interaction, button: Button):
        data = save.load_giveaway_data()
        giveaway = data.get(self.giveaway_id)
        if not giveaway or giveaway.get('status') != 'active':
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("This giveaway is no longer active.", ephemeral=True)
            return

        updated_entries = [entry for entry in giveaway.get('entries', []) if str(entry) != self.user_id]
        giveaway['entries'] = updated_entries
        data[self.giveaway_id] = giveaway
        save.save_giveaway_data(data)

        updated_view = GiveawayView(self.giveaway_id, giveaway)
        try:
            if self.original_message is not None:
                await self.original_message.edit(view=updated_view)
        except Exception:
            pass

        await interaction.response.defer(ephemeral=True); await interaction.followup.send("You left the giveaway.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_leave(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Okay, you stayed in the giveaway.", ephemeral=True)


class GiveawayView(LayoutView):
    def __init__(self, giveaway_id: str, giveaway: dict):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.giveaway = giveaway
        self.build_components()

    def build_components(self):
        self.clear_items()
        giveaway = self.giveaway
        entries = giveaway.get('entries', [])

        entry_button = Button(
            label="Enter giveaway !",
            style=discord.ButtonStyle.success,
            custom_id=f"giveaway_enter:{self.giveaway_id}",
        )

        async def on_enter(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)

            data = save.load_giveaway_data()
            giveaway = data.get(self.giveaway_id)
            if not giveaway or giveaway.get('status') != 'active':
                await interaction.followup.send("This giveaway is no longer active.", ephemeral=True)
                return

            user_id = str(interaction.user.id)
            normalized_entries = [str(entry) for entry in giveaway.get('entries', []) if entry]
            if user_id in normalized_entries:
                confirm_view = LeaveGiveawayConfirmView(self.giveaway_id, interaction.message, user_id)
                await interaction.followup.send(
                    "You are already entered in this giveaway. Do you want to leave it?",
                    view=confirm_view,
                    ephemeral=True,
                )
                return

            normalized_entries.append(user_id)
            giveaway['entries'] = normalized_entries
            data[self.giveaway_id] = giveaway
            save.save_giveaway_data(data)

            updated_view = GiveawayView(self.giveaway_id, giveaway)
            try:
                await interaction.message.edit(view=updated_view)
            except Exception:
                pass

            await interaction.followup.send("You joined the giveaway!", ephemeral=True)

        entry_button.callback = on_enter

        host_id = giveaway.get('host_id')
        host_value = f"<@{host_id}>" if host_id else "Unknown"

        reward_parts = []
        if giveaway.get('role_id'):
            role = runtime.bot.get_guild(int(giveaway['guild_id'])).get_role(int(giveaway['role_id'])) if runtime.bot.get_guild(int(giveaway['guild_id'])) else None
            reward_parts.append(f"Role: {role.name if role else 'Unknown role'}")
        if giveaway.get('temp_role_id'):
            role = runtime.bot.get_guild(int(giveaway['guild_id'])).get_role(int(giveaway['temp_role_id'])) if runtime.bot.get_guild(int(giveaway['guild_id'])) else None
            reward_parts.append(f"Temp role: {role.name if role else 'Unknown role'} ({giveaway.get('temp_role_time', 0)}m)")
        if giveaway.get('item'):
            reward_parts.append(f"Item: {giveaway['item']}")
        if giveaway.get('money', 0):
            reward_parts.append(f"Money: ${giveaway['money']}")
        if giveaway.get('xp', 0):
            reward_parts.append(f"XP: {giveaway['xp']}")

        reward_text = "\n".join(reward_parts) if reward_parts else "No rewards"

        container_items = [
            TextDisplay(f"<:present:1522648005650415658> {giveaway['name']}"),
            Separator(),
            TextDisplay(f"**Host:** {host_value}\n**Winners:** {giveaway.get('winners_count', 1)}"),
        ]

        if giveaway.get('status') == 'active':
            container_items.append(
                Section(
                    f"**Entries:** {len(entries)}",
                    accessory=entry_button,
                )
            )
        else:
            container_items.append(TextDisplay(f"**Entries:** {len(entries)}"))

        container_items.extend([
            Separator(),
            TextDisplay(f"**Rewards:**\n{reward_text}"),
            Separator(),
            TextDisplay(f"**Ends:** <t:{giveaway.get('end_time')}:R>"),
        ])

        container = Container(
            *container_items,
            accent_color=discord.Color.gold() if giveaway.get('status') == 'active' else discord.Color.red(),
        )
        self.add_item(container)


class GiveawaysCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._background_tasks: set[asyncio.Task] = set()
        self._views_restored = False

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    # bot.py loads cogs before logging in, so the loop starts on ready (or right away on a reload).
    async def cog_load(self):
        if self.bot.is_ready():
            self.start_tasks()

    async def cog_unload(self):
        self.giveaway_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        self.start_tasks()

    def start_tasks(self) -> None:
        self.restore_giveaway_views()
        if not self.giveaway_loop.is_running():
            self.giveaway_loop.start()

    def restore_giveaway_views(self) -> None:
        """Re-attach the Enter buttons of running giveaways after a restart."""
        if self._views_restored:
            return
        self._views_restored = True
        for giveaway_id, giveaway in save.load_giveaway_data().items():
            try:
                if giveaway.get('status') != 'active' or not giveaway.get('message_id'):
                    continue
                self.bot.add_view(GiveawayView(str(giveaway_id), giveaway), message_id=int(giveaway['message_id']))
            except Exception:
                continue

    # ------------------------------------------------------------ ending

    @tasks.loop(minutes=1)
    async def giveaway_loop(self):
        await self.check_giveaways()

    @giveaway_loop.before_loop
    async def before_giveaway_loop(self):
        await self.bot.wait_until_ready()

    async def check_giveaways(self) -> None:
        data = save.load_giveaway_data()
        if not data:
            return
        now_ts = int(datetime.now(timezone.utc).timestamp())
        due = []
        for giveaway_id, giveaway in data.items():
            try:
                status = giveaway.get('status')
                # 'ending' was left behind by a restart in the middle of drawing winners.
                if status == 'ending' and not self._background_tasks:
                    due.append((str(giveaway_id), giveaway))
                elif status == 'active' and int(giveaway.get('end_time', 0)) <= now_ts:
                    due.append((str(giveaway_id), giveaway))
            except (TypeError, ValueError):
                continue
        if not due:
            return
        # Mark them before drawing so the next loop tick can't draw winners a second time.
        for giveaway_id, giveaway in due:
            giveaway['status'] = 'ending'
        save.save_giveaway_data(data)
        for giveaway_id, giveaway in due:
            self._spawn(self.finalize_giveaway(giveaway_id, giveaway))

    async def finalize_giveaway(self, giveaway_id: str, giveaway: dict):
        try:
            await self._finalize_giveaway(giveaway_id, giveaway)
        except Exception as error:
            add_bot_error_entry(int(giveaway['guild_id']) if giveaway.get('guild_id') else None, giveaway.get('channel_id'), None, "giveaway: finalize", error)
        finally:
            data = save.load_giveaway_data()
            if giveaway_id in data:
                del data[giveaway_id]
                save.save_giveaway_data(data)

    async def _finalize_giveaway(self, giveaway_id: str, giveaway: dict):
        bot = self.bot
        guild = bot.get_guild(int(giveaway['guild_id'])) if giveaway.get('guild_id') else None
        entries = [entry for entry in giveaway.get('entries', []) if entry]
        winners = []
        if entries:
            winner_count = max(1, int(giveaway.get('winners_count', 1)))
            winners = random.sample(entries, k=min(winner_count, len(entries)))

        channel = bot.get_channel(int(giveaway['channel_id'])) if giveaway.get('channel_id') else None
        if channel and giveaway.get('message_id'):
            try:
                message = await channel.fetch_message(int(giveaway['message_id']))
                giveaway['status'] = 'ended'
                view = GiveawayView(giveaway_id, giveaway)
                await message.edit(view=view)
            except Exception:
                pass

        winner_references = []
        if guild:
            role = guild.get_role(int(giveaway['role_id'])) if giveaway.get('role_id') else None
            temp_role = guild.get_role(int(giveaway['temp_role_id'])) if giveaway.get('temp_role_id') else None

            for winner_id in winners:
                member = guild.get_member(int(winner_id))
                if member:
                    winner_references.append(format_user_reference(member))
                if role and member:
                    try:
                        await member.add_roles(role, reason=f"Giveaway winner for {giveaway['name']}"[:512])
                    except Exception:
                        pass
                if temp_role and member and giveaway.get('temp_role_time', 0) > 0:
                    try:
                        await member.add_roles(temp_role, reason=f"Temporary giveaway role for {giveaway['name']}"[:512])

                        async def remove_temp_role(member=member):
                            await asyncio.sleep(int(giveaway['temp_role_time']) * 60)
                            try:
                                await member.remove_roles(temp_role, reason="Temporary giveaway role expired")
                            except Exception:
                                pass
                        # Not tied to this cog's tasks: a cog reload must not cancel pending role removals.
                        asyncio.get_running_loop().create_task(remove_temp_role())
                    except Exception:
                        pass

                if giveaway.get('money', 0) or giveaway.get('item'):
                    economy_data = save.load_data()
                    user_data = get_user_data(economy_data, str(guild.id), winner_id)
                    if giveaway.get('money', 0):
                        user_data['balance'] = user_data.get('balance', 0) + int(giveaway['money'])
                    if giveaway.get('item'):
                        inventory_add(user_data['inventory'], giveaway['item'], 1)
                    save.save_data(economy_data)
                if giveaway.get('xp', 0) and member:
                    levels_cog = bot.get_cog('LevelsCog')
                    if levels_cog is not None:
                        await levels_cog.add_xp(member, guild, int(giveaway['xp']), announce_channel=channel)

                try:
                    user = member or await bot.fetch_user(int(winner_id))
                    dm_embed = discord.Embed(
                        title="<:spark:1517583248421552305> Giveaway Win!",
                        description=f"You won the giveaway **{giveaway['name']}** in **{guild.name}**.",
                        color=discord.Color.green(),
                    )
                    if role:
                        dm_embed.add_field(name="<:bell:1517497562184024275> Role", value=role.name, inline=True)
                    if temp_role:
                        dm_embed.add_field(name="<:timer:1517996239583576194> Temp Role", value=f"{temp_role.name} ({giveaway.get('temp_role_time', 0)}m)", inline=True)
                    if giveaway.get('money', 0):
                        dm_embed.add_field(name="<:money:1517580310395486239> Money", value=f"${giveaway['money']}", inline=True)
                    if giveaway.get('xp', 0):
                        dm_embed.add_field(name="<:Vial:1517681553377857628> XP", value=str(giveaway['xp']), inline=True)
                    if giveaway.get('item'):
                        dm_embed.add_field(name="<:box:1517581439552585759> Item", value=giveaway['item'], inline=True)
                    await user.send(embed=dm_embed)
                except Exception:
                    pass

        if channel:
            if winners:
                winner_text = ", ".join(winner_references) if winner_references else "unknown winners"
                text = f"<:spark:1517583248421552305> Giveaway **{giveaway['name']}** has ended! Winners: {winner_text}"
                source = "giveaway: send winners"
            else:
                text = f"<:spark:1517583248421552305> Giveaway **{giveaway['name']}** has ended with no entries."
                source = "giveaway: send no-entries"
            try:
                await channel.send(text[:2000])
            except Exception as e:
                add_bot_error_entry(guild.id if guild else None, getattr(channel, 'id', None), None, source, e)

    # ------------------------------------------------------------ command

    @app_commands.command(name='giveaway_adm', description='Create or cancel a giveaway')
    @app_commands.describe(action='Create or cancel a giveaway', name='The giveaway title', winners='How many winners to select', time='How long the giveaway lasts (e.g. 1h, 30m, 2d)', role='Optional role to award to winners', temp_role='Optional temporary role to award to winners', temp_role_time='Temporary role duration in minutes', item='Optional item reward', money='Optional money reward', xp='Optional XP reward')
    @app_commands.choices(action=[app_commands.Choice(name='Create', value='create'), app_commands.Choice(name='Cancel', value='cancel')])
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def giveaway_adm(self, interaction: discord.Interaction, action: str, name: str | None = None, winners: int = 1, time: str | None = None, role: discord.Role | None = None, temp_role: discord.Role | None = None, temp_role_time: int = 0, item: str | None = None, money: int = 0, xp: int = 0):
        if action == "cancel":
            if not name:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide the giveaway name to cancel.", ephemeral=True)
                return

            data = save.load_giveaway_data()
            matched = None
            for giveaway_id, giveaway in data.items():
                if str(giveaway.get('guild_id')) == str(interaction.guild_id) and giveaway.get('status') == 'active' and str(giveaway.get('name', '')).lower() == name.lower():
                    matched = (giveaway_id, giveaway)
                    break

            if not matched:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> I couldn't find an active giveaway with that name.", ephemeral=True)
                return

            giveaway_id, giveaway = matched
            giveaway['status'] = 'cancelled'
            data.pop(giveaway_id, None)
            save.save_giveaway_data(data)
            await interaction.response.defer()

            # The giveaway message may be in another channel than the one /giveaway_adm is used in.
            channel = self.bot.get_channel(int(giveaway['channel_id'])) if giveaway.get('channel_id') else interaction.channel
            if channel and giveaway.get('message_id'):
                try:
                    message = await channel.fetch_message(int(giveaway['message_id']))
                    view = GiveawayView(giveaway_id, giveaway)
                    await message.edit(view=view)
                except Exception:
                    pass

            await interaction.followup.send(f"<:approve:1517452125687513158> Cancelled giveaway **{name}**.")
            return

        if not name:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide a giveaway name.", ephemeral=True)
            return
        if winners <= 0:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Winners must be at least 1.", ephemeral=True)
            return
        if money < 0 or xp < 0:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Money and XP rewards can't be negative.", ephemeral=True)
            return
        if temp_role and temp_role_time <= 0:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Temporary role time must be greater than 0 when using a temp role.", ephemeral=True)
            return

        role_error = validate_role_selection(interaction, role, "role")
        if role_error:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(role_error, ephemeral=True)
            return

        temp_role_error = validate_role_selection(interaction, temp_role, "temporary role")
        if temp_role_error:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(temp_role_error, ephemeral=True)
            return

        duration_seconds = parse_duration_to_seconds(time or "30m")
        if duration_seconds is None or duration_seconds <= 0:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please provide a valid time like 30m, 1h, or 2d.", ephemeral=True)
            return

        giveaway_data = {
            'name': name,
            'host_id': interaction.user.id,
            'winners_count': winners,
            'entries': [],
            'status': 'active',
            'end_time': int((datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)).timestamp()),
            'guild_id': interaction.guild_id,
            'channel_id': interaction.channel_id,
            'role_id': role.id if role else None,
            'temp_role_id': temp_role.id if temp_role else None,
            'temp_role_time': temp_role_time if temp_role else 0,
            'item': item,
            'money': money,
            'xp': xp,
        }

        view = GiveawayView("placeholder", giveaway_data)
        await interaction.response.defer(); await interaction.followup.send(view=view)
        message = await interaction.original_response()

        giveaway_id = f"{interaction.guild_id}:{interaction.channel_id}:{message.id}"
        giveaway_data['message_id'] = message.id
        data = save.load_giveaway_data()
        data[giveaway_id] = giveaway_data
        save.save_giveaway_data(data)

        view = GiveawayView(giveaway_id, giveaway_data)
        try:
            await message.edit(view=view)
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawaysCog(bot))
