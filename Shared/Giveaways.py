import asyncio
import random

import discord

from Shared.Data import load_data, save_data
from Shared.Inventory import inventory_add
from Shared.Leveling import add_xp
from Shared.User import format_user_reference
from Views.Giveaways import GiveawayView
from main import GIVEAWAY_FILE
from DataManager import DataManager

def load_giveaway_data():
    return DataManager.load(GIVEAWAY_FILE, {})


def save_giveaway_data(data):
    DataManager.save(GIVEAWAY_FILE, data)

def build_giveaway_embed(bot, giveaway: dict) -> discord.Embed:
    """Build embed for giveaway display."""
    title = giveaway.get('name', 'Giveaway')
    host_id = giveaway.get('host_id')
    host_value = f"<@{host_id}>" if host_id else "Unknown"
    entries = giveaway.get('entries', [])

    reward_parts = []
    if giveaway.get('role_id'):
        role = bot.get_guild(int(giveaway['guild_id'])).get_role(int(giveaway['role_id'])) if bot.get_guild(
            int(giveaway['guild_id'])) else None
        reward_parts.append(f"Role: {role.name if role else 'Unknown role'}")
    if giveaway.get('temp_role_id'):
        role = bot.get_guild(int(giveaway['guild_id'])).get_role(int(giveaway['temp_role_id'])) if bot.get_guild(
            int(giveaway['guild_id'])) else None
        reward_parts.append(
            f"Temp role: {role.name if role else 'Unknown role'} ({giveaway.get('temp_role_time', 0)}m)")
    if giveaway.get('item'):
        reward_parts.append(f"Item: {giveaway['item']}")
    if giveaway.get('money', 0):
        reward_parts.append(f"Money: ${giveaway['money']}")
    if giveaway.get('xp', 0):
        reward_parts.append(f"XP: {giveaway['xp']}")

    reward_text = "\n".join(reward_parts) if reward_parts else "No rewards"

    if giveaway.get('status') == 'ended':
        embed = discord.Embed(title=f"<:present:1522648005650415658> {title}", description="Giveaway ended",
                              color=discord.Color.red())
    else:
        embed = discord.Embed(title=f"<:present:1522648005650415658> {title}", description="━━━━━━━━━━━━━━",
                              color=discord.Color.gold())

    embed.add_field(name="Host", value=host_value, inline=True)
    embed.add_field(name="Winners", value=str(giveaway.get('winners_count', 1)), inline=True)
    embed.add_field(name="Entries", value=str(len(entries)), inline=False)
    embed.add_field(name="Rewards", value=reward_text, inline=False)
    embed.add_field(name="Ends", value=f"<t:{giveaway.get('end_time')}:R>", inline=False)
    return embed

async def finalize_giveaway(bot, giveaway_id: str, giveaway: dict):
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
            view = GiveawayView(giveaway_id, giveaway, bot)
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
                    await member.add_roles(role, reason=f"Giveaway winner for {giveaway['name']}")
                except Exception:
                    pass
            if temp_role and member and giveaway.get('temp_role_time', 0) > 0:
                try:
                    await member.add_roles(temp_role, reason=f"Temporary giveaway role for {giveaway['name']}")

                    async def remove_temp_role():
                        await asyncio.sleep(int(giveaway['temp_role_time']) * 60)
                        try:
                            await member.remove_roles(temp_role, reason="Temporary giveaway role expired")
                        except Exception:
                            pass

                    asyncio.create_task(remove_temp_role())
                except Exception:
                    pass

            if giveaway.get('money', 0) or giveaway.get('xp', 0) or giveaway.get('item'):
                if giveaway.get('money', 0) or giveaway.get('item'):
                    economy_data = load_data()
                    guild_data = economy_data.setdefault(str(guild.id), {})
                    users = guild_data.setdefault('users', {})
                    user_data = users.setdefault(str(winner_id), {"balance": 0, "inventory": {}})
                    user_data.setdefault("inventory", {})
                    if giveaway.get('money', 0):
                        user_data['balance'] = user_data.get('balance', 0) + int(giveaway['money'])
                    if giveaway.get('item'):
                        inventory_add(user_data['inventory'], giveaway['item'], 1)
                    save_data(economy_data)
                if giveaway.get('xp', 0) and member:
                    await add_xp(bot, member, guild, int(giveaway['xp']), announce_channel=channel)

            try:
                user = await bot.fetch_user(int(winner_id))
                if user:
                    dm_embed = discord.Embed(
                        title="<:spark:1517583248421552305> Giveaway Win!",
                        description=f"You won the giveaway **{giveaway['name']}** in **{guild.name}**.",
                        color=discord.Color.green(),
                    )
                    if role:
                        dm_embed.add_field(name="<:bell:1517497562184024275> Role", value=role.name, inline=True)
                    if temp_role:
                        dm_embed.add_field(name="<:timer:1517996239583576194> Temp Role",
                                           value=f"{temp_role.name} ({giveaway.get('temp_role_time', 0)}m)",
                                           inline=True)
                    if giveaway.get('money', 0):
                        dm_embed.add_field(name="<:money:1517580310395486239> Money", value=f"${giveaway['money']}",
                                           inline=True)
                    if giveaway.get('xp', 0):
                        dm_embed.add_field(name="<:Vial:1517681553377857628> XP", value=str(giveaway['xp']),
                                           inline=True)
                    if giveaway.get('item'):
                        dm_embed.add_field(name="<:box:1517581439552585759> Item", value=giveaway['item'], inline=True)
                    await user.send(embed=dm_embed)
            except Exception:
                pass

    if channel:
        if winners:
            winner_text = ", ".join(winner_references) if winner_references else "unknown winners"
            await channel.send(
                f"<:spark:1517583248421552305> Giveaway **{giveaway['name']}** has ended! Winners: {winner_text}")
        else:
            await channel.send(
                f"<:spark:1517583248421552305> Giveaway **{giveaway['name']}** has ended with no entries.")

    data = load_giveaway_data()
    if giveaway_id in data:
        del data[giveaway_id]
        save_giveaway_data(data)
