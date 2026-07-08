import io
import os
import unicodedata

import discord
from PIL import Image, ImageOps, ImageDraw, ImageFont

from LowerLeveled.image import wrap_text


async def create_quote_card(message: discord.Message):
    base_path = os.path.dirname(__file__)
    bg_path = os.path.join(base_path, "Quote_bg.png")
    fg_path = os.path.join(base_path, "Quote_fg.png")
    font_path = os.path.join(base_path, "Minecraft.ttf")

    if not os.path.exists(bg_path) or not os.path.exists(fg_path):
        print(f"Quote background or foreground not found at: {bg_path}, {fg_path}")
        return None

    background = Image.open(bg_path).convert("RGBA")
    foreground = Image.open(fg_path).convert("RGBA")
    avatar_bytes = await message.author.display_avatar.with_format("png").read()

    with Image.open(io.BytesIO(avatar_bytes)) as avatar:
        avatar = avatar.convert("RGBA").resize((200, 200))
        avatar = ImageOps.grayscale(avatar).convert("RGBA")
        background.paste(avatar, (20, 20), avatar)

    background = Image.alpha_composite(background, foreground)
    draw = ImageDraw.Draw(background)

    try:
        font_big = ImageFont.truetype(font_path, 24)
        font_quote_small = ImageFont.truetype(font_path, 20)
        font_small = ImageFont.truetype(font_path, 16)
        font_body = ImageFont.truetype(font_path, 18)
        font_display = ImageFont.truetype(font_path, 20)
    except Exception as e:
        print(f"Font error: {e}. Using default.")
        font_big = ImageFont.load_default()
        font_quote_small = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_display = ImageFont.load_default()

    display_name_is_ascii = not any(ord(char) > 127 for char in message.author.display_name)
    display_name_text = f"- {message.author.display_name if display_name_is_ascii else message.author.name}"
    username_text = f"@{message.author.name}"
    show_username = display_name_is_ascii

    original_content = message.content.strip() or "[Embed or media content]"
    content_text = original_content
    content_text = content_text.replace('\n', ' ')
    content_text = content_text.replace('"', '\\"')
    had_non_ascii = any(ord(char) > 127 for char in original_content)
    content_text = unicodedata.normalize('NFKD', content_text)
    content_text = content_text.encode('ascii', 'ignore').decode('ascii')
    content_text = f'"{content_text}"'

    bg_width, bg_height = background.size
    text_x = 250
    text_y = 35
    max_text_width = min(400, bg_width - text_x - 30)
    footer_y = bg_height - 44

    quote_font_size = 24
    quote_font = font_big
    lines = wrap_text(content_text, draw, quote_font, max_text_width)

    if len(lines) > 4:
        quote_font_size = max(12, 24 - 4 * (len(lines) - 4))
        quote_font = ImageFont.truetype(font_path, quote_font_size)
        lines = wrap_text(content_text, draw, quote_font, max_text_width)
        if len(lines) > 4:
            quote_font_size = max(12, 24 - 4 * (len(lines) - 4))
            quote_font = ImageFont.truetype(font_path, quote_font_size)
            lines = wrap_text(content_text, draw, quote_font, max_text_width)

    line_height = int(getattr(quote_font, 'size', quote_font_size) * 1.4)
    max_lines = max(1, (footer_y - text_y) // line_height)
    truncated = False
    if len(lines) > max_lines:
        truncated = True
        if quote_font_size == 12:
            visible = lines[:max_lines]
            ellipsis = "..."
            while ellipsis and draw.textbbox((0, 0), ellipsis, font=quote_font)[2] > max_text_width:
                ellipsis = ellipsis[:-1]

            last = visible[-1]
            if ellipsis:
                while last and draw.textbbox((0, 0), last + ellipsis, font=quote_font)[2] > max_text_width:
                    last = last[:-1]
                last = last.rstrip()
                if not last:
                    visible[-1] = ellipsis
                else:
                    visible[-1] = last + ellipsis
            else:
                while last and draw.textbbox((0, 0), last, font=quote_font)[2] > max_text_width:
                    last = last[:-1]
                visible[-1] = last

            lines = visible
        else:
            lines = lines[:max_lines]

    for line in lines:
        draw.text((text_x, text_y), line, fill=(255, 255, 255), font=quote_font)
        text_y += line_height

    display_bbox = draw.textbbox((0, 0), display_name_text, font=font_display)
    footer_y = bg_height - 44
    username_y = footer_y - 4
    display_y = username_y

    draw.text((text_x, display_y), display_name_text, fill=(255, 255, 255), font=font_display)
    if show_username:
        username_bbox = draw.textbbox((0, 0), username_text, font=font_small)
        username_x = bg_width - 30 - (username_bbox[2] - username_bbox[0])
        draw.text((username_x, username_y), username_text, fill=(100, 100, 100), font=font_small)

    notices = []
    if 'had_non_ascii' in locals() and had_non_ascii:
        notices.append("ASCII Error")
    if truncated:
        notices.append("Size Error")

    if notices:
        notice_text = " | ".join(notices)
        try:
            notice_font = ImageFont.truetype(font_path, 12)
        except Exception:
            notice_font = font_small
        notice_color = (255, 60, 60)
        notice_x = 25
        notice_y = footer_y - -5
        draw.text((notice_x, notice_y), notice_text, fill=notice_color, font=notice_font)

    buffer = io.BytesIO()
    background.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="quote.png")
