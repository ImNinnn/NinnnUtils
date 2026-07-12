import asyncio
import io
import os

import discord
from PIL import Image, ImageDraw, ImageFont

from LowerLeveled.jsonutils import load_json_file, save_json_file
from Shared.Data import load_data, save_data
from Shared.Errors import add_bot_error_entry
from Shared.Guilds import get_guild_config
from Shared.Inventory import inventory_add
from Shared.User import get_user_color, get_user_has_leveled_up_before, set_user_has_leveled_up_before, get_user_data, \
    format_user_reference, format_banner_username, get_banner_name
from main import LEVEL_FILE


def load_levels():
    return load_json_file(LEVEL_FILE, {})


def save_levels(data):
    save_json_file(LEVEL_FILE, data)

def get_xp_needed(level: int) -> int:
    return 100 + (level * 10)

def get_level_channel_id(guild_id: str):
    levels = load_levels()
    if guild_id in levels:
        return levels[guild_id].get("config", {}).get("channel_id")
    return None


def set_level_channel(guild_id: str, channel_id: int | None):
    levels = load_levels()
    if guild_id not in levels:
        levels[guild_id] = {"config": {}, "users": {}}
    if "config" not in levels[guild_id]:
        levels[guild_id]["config"] = {}
    levels[guild_id]["config"]["channel_id"] = channel_id
    save_levels(levels)


async def add_xp(bot, member: discord.Member, guild: discord.Guild, xp_to_add: int, announce_channel=None):
    if member.bot:
        return

    levels = load_levels()
    guild_id = str(guild.id)
    user_id = str(member.id)

    if guild_id not in levels:
        levels[guild_id] = {"config": {"channel_id": None, "rewards": {}}, "users": {}}

    if user_id not in levels[guild_id]["users"]:
        levels[guild_id]["users"][user_id] = {"xp": 0, "level": 0, "color": get_user_color(user_id) or "white"}

    user_data = levels[guild_id]["users"][user_id]
    user_data["xp"] += xp_to_add

    leveled_up = False
    while user_data["xp"] >= get_xp_needed(user_data["level"]):
        user_data["xp"] -= get_xp_needed(user_data["level"])
        user_data["level"] += 1
        leveled_up = True

    has_leveled_up_before = get_user_has_leveled_up_before(user_id)
    first_time_level_up = leveled_up and not has_leveled_up_before

    save_levels(levels)

    if leveled_up:
        rewards = levels[guild_id]["config"].get("rewards", {})
        current_level = user_data["level"]
        reward = rewards.get(str(current_level))
        level_up_notification_sent = False
        if reward:
            if isinstance(reward, (str, int)):
                reward = {"role_id": int(reward)}

            if reward.get("money", 0) > 0 or reward.get("give_item") or reward.get("xp", 0) > 0:
                data = load_data()
                economy_user = get_user_data(data, guild_id, member.id)
                if reward.get("money", 0) > 0:
                    economy_user["balance"] += reward["money"]
                if reward.get("give_item"):
                    inventory_add(economy_user["inventory"], reward["give_item"], reward.get("give_item_amount", 1))
                save_data(data)

            if reward.get("role_id"):
                role = guild.get_role(int(reward["role_id"]))
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role)
                    except discord.Forbidden as error:
                        add_bot_error_entry(guild.id, None, member, f"level reward role: {role.name}", error)

            if reward.get("temp_role_id"):
                role = guild.get_role(int(reward["temp_role_id"]))
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role)
                    except discord.Forbidden as error:
                        add_bot_error_entry(guild.id, None, member, f"level temp role: {role.name}", error)
                        role = None
                if role and reward.get("duration", 0) > 0:
                    async def remove_temp_role(r):
                        await asyncio.sleep(reward.get("duration", 0))
                        try:
                            await member.remove_roles(r)
                        except discord.Forbidden as error:
                            add_bot_error_entry(guild.id, None, member, f"level temp role remove: {r.name}", error)

                    bot.loop.create_task(remove_temp_role(role))

            if reward.get("xp", 0) > 0:
                await add_xp(bot, member, guild, reward["xp"], announce_channel=announce_channel)

        guild_config = get_guild_config(str(guild.id))[0]
        if guild_config.get("level_up_message_enabled", False) and announce_channel is not None:
            try:
                level_up_message = f"{format_user_reference(member)} just reached **Level {current_level}**!"
                if first_time_level_up:
                    level_up_message += "\n-# Use /settings and go to the user settings to disable pings."
                await announce_channel.send(level_up_message)
                level_up_notification_sent = True
            except discord.Forbidden as error:
                add_bot_error_entry(guild.id, announce_channel.id, member, "level up message", error)
            except Exception:
                pass

        channel_id = levels[guild_id]["config"].get("channel_id")
        target_channel = guild.get_channel(int(channel_id)) if channel_id else None

        if target_channel:
            card_bytes = await create_levelup_card(member, current_level)
            if card_bytes:
                file = discord.File(fp=card_bytes, filename="levelup.png")
                try:
                    level_banner_message = f"{format_user_reference(member)}, you just reached **Level {current_level}**!"
                    if first_time_level_up:
                        level_banner_message += "\n-# Use /settings and go to the user settings to disable pings."
                    await target_channel.send(
                        content=level_banner_message,
                        file=file
                    )
                    level_up_notification_sent = True
                except discord.Forbidden as error:
                    add_bot_error_entry(guild.id, target_channel.id, member, "level banner", error)

        if first_time_level_up and level_up_notification_sent:
            set_user_has_leveled_up_before(user_id, True)

async def create_levelup_card(member: discord.Member, level: int):
    base_path = os.path.dirname(__file__)
    bg_path = os.path.join(base_path, "levelup_bg.png")
    font_path = os.path.join(base_path, "Minecraft.ttf")

    if not os.path.exists(bg_path):
        return None

    background = Image.open(bg_path).convert("RGBA")
    avatar_bytes = await member.display_avatar.with_format("png").read()

    bg_width = background.width
    center_x = bg_width // 2

    with Image.open(io.BytesIO(avatar_bytes)) as avatar:
        avatar = avatar.convert("RGBA").resize((120, 120))
        background.paste(avatar, (center_x - 60, 40))

    draw = ImageDraw.Draw(background)
    try:
        font = ImageFont.truetype(font_path, 25)
    except Exception:
        font = ImageFont.load_default()

    draw.text((center_x, 190), f"{format_banner_username(get_banner_name(member))} you are now Level {level}!",
              fill="white", font=font, anchor="mm")

    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def save_level_reward_data(guild_id: str, level: int, reward_data: dict) -> None:
    levels = load_levels()
    if guild_id not in levels:
        levels[guild_id] = {"config": {"channel_id": None, "rewards": {}}, "users": {}}
    if "rewards" not in levels[guild_id]["config"]:
        levels[guild_id]["config"]["rewards"] = {}
    levels[guild_id]["config"]["rewards"][str(level)] = reward_data
    save_levels(levels)


def format_level_reward_summary(guild: discord.Guild, level: str, reward_data: dict) -> str:
    parts = []

    role_id = reward_data.get("role_id")
    if role_id:
        role = guild.get_role(role_id)
        parts.append(f"Role: {role.mention if role else f'`{role_id}`'}")

    temp_role_id = reward_data.get("temp_role_id")
    if temp_role_id:
        role = guild.get_role(temp_role_id)
        duration = reward_data.get("duration", 0)
        parts.append(f"Temp role: {role.mention if role else f'`{temp_role_id}`'} for `{duration}s`")

    money = reward_data.get("money", 0)
    if money > 0:
        parts.append(f"Money: `${money}`")

    xp = reward_data.get("xp", 0)
    if xp > 0:
        parts.append(f"XP: `{xp}`")

    give_item = reward_data.get("give_item")
    if give_item:
        amount = reward_data.get("give_item_amount", 1)
        parts.append(f"Item: `{amount}x {give_item}`")

    if not parts:
        return f"Level {level}: No rewards configured."

    return f"Level {level}: " + " | ".join(parts)
