"""Banner creation and styling utilities.

This module owns the banner image generation logic directly and does not depend on
helper.py or main.py being loaded at runtime.
"""

from __future__ import annotations

import io
import json
import os
import random
from pathlib import Path

import discord
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT_DIR = Path(__file__).resolve().parent.parent
UTILS_DIR = Path(__file__).resolve().parent
BANNERS_FILE = ROOT_DIR / 'banners.json'


def load_user_settings() -> dict:
    user_file = ROOT_DIR / 'user.json'
    if not user_file.exists():
        return {'users': {}}
    try:
        with user_file.open('r', encoding='utf-8') as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {'users': {}}


def save_user_settings(data: dict) -> None:
    user_file = ROOT_DIR / 'user.json'
    with user_file.open('w', encoding='utf-8') as handle:
        json.dump(data, handle, indent=4, ensure_ascii=False)


def get_user_settings_entry(settings: dict, user_id: str) -> dict:
    if 'users' not in settings or not isinstance(settings['users'], dict):
        settings['users'] = {}

    user_key = str(user_id)
    user_settings = settings['users'].get(user_key)
    if not isinstance(user_settings, dict):
        user_settings = {}
        settings['users'][user_key] = user_settings
    return user_settings


def get_user_blacklist() -> set[int]:
    raw_blacklist = os.getenv('USER_BLACKLIST', '')
    return {int(value.strip()) for value in raw_blacklist.split(',') if value.strip().isdigit()}


def load_banner_definitions() -> dict:
    if BANNERS_FILE.exists():
        try:
            with BANNERS_FILE.open('r', encoding='utf-8') as handle:
                return json.load(handle)
        except Exception:
            return {}
    return {}


def get_banner_style_entry(style_name: str) -> dict | None:
    if not style_name:
        return None
    defs = load_banner_definitions()
    if style_name in defs:
        return defs.get(style_name)
    key = str(style_name).strip().lower()
    for k, v in defs.items():
        if k and k.lower() == key:
            return v
    return None


def normalize_banner_style(style: str | None) -> str:
    name = str(style or 'normal').strip().lower()
    defs = load_banner_definitions()
    if name == 'random':
        keys = list(defs.keys())
        if keys:
            return random.choice(keys)
        return 'normal'
    if name in defs:
        return name

    aliases = {
        'normal': 'normal',
        'alt': 'alt',
        'alternate': 'alt',
        '1000': '1000',
        'milestone': '1000',
        'milestone1000': '1000',
        'admin': 'admin',
        'administrator': 'admin',
    }
    mapped = aliases.get(name)
    if mapped and mapped in defs:
        return mapped
    if defs:
        return next(iter(defs.keys()))
    return 'normal'


USER_COLOR_OPTIONS = ["random"] + [name for name in ["white", "black", "red", "blue", "green", "yellow", "purple", "orange", "brown"] if name != "black" and name != "random"]


def get_user_color(user_id: str) -> str:
    settings = load_user_settings()
    return get_user_settings_entry(settings, user_id).get('color', 'white')


def resolve_user_color_name(color_name: str | None) -> str:
    cleaned = str(color_name or 'white').strip().lower()
    if cleaned == 'random':
        palette = [name for name in USER_COLOR_OPTIONS if name != 'random']
        return random.choice(palette) if palette else 'white'
    valid = {'white', 'black', 'red', 'blue', 'green', 'yellow', 'purple', 'orange', 'brown'}
    return cleaned if cleaned in valid else 'white'


def get_user_color_value(user_id: str) -> discord.Color:
    settings = load_user_settings()
    user_settings = get_user_settings_entry(settings, user_id)
    color_name = resolve_user_color_name(user_settings.get('color', 'white'))
    color_map = {
        'white': discord.Color.light_gray(),
        'black': discord.Color.dark_gray(),
        'red': discord.Color.red(),
        'blue': discord.Color.blue(),
        'green': discord.Color.green(),
        'yellow': discord.Color.gold(),
        'purple': discord.Color.purple(),
        'orange': discord.Color.orange(),
        'brown': discord.Color.dark_orange(),
    }
    return color_map.get(color_name, discord.Color.blurple())


def format_banner_style_label(style: str | None) -> str:
    name = str(style or 'normal').strip().lower()
    if name == 'random':
        return 'Random'
    normalized = normalize_banner_style(name)
    entry = get_banner_style_entry(normalized)
    if entry and isinstance(entry.get('label'), str):
        return entry.get('label')
    return normalized.title()


def get_banner_search_matches(definitions: dict, query: str) -> list[str]:
    q = (query or '').strip().lower()
    if not q:
        return list(definitions.keys())

    category_prefix = 'category:'
    target = q
    if q.startswith(category_prefix):
        target = q[len(category_prefix):].strip()

    matches = []
    for name in definitions.keys():
        entry = definitions.get(name) or {}
        category = str(entry.get('category') or '').strip()
        label = str(entry.get('label') or '').strip()
        description = str(entry.get('desc') or '').strip()
        tokens = [
            name,
            name.replace('_', ' '),
            category,
            category.lower(),
            label,
            description,
        ]
        haystack = ' '.join(token for token in tokens if token).lower()

        if q.startswith(category_prefix):
            if target and target in category.lower():
                matches.append(name)
            continue

        if target and (target in haystack or target in name.lower() or target in category.lower()):
            matches.append(name)

    return matches


def get_user_banner_style(user_id: str) -> str:
    settings = load_user_settings()
    return normalize_banner_style(get_user_settings_entry(settings, user_id).get('banner_style', 'normal'))


def ensure_user_banner_assigned(user_id: str) -> str:
    settings = load_user_settings()
    entry = get_user_settings_entry(settings, user_id)
    style = entry.get('banner_style', None)
    if style is None:
        defs = load_banner_definitions()
        keys = [k for k in defs.keys() if k and k.lower() != 'random']
        chosen = random.choice(keys) if keys else 'normal'
        entry['banner_style'] = chosen
        save_user_settings(settings)
        return normalize_banner_style(chosen)
    return normalize_banner_style(style)


def get_banner_asset_path(kind: str, style: str, *, allow_legacy: bool = True) -> str | None:
    base_dir = str(ROOT_DIR)
    banner_dir = os.path.join(base_dir, 'banners')
    style_name = normalize_banner_style(style)
    kind_name = (str(kind) or '').strip().lower()

    candidates = [
        os.path.join(base_dir, 'newbanners', f'{kind_name}.png'),
        os.path.join(base_dir, 'newbanners', f'{kind_name}_{style_name}.png'),
        os.path.join(banner_dir, f'{kind_name}.png'),
        os.path.join(banner_dir, f'{kind_name}_{style_name}.png'),
        os.path.join(base_dir, f'{kind_name}.png'),
        os.path.join(base_dir, f'{kind_name}_{style_name}.png'),
    ]

    if allow_legacy:
        legacy_names = {
            'welcome_bg': ['welcome_bg.png', 'welcome_bg_normal.png'],
            'goodbye_bg': ['goodbye_bg.png', 'goodbye_bg_normal.png'],
            'levelup_bg': ['levelup_bg.png', 'levelup_bg_normal.png'],
            'quest_bg': ['quest_bg.png', 'quest_bg_normal.png'],
        }
        for legacy_name in legacy_names.get(kind, []):
            candidates.append(os.path.join(base_dir, legacy_name))

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    generic = os.path.join(base_dir, 'newbanners', 'banner_size.png')
    if os.path.exists(generic):
        return generic
    return None


def apply_named_overlay(background: Image.Image, overlay_name: str) -> Image.Image:
    if not overlay_name:
        return background
    candidates = []
    if os.path.isabs(overlay_name):
        candidates.append(overlay_name)
    else:
        candidates.append(os.path.join(ROOT_DIR, overlay_name))
        candidates.append(os.path.join(ROOT_DIR, 'newbanners', overlay_name))
        if overlay_name.endswith('~'):
            on = overlay_name.rstrip('~')
            candidates.append(os.path.join(ROOT_DIR, on))
            candidates.append(os.path.join(ROOT_DIR, 'newbanners', on))
        name, ext = os.path.splitext(overlay_name)
        if not ext:
            candidates.append(os.path.join(ROOT_DIR, f'{overlay_name}.png'))
            candidates.append(os.path.join(ROOT_DIR, 'newbanners', f'{overlay_name}.png'))

    ov_path = None
    for cand in candidates:
        if cand and os.path.exists(cand):
            ov_path = cand
            break
    if not ov_path:
        return background
    try:
        overlay = Image.open(ov_path).convert('RGBA')
        if overlay.size != background.size:
            overlay = overlay.resize(background.size)
        background = Image.alpha_composite(background, overlay)
    except Exception:
        pass
    return background


def assemble_banner_image(bg_path: str, style_name: str):
    background = Image.open(bg_path).convert('RGBA')
    entry = get_banner_style_entry(style_name)
    if entry and isinstance(entry.get('file'), str):
        style_file = entry.get('file')
        candidates = []
        if os.path.isabs(style_file):
            candidates.append(style_file)
        else:
            candidates.append(os.path.join(ROOT_DIR, style_file))
            candidates.append(os.path.join(ROOT_DIR, 'newbanners', style_file))
            if style_file.endswith('~'):
                sf = style_file.rstrip('~')
                candidates.append(os.path.join(ROOT_DIR, sf))
                candidates.append(os.path.join(ROOT_DIR, 'newbanners', sf))
            name, ext = os.path.splitext(style_file)
            if not ext:
                candidates.append(os.path.join(ROOT_DIR, f'{style_file}.png'))
                candidates.append(os.path.join(ROOT_DIR, 'newbanners', f'{style_file}.png'))

        style_path = None
        for cand in candidates:
            if cand and os.path.exists(cand):
                style_path = cand
                break
        if style_path:
            try:
                overlay = Image.open(style_path).convert('RGBA')
                target_w, target_h = 680, 382
                bg_w, bg_h = background.size
                if overlay.size != (target_w, target_h):
                    overlay_resized = overlay.resize((target_w, target_h))
                else:
                    overlay_resized = overlay
                layer = Image.new('RGBA', background.size, (0, 0, 0, 0))
                layer.paste(overlay_resized, ((bg_w - target_w) // 2, (bg_h - target_h) // 2), overlay_resized)
                background = Image.alpha_composite(background, layer)
            except Exception:
                pass

    overlays = []
    if entry:
        if isinstance(entry.get('mg'), str):
            overlays.append(entry.get('mg'))
        if isinstance(entry.get('overlay'), str):
            overlays.append(entry.get('overlay'))
        if isinstance(entry.get('overlay'), list):
            overlays.extend([p for p in entry.get('overlay') if isinstance(p, str)])

    for ov in overlays:
        candidates = []
        if os.path.isabs(ov):
            candidates.append(ov)
        else:
            candidates.append(os.path.join(ROOT_DIR, ov))
            candidates.append(os.path.join(ROOT_DIR, 'newbanners', ov))
            if ov.endswith('~'):
                ov2 = ov.rstrip('~')
                candidates.append(os.path.join(ROOT_DIR, ov2))
                candidates.append(os.path.join(ROOT_DIR, 'newbanners', ov2))
            name, ext = os.path.splitext(ov)
            if not ext:
                candidates.append(os.path.join(ROOT_DIR, f'{ov}.png'))
                candidates.append(os.path.join(ROOT_DIR, 'newbanners', f'{ov}.png'))
        ov_path = None
        for cand in candidates:
            if cand and os.path.exists(cand):
                ov_path = cand
                break
        if ov_path:
            try:
                overlay = Image.open(ov_path).convert('RGBA')
                if overlay.size != background.size:
                    overlay = overlay.resize(background.size)
                background = Image.alpha_composite(background, overlay)
            except Exception:
                pass
    return background, entry


def pick_text_color(entry: dict | None, background: Image.Image):
    if entry and entry.get('textcolor'):
        c = str(entry.get('textcolor')).lower()
        if c in {'white', '#fff', '#ffffff'}:
            return (255, 255, 255)
        if c in {'black', '#000', '#000000'}:
            return (0, 0, 0)
        if c.startswith('#') and len(c) == 7:
            try:
                return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
            except Exception:
                pass
    region = background.convert('RGB')
    pixels = region.resize((1, 1))
    return tuple(pixels.getdata()[0])


def get_opposite_color(color):
    return tuple(255 - c for c in color)


def format_banner_limit_text(value: str | None, limit: int = 18, fallback: str = 'DM') -> str:
    text = str(value).strip() if value is not None else ''
    safe = text.encode('ascii', 'ignore').decode('ascii').strip()
    text = safe if safe else fallback
    if limit <= 0:
        return ''
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + '...'


def get_banner_name(member: discord.abc.User | discord.Member) -> str:
    display_name = member.display_name
    if any(ord(char) > 127 for char in display_name):
        return member.name
    return display_name


def format_banner_username(name: str, limit: int = 17) -> str:
    if len(name) <= limit:
        return name
    return name[:limit] + '...'


def resolve_font_path(base_path: str | os.PathLike[str], preferred_names: tuple[str, ...] = ('Minecraft.ttf', 'NotoSans-Regular.ttf', 'NotoSansMono-Regular.ttf')) -> str | None:
    base_path = str(base_path)
    for name in preferred_names:
        candidate = os.path.join(base_path, name)
        if os.path.exists(candidate):
            return candidate
    for root, _, files in os.walk(base_path):
        for name in files:
            if name.lower().endswith('.ttf') or name.lower().endswith('.otf'):
                return os.path.join(root, name)
    return None


def wrap_text(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int, emoji_font: ImageFont.ImageFont | None = None) -> list[str]:
    lines = []
    for paragraph in text.splitlines() or ['']:
        if not paragraph:
            lines.append('')
            continue
        words = paragraph.split(' ')
        if not words:
            lines.append('')
            continue
        current_line = words[0]
        for word in words[1:]:
            test_line = f'{current_line} {word}'
            width = draw.textbbox((0, 0), test_line, font=font)[2]
            if width <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
    return lines


async def create_banner_preview(member: discord.Member, kind: str = 'welcome', style_override: str | None = None, quest_text: str | None = None):
    kind_name = str(kind or 'welcome').lower()
    if kind_name in {'lvl', 'level', 'levelup'}:
        style_name = normalize_banner_style(style_override or get_user_banner_style(str(member.id)))
        bg_path = get_banner_asset_path('levelup_bg', style_name)
        if not bg_path or not os.path.exists(bg_path):
            return None
        background, entry = assemble_banner_image(bg_path, style_name)
        background = apply_named_overlay(background, 'levelup_mg.png')
        avatar_bytes = await member.display_avatar.with_format('png').read()
        center_x = background.width // 2
        with Image.open(io.BytesIO(avatar_bytes)) as avatar:
            avatar = avatar.convert('RGBA').resize((120, 120))
            background.paste(avatar, (center_x - 60, 40))
        draw = ImageDraw.Draw(background)
        font_path = resolve_font_path(ROOT_DIR)
        try:
            font = ImageFont.truetype(font_path, 25)
        except Exception:
            font = ImageFont.load_default()
        text_color = pick_text_color(entry, background)
        stroke_color = get_opposite_color(text_color)
        draw.text((center_x, 190), f"{format_banner_username(get_banner_name(member))} you are now Level 1!", fill=text_color, font=font, anchor='mm', stroke_fill=stroke_color, stroke_width=2)
        buffer = io.BytesIO(); background.save(buffer, format='PNG'); buffer.seek(0)
        return discord.File(buffer, filename='banner_level_preview.png')

    if kind_name in {'quest', 'quest_bg'}:
        style_name = normalize_banner_style(style_override or get_user_banner_style(str(member.id)))
        bg_path = get_banner_asset_path('quest_bg', style_name)
        if not bg_path or not os.path.exists(bg_path):
            return None
        background, entry = assemble_banner_image(bg_path, style_name)
        background = apply_named_overlay(background, 'quest_mg.png')
        avatar_bytes = await member.display_avatar.with_format('png').read()
        with Image.open(io.BytesIO(avatar_bytes)) as avatar:
            avatar = avatar.convert('RGBA').resize((100, 100))
            avatar_x = max(480, background.width - 100 - 40)
            background.paste(avatar, (avatar_x, 40))
        draw = ImageDraw.Draw(background)
        font_path = resolve_font_path(ROOT_DIR)
        try:
            font_big = ImageFont.truetype(font_path, 32)
            font_medium = ImageFont.truetype(font_path, 18)
            font_small = ImageFont.truetype(font_path, 14)
        except Exception:
            font_big = ImageFont.load_default(); font_medium = ImageFont.load_default(); font_small = ImageFont.load_default()
        text_color = pick_text_color(entry, background)
        stroke_color = get_opposite_color(text_color)
        draw.text((35, background.height // 2 - 40), 'Quest Complete!', fill=text_color, font=font_big, stroke_fill=stroke_color, stroke_width=2)
        draw.text((35, background.height // 2 + 2), format_banner_username(get_banner_name(member), 22), fill=text_color, font=font_medium, stroke_fill=stroke_color, stroke_width=2)
        quest_line = quest_text if quest_text else 'You completed: <quest description>'
        wrapped = wrap_text(quest_line, draw, font_small, background.width - 80)
        for i, line in enumerate(wrapped[-2:]):
            draw.text((35, background.height - 44 + (i * 18)), line, fill=(200, 200, 200), font=font_small)
        buffer = io.BytesIO(); background.save(buffer, format='PNG'); buffer.seek(0)
        return discord.File(buffer, filename='banner_quest_preview.png')

    if kind_name == 'goodbye':
        style_name = normalize_banner_style(style_override or get_user_banner_style(str(member.id)))
        bg_path = get_banner_asset_path('goodbye_bg', style_name)
        if not bg_path or not os.path.exists(bg_path):
            bg_path = get_banner_asset_path('welcome_bg', style_name)
        if not bg_path or not os.path.exists(bg_path):
            return None
        background, entry = assemble_banner_image(bg_path, style_name)
        background = apply_named_overlay(background, 'welcome_mg.png')
        avatar_bytes = await member.display_avatar.with_format('png').read()
        with Image.open(io.BytesIO(avatar_bytes)) as avatar:
            avatar = avatar.convert('RGBA').resize((160, 160))
            background.paste(avatar, (480, 40))
        draw = ImageDraw.Draw(background)
        font_path = resolve_font_path(ROOT_DIR)
        try:
            font_big = ImageFont.truetype(font_path, 35)
            font_small = ImageFont.truetype(font_path, 15)
            font_medium = ImageFont.truetype(font_path, 25)
        except Exception:
            font_big = ImageFont.load_default(); font_small = ImageFont.load_default(); font_medium = ImageFont.load_default()
        text_color = pick_text_color(entry, background)
        stroke_color = get_opposite_color(text_color)
        gray_color = tuple(max(0, min(255, int(c * 0.8))) for c in text_color)
        draw.text((35, 30), 'Goodbye', fill=text_color, font=font_big, stroke_fill=stroke_color, stroke_width=2)
        draw.text((35, 80), format_banner_username(get_banner_name(member), 25), fill=text_color, font=font_medium, stroke_fill=stroke_color, stroke_width=2)
        guild = getattr(member, 'guild', None)
        guild_name = format_banner_limit_text((getattr(guild, 'name', None) or 'DM') if guild is not None else 'DM', 35)
        draw.text((35, 140), f'from {guild_name}', fill=gray_color, font=font_small, stroke_fill=get_opposite_color(gray_color), stroke_width=1)
        draw.text((35, 170), 'We hope to see you again soon!', fill=gray_color, font=font_small, stroke_fill=get_opposite_color(gray_color), stroke_width=1)
        buffer = io.BytesIO(); background.save(buffer, format='PNG'); buffer.seek(0)
        return discord.File(buffer, filename='banner_goodbye_preview.png')

    style_name = normalize_banner_style(style_override or get_user_banner_style(str(member.id)))
    bg_path = get_banner_asset_path('welcome_bg', style_name)
    if not bg_path or not os.path.exists(bg_path):
        return None
    background, entry = assemble_banner_image(bg_path, style_name)
    background = apply_named_overlay(background, 'welcome_mg.png')
    avatar_bytes = await member.display_avatar.with_format('png').read()
    with Image.open(io.BytesIO(avatar_bytes)) as avatar:
        avatar = avatar.convert('RGBA').resize((160, 160))
        background.paste(avatar, (480, 40))
    draw = ImageDraw.Draw(background)
    font_path = resolve_font_path(ROOT_DIR)
    try:
        font_big = ImageFont.truetype(font_path, 35)
        font_small = ImageFont.truetype(font_path, 15)
        font_medium = ImageFont.truetype(font_path, 25)
    except Exception:
        font_big = ImageFont.load_default(); font_small = ImageFont.load_default(); font_medium = ImageFont.load_default()
    text_color = pick_text_color(entry, background)
    stroke_color = get_opposite_color(text_color)
    gray_color = tuple(max(0, min(255, int(c * 0.8))) for c in text_color)
    draw.text((35, 30), 'Welcome', fill=text_color, font=font_big, stroke_fill=stroke_color, stroke_width=2)
    draw.text((35, 80), format_banner_username(get_banner_name(member), 25), fill=text_color, font=font_medium, stroke_fill=stroke_color, stroke_width=2)
    guild = getattr(member, 'guild', None)
    guild_name = format_banner_limit_text((getattr(guild, 'name', None) or 'DM') if guild is not None else 'DM', 35)
    draw.text((35, 140), f'to the {guild_name} server', fill=gray_color, font=font_small, stroke_fill=get_opposite_color(gray_color), stroke_width=1)
    buffer = io.BytesIO(); background.save(buffer, format='PNG'); buffer.seek(0)
    return discord.File(buffer, filename='banner_welcome_preview.png')


create_welcome_card = create_banner_preview
create_goodbye_card = create_banner_preview


def format_quote_content(value: str | None) -> str:
    return str(value or '').strip() or 'Quote'


async def create_quote_card(message: discord.Message, viewer_id: int | None = None):
    if message is None:
        return None
    bg_path = UTILS_DIR / 'Quote_bg.png'
    fg_path = UTILS_DIR / 'Quote_fg.png'
    if not bg_path.exists() or not fg_path.exists():
        return None
    background = Image.open(bg_path).convert('RGBA')
    foreground = Image.open(fg_path).convert('RGBA')
    try:
        avatar_bytes = await message.author.display_avatar.with_format('png').read()
        with Image.open(io.BytesIO(avatar_bytes)) as avatar:
            avatar = avatar.convert('RGBA').resize((360, 360))
            avatar = ImageOps.grayscale(avatar).convert('RGBA')
            background.paste(avatar, (20, 20), avatar)
    except Exception:
        pass
    background = Image.alpha_composite(background, foreground)
    draw = ImageDraw.Draw(background)
    font_path = resolve_font_path(UTILS_DIR) or resolve_font_path(ROOT_DIR)
    if font_path:
        try:
            font_big = ImageFont.truetype(font_path, 24)
            font_small = ImageFont.truetype(font_path, 16)
        except Exception:
            font_big = ImageFont.load_default(); font_small = ImageFont.load_default()
    else:
        font_big = ImageFont.load_default(); font_small = ImageFont.load_default()
    content_text = str(getattr(message, 'content', '') or '').strip() or 'Quote'
    if len(content_text) > 180:
        content_text = content_text[:177] + '...'
    text_x = 300
    text_y = 35
    max_text_width = max(200, background.width - text_x - 40)
    lines = wrap_text(f'"{content_text}"', draw, font_big, max_text_width)
    if len(lines) > 4:
        lines = wrap_text(f'"{content_text}"', draw, font_small, max_text_width)
    footer_y = background.height - 44
    line_height = int(max(font_big.size, 18) * 1.4)
    visible_lines = lines[:max(1, (footer_y - text_y) // line_height)]
    for idx, line in enumerate(visible_lines):
        draw.text((text_x, text_y + idx * line_height), line, fill=(255, 255, 255), font=font_big)
    author_name = getattr(message.author, 'display_name', None) or getattr(message.author, 'name', 'User')
    author_text = f'- {author_name}'
    draw.text((text_x, background.height - 72), author_text, fill=(220, 220, 220), font=font_small)
    buffer = io.BytesIO(); background.save(buffer, format='PNG'); buffer.seek(0)
    return discord.File(buffer, filename='quote_card.png')


__all__ = [
    'apply_named_overlay',
    'assemble_banner_image',
    'format_banner_style_label',
    'get_banner_search_matches',
    'get_banner_style_entry',
    'load_banner_definitions',
    'normalize_banner_style',
    'get_user_banner_style',
    'ensure_user_banner_assigned',
    'get_banner_asset_path',
    'get_banner_name',
    'get_user_color',
    'resolve_user_color_name',
    'get_user_color_value',
    'format_banner_limit_text',
    'format_banner_username',
    'resolve_font_path',
    'wrap_text',
    'pick_text_color',
    'get_opposite_color',
    'create_welcome_card',
    'create_goodbye_card',
    'create_banner_preview',
    'format_quote_content',
    'create_quote_card',
]
