from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext.commands import Cog, hybrid_command, Context, has_permissions
from discord.ext import tasks

from LowerLeveled.timestamp import parse_duration_to_seconds
from LowerLeveled.validate import validate_role_selection
from Shared.Giveaways import load_giveaway_data, finalize_giveaway, save_giveaway_data
from Views.Giveaways import GiveawayView


async def setup(bot):
    await bot.add_cog(Giveaways(bot))

class Giveaways(Cog):
    def __init__(self, bot):
        self.bot = bot

    @tasks.loop(minutes=1)
    async def giveaway_loop(self):
        data = load_giveaway_data()
        if not data:
            return

        now = int(datetime.now(timezone.utc).timestamp())
        for giveaway_id, giveaway in list(data.items()):
            if giveaway.get('status') != 'active':
                continue
            if int(giveaway.get('end_time', 0)) <= now:
                await finalize_giveaway(self.bot, giveaway_id, giveaway)

    @tasks.loop(seconds=30)
    async def giveaway_refresh_loop(self):
        data = load_giveaway_data()
        if not data:
            return

        for giveaway_id, giveaway in list(data.items()):
            if giveaway.get('status') != 'active':
                continue

            channel = self.bot.get_channel(int(giveaway['channel_id'])) if giveaway.get('channel_id') else None
            if not channel or not giveaway.get('message_id'):
                continue

            try:
                message = await channel.fetch_message(int(giveaway['message_id']))
                await message.edit(view=GiveawayView(self.bot, giveaway_id, giveaway))
            except Exception:
                pass

    @giveaway_loop.before_loop
    async def before_giveaway_loop(self):
        await self.bot.wait_until_ready()

    @hybrid_command(name="giveaway", description="Create or cancel a giveaway")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        action="Create or cancel a giveaway",
        name="The giveaway title",
        winners="How many winners to select",
        time="How long the giveaway lasts (e.g. 1h, 30m, 2d)",
        role="Optional role to award to winners",
        temp_role="Optional temporary role to award to winners",
        temp_role_time="Temporary role duration in minutes",
        item="Optional item reward",
        money="Optional money reward",
        xp="Optional XP reward"
    )
    @app_commands.choices(
        action=[app_commands.Choice(name="Create", value="create"), app_commands.Choice(name="Cancel", value="cancel")])
    @has_permissions(manage_guild=True)
    async def adm_giveaway(
            self,
            ctx: Context,
            action: str,
            name: str = None,
            winners: int = 1,
            time: str = None,
            role: discord.Role = None,
            temp_role: discord.Role = None,
            temp_role_time: int = 0,
            item: str = None,
            money: int = 0,
            xp: int = 0,
    ):
        if action == "cancel":
            if not name:
                await ctx.send(
                    "<:disapprove:1517452151012589662> Please provide the giveaway name to cancel.", ephemeral=True)
                return

            data = load_giveaway_data()
            matched = None
            for giveaway_id, giveaway in data.items():
                if str(giveaway.get('guild_id')) == str(ctx.guild_id) and giveaway.get(
                        'status') == 'active' and str(giveaway.get('name', '')).lower() == name.lower():
                    matched = (giveaway_id, giveaway)
                    break

            if not matched:
                await ctx.send(
                    "<:disapprove:1517452151012589662> I couldn't find an active giveaway with that name.",
                    ephemeral=True)
                return

            giveaway_id, giveaway = matched
            giveaway['status'] = 'cancelled'
            data.pop(giveaway_id, None)
            save_giveaway_data(data)

            channel = ctx.channel
            if channel and giveaway.get('message_id'):
                try:
                    message = await channel.fetch_message(int(giveaway['message_id']))
                    view = GiveawayView(giveaway_id, giveaway, bot = self.bot)
                    await message.edit(view=view)
                except Exception:
                    pass

            await ctx.send(f"<:approve:1517452125687513158> Cancelled giveaway **{name}**.")
            return

        if not name:
            await ctx.send("<:disapprove:1517452151012589662> Please provide a giveaway name.",
                                                    ephemeral=True)
            return
        if winners <= 0:
            await ctx.send("<:disapprove:1517452151012589662> Winners must be at least 1.",
                                                    ephemeral=True)
            return
        if temp_role and temp_role_time <= 0:
            await ctx.send(
                "<:disapprove:1517452151012589662> Temporary role time must be greater than 0 when using a temp role.",
                ephemeral=True)
            return

        role_error = validate_role_selection(ctx, role, "role")
        if role_error:
            await ctx.send(role_error, ephemeral=True)
            return

        temp_role_error = validate_role_selection(ctx, temp_role, "temporary role")
        if temp_role_error:
            await ctx.send(temp_role_error, ephemeral=True)
            return

        duration_seconds = parse_duration_to_seconds(time or "30m")
        if duration_seconds is None or duration_seconds <= 0:
            await ctx.send(
                "<:disapprove:1517452151012589662> Please provide a valid time like 30m, 1h, or 2d.", ephemeral=True)
            return

        giveaway_data = {
            'name': name,
            'host_id': ctx.author.id,
            'winners_count': winners,
            'entries': [],
            'status': 'active',
            'end_time': int((datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)).timestamp()),
            'guild_id': ctx.guild.id,
            'channel_id': ctx.channel.id,
            'role_id': role.id if role else None,
            'temp_role_id': temp_role.id if temp_role else None,
            'temp_role_time': temp_role_time if temp_role else 0,
            'item': item,
            'money': money,
            'xp': xp,
        }

        view = GiveawayView("placeholder", giveaway_data, bot=self.bot)
        message = await ctx.send(view=view)

        giveaway_id = f"{ctx.guild.id}:{ctx.channel.id}:{message.id}"
        giveaway_data['message_id'] = message.id
        data = load_giveaway_data()
        data[giveaway_id] = giveaway_data
        save_giveaway_data(data)

        view = GiveawayView(giveaway_id, giveaway_data, bot=self.bot)
        try:
            await message.edit(view=view)
        except Exception:
            pass
