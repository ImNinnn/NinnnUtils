import io
import os

import discord
from PIL import Image, ImageDraw, ImageFont

from Shared.User import format_banner_username, get_banner_name


async def create_welcome_card(member):
    base_path = os.path.dirname(__file__)
    bg_path = os.path.join(base_path, "welcome_bg.png")
    font_path = os.path.join(base_path, "Minecraft.ttf")

    if not os.path.exists(bg_path):
        print(f"Background not found at: {bg_path}")
        return None

    background = Image.open(bg_path).convert("RGBA")
    avatar_bytes = await member.display_avatar.with_format("png").read()

    with Image.open(io.BytesIO(avatar_bytes)) as avatar:
        avatar = avatar.convert("RGBA").resize((160, 160))
        background.paste(avatar, (480, 40))

    draw = ImageDraw.Draw(background)
    try:
        font_big = ImageFont.truetype(font_path, 35)
        font_small = ImageFont.truetype(font_path, 15)
        font_medium = ImageFont.truetype(font_path, 25)
    except Exception as e:
        print(f"Font error: {e}. Using default.")
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()

    draw.text((35, 30), f"Welcome", fill=(255, 255, 255), font=font_big)
    draw.text((35, 80), format_banner_username(get_banner_name(member), 25), fill=(255, 255, 255), font=font_medium)
    draw.text((35, 140), f"to the {member.guild.name} server", fill=(200, 200, 200), font=font_small)

    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="welcome.png")


async def create_goodbye_card(member):
    base_path = os.path.dirname(__file__)
    goodbye_bg_path = os.path.join(base_path, "goodbye_bg.png")
    bg_path = goodbye_bg_path if os.path.exists(goodbye_bg_path) else os.path.join(base_path, "welcome_bg.png")
    font_path = os.path.join(base_path, "Minecraft.ttf")

    if not os.path.exists(bg_path):
        print(f"Goodbye background not found at: {bg_path}")
        return None

    background = Image.open(bg_path).convert("RGBA")
    avatar_bytes = await member.display_avatar.with_format("png").read()

    with Image.open(io.BytesIO(avatar_bytes)) as avatar:
        avatar = avatar.convert("RGBA").resize((160, 160))
        background.paste(avatar, (480, 40))

    draw = ImageDraw.Draw(background)
    try:
        font_big = ImageFont.truetype(font_path, 35)
        font_small = ImageFont.truetype(font_path, 15)
        font_medium = ImageFont.truetype(font_path, 25)
    except Exception as e:
        print(f"Font error: {e}. Using default.")
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()

    draw.text((35, 30), "Goodbye", fill=(255, 255, 255), font=font_big)
    draw.text((35, 80), format_banner_username(get_banner_name(member), 25), fill=(255, 255, 255), font=font_medium)
    draw.text((35, 140), f"from {member.guild.name}", fill=(200, 200, 200), font=font_small)
    draw.text((35, 170), "We hope to see you again soon!", fill=(200, 200, 200), font=font_small)

    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="goodbye.png")
