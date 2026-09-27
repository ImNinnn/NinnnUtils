"""Banner creation and styling utilities: welcome/goodbye/level-up cards, banner styles and quote cards."""

from __future__ import annotations
import pilmoji
import aiohttp
import io
import json
import os
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from PIL import Image, ImageDraw, ImageFont, ImageOps

from save import load_user_settings, save_user_settings
from utils.user_settings import (  # noqa: F401  (re-exported for older callers)
    USER_COLOR_OPTIONS, get_user_color, get_user_color_value, get_user_settings_entry,
    parse_utc_offset, resolve_user_color_name,
)

try:
    from pilmoji import Pilmoji
    from pilmoji.source import Twemoji, DiscordEmojiSourceMixin
    _PILMOJI_AVAILABLE = True
except Exception:
    Pilmoji = None
    Twemoji = None
    DiscordEmojiSourceMixin = None
    _PILMOJI_AVAILABLE = False
ROOT_DIR = Path(__file__).resolve().parent.parent
UTILS_DIR = Path(__file__).resolve().parent
BANNERS_FILE = ROOT_DIR / 'banners.json'
# Dynamic quote text scaling: the quote is rendered at the largest size in
# this range whose wrapped lines still fit the available space, so a short
# quote stays big and a long one shrinks - continuously, not just a
# big/small toggle - instead of ever being cut off. There's no separate
# character limit any more: any length is attempted, and this range (plus
# the last-resort line truncation in create_quote_card) is what keeps it
# from ever overflowing or crashing.
QUOTE_MAX_FONT_SIZE = 24
QUOTE_MIN_FONT_SIZE = 6


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
    for key in defs:
        if str(key).strip().lower() == name:
            return key

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


MAIN_FONT_NAMES = ('minecraft.ttf',)
UNICODE_FALLBACK_FONT_NAME = 'sevenfifteen.ttf'


def _find_named_file(directory: str | os.PathLike[str], name: str) -> str | None:
    """Case-insensitive lookup of one file in one folder (Linux file names are case-sensitive)."""
    try:
        entries = os.listdir(directory)
    except OSError:
        return None
    for entry in entries:
        if entry.lower() == name.lower():
            path = os.path.join(directory, entry)
            if os.path.isfile(path):
                return path
    return None


def resolve_font_path(
    base_path: str | os.PathLike[str] | None = None,
    preferred_names: tuple[str, ...] = MAIN_FONT_NAMES,
) -> str | None:
    """The main banner font. Looked up by name only: never a random font found elsewhere."""
    folders = [UTILS_DIR]
    if base_path is not None and os.path.abspath(base_path) != os.path.abspath(UTILS_DIR):
        folders.append(base_path)
    for name in preferred_names:
        for folder in folders:
            path = _find_named_file(folder, name)
            if path:
                return path
    return None


def is_emoji_character(char: str) -> bool:
    if not char:
        return False

    codepoint = ord(char)
    if codepoint in {0x200D, 0xFE0F, 0xFE0E, 0x20E3}:
        return True

    return (
        0x1F300 <= codepoint <= 0x1FAFF    # main emoji blocks (covers nearly all recent additions)
        or 0x2600 <= codepoint <= 0x27BF    # misc symbols / dingbats
        or 0x1F1E6 <= codepoint <= 0x1F1FF  # regional indicators (2-letter flags)
        or 0x2190 <= codepoint <= 0x21FF    # arrows (e.g. used in the 15.1 head-shake ZWJ sequences)
        or 0x2300 <= codepoint <= 0x23FF    # misc technical (\u231a\u23f0\u23f3 etc.)
        or 0x25A0 <= codepoint <= 0x25FF    # geometric shapes
        or 0x2B00 <= codepoint <= 0x2BFF    # misc symbols and arrows (\u2b50\u2b1b\u2b1c etc.)
        or 0xE0020 <= codepoint <= 0xE007F  # tag characters (subdivision flags, e.g. Scotland/Wales)
    )


def can_render_glyph(font: ImageFont.ImageFont, char: str) -> bool:
    if not font or not char:
        return False
    try:
        test_image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        test_draw = ImageDraw.Draw(test_image)
        test_draw.text((8, 8), char, fill=(255, 255, 255), font=font, embedded_color=True)
        return test_image.getbbox() is not None
    except Exception:
        return False


_LOCAL_COLOR_EMOJI_FONT_CACHE: dict[str, ImageFont.ImageFont | None] = {}
# Color-bitmap emoji fonts (CBDT/CBLC, which is what Twemoji.ttf builds use)
# only ship a handful of fixed embedded pixel sizes. Asking Pillow for an
# arbitrary size (like the 16/24px used elsewhere for text) raises
# `OSError: invalid pixel size`, so we probe common strike sizes instead of
# assuming one. Pilmoji rescales whatever image we return to the target text
# size anyway, so the exact size we load here doesn't need to match.
_LOCAL_COLOR_EMOJI_FONT_SIZES = (160, 128, 96, 72, 64, 61, 36, 32, 24, 20, 16)
_LOCAL_COLOR_EMOJI_FONT_NAMES = ('Twemoji.ttf', 'NotoColorEmoji.ttf', 'NotoEmoji.ttf')


def _load_local_color_emoji_font(base_path: str | os.PathLike[str]) -> ImageFont.ImageFont | None:
    base_path = str(base_path)
    if base_path in _LOCAL_COLOR_EMOJI_FONT_CACHE:
        return _LOCAL_COLOR_EMOJI_FONT_CACHE[base_path]

    font_path = None
    for name in _LOCAL_COLOR_EMOJI_FONT_NAMES:
        candidate = os.path.join(base_path, name)
        if os.path.exists(candidate):
            font_path = candidate
            break
        found = find_font_file(base_path, name)
        if found:
            font_path = found
            break

    result: ImageFont.ImageFont | None = None
    if font_path:
        # RAQM shaping lets multi-codepoint sequences (flags, ZWJ family/skin
        # tone combos) resolve to their single composed glyph via the font's
        # GSUB table; without it they'd just render as separate glyphs. It's
        # optional here (single-codepoint emoji render fine either way).
        layout_engines: list = []
        raqm_layout = getattr(getattr(ImageFont, 'Layout', None), 'RAQM', None)
        if raqm_layout is not None:
            layout_engines.append(raqm_layout)
        layout_engines.append(None)  # Pillow's default layout engine

        for size in _LOCAL_COLOR_EMOJI_FONT_SIZES:
            for layout in layout_engines:
                try:
                    kwargs = {'layout_engine': layout} if layout is not None else {}
                    font = ImageFont.truetype(font_path, size, **kwargs)
                except Exception:
                    continue
                if can_render_glyph(font, '\U0001F600'):
                    result = font
                    break
            if result:
                break

    _LOCAL_COLOR_EMOJI_FONT_CACHE[base_path] = result
    return result


def resolve_local_color_emoji_font() -> ImageFont.ImageFont | None:
    """Find the bundled color-emoji font (Twemoji.ttf), checking next to
    banners.py first and then the bot's root directory."""
    for base in (UTILS_DIR, ROOT_DIR):
        font = _load_local_color_emoji_font(base)
        if font is not None:
            return font
    return None


_EMOJI_GLYPH_IMAGE_CACHE: dict[str, bytes | None] = {}


def render_emoji_cluster_image(cluster: str, native_font: ImageFont.ImageFont | None = None) -> Image.Image | None:
    """Render a single emoji, or a multi-codepoint emoji sequence (flag, ZWJ
    combo, skin tone, etc.), using the local color-emoji font.

    Returns a cropped RGBA image, or None if the font has no glyph for it
    (e.g. an emoji added to Unicode after this font was built) or no local
    color-emoji font is available at all.
    """
    if not cluster:
        return None
    if native_font is None:
        native_font = resolve_local_color_emoji_font()
    if native_font is None:
        return None

    if cluster in _EMOJI_GLYPH_IMAGE_CACHE:
        cached = _EMOJI_GLYPH_IMAGE_CACHE[cluster]
        return Image.open(io.BytesIO(cached)).convert('RGBA') if cached else None

    try:
        native_size = int(getattr(native_font, 'size', 64) or 64)
        pad = max(4, native_size // 8)
        canvas = Image.new('RGBA', (native_size * (len(cluster) + 1) + pad * 2, native_size * 2 + pad * 2), (0, 0, 0, 0))
        canvas_draw = ImageDraw.Draw(canvas)
        canvas_draw.text((pad, pad), cluster, font=native_font, embedded_color=True)
        ink_bbox = canvas.getbbox()
        cropped = None
        if ink_bbox is not None:
            # Crop to the font's own glyph cell (advance width x ascent+descent)
            # rather than the tight ink-only bbox. Twemoji-style bitmap glyphs
            # are designed to sit in a uniform, roughly-square cell - even
            # non-round shapes (flags, a moose, a goose) use less of that cell's
            # height than a face does. Cropping to ink alone made glyph height
            # vary wildly per emoji, which is what threw off vertical alignment
            # against custom Discord emoji (always drawn at a fixed height) and
            # made some unicode emoji look shifted/clipped within the line.
            try:
                advance = native_font.getlength(cluster)
            except Exception:
                advance = ink_bbox[2] - pad
            try:
                ascent, descent = native_font.getmetrics()
                cell_h = ascent + descent
            except Exception:
                cell_h = native_size
            crop_box = (
                min(pad, ink_bbox[0]),
                min(pad, ink_bbox[1]),
                round(pad + max(advance, ink_bbox[2] - pad)),
                round(pad + max(cell_h, ink_bbox[3] - pad)),
            )
            cropped = canvas.crop(crop_box)
    except Exception:
        cropped = None

    if cropped is None:
        _EMOJI_GLYPH_IMAGE_CACHE[cluster] = None
        return None

    buf = io.BytesIO()
    cropped.save(buf, format='PNG')
    _EMOJI_GLYPH_IMAGE_CACHE[cluster] = buf.getvalue()
    return cropped


if _PILMOJI_AVAILABLE and DiscordEmojiSourceMixin is not None:
    class LocalTwemojiSource(DiscordEmojiSourceMixin):
        """Pilmoji emoji source backed by the bundled local Twemoji.ttf.

        Renders straight from the local color font, which is what actually
        keeps up with newly-added Unicode emoji once you drop in an updated
        Twemoji.ttf. Falls back to the network TwitterEmojiSource (pilmoji's
        default `Twemoji`, which pulls from a third-party CDN proxy) only for
        glyphs the local font doesn't have.
        """

        def __init__(self) -> None:
            super().__init__()
            self._native_font = resolve_local_color_emoji_font()
            self._network_fallback = None  # lazily created; False once known unusable

        def get_emoji(self, emoji: str, /):
            image = render_emoji_cluster_image(emoji, self._native_font)
            if image is not None:
                buf = io.BytesIO()
                image.save(buf, format='PNG')
                buf.seek(0)
                return buf

            if self._network_fallback is None:
                try:
                    self._network_fallback = Twemoji()
                except Exception:
                    self._network_fallback = False

            if not self._network_fallback:
                return None
            try:
                return self._network_fallback.get_emoji(emoji)
            except Exception:
                return None
else:
    LocalTwemojiSource = None


def find_font_file(base_path: str | os.PathLike[str], filename_hint: str | None = None, text: str | None = None) -> str | None:
    base_path = str(base_path)
    fonts_dir = os.path.join(base_path, 'fonts')
    roots = []
    if filename_hint:
        roots.extend([
            os.path.join(base_path, filename_hint),
            os.path.join(fonts_dir, filename_hint),
        ])
    roots.append(fonts_dir)
    roots.append(base_path)

    seen = set()
    preferred_paths: list[str] = []
    fallback_paths: list[str] = []

    for root in roots:
        if not root or root in seen:
            continue
        seen.add(root)
        if os.path.isfile(root):
            if filename_hint and os.path.basename(root).lower() != filename_hint.lower():
                continue
            preferred_paths.append(root)
            continue

        if not os.path.isdir(root):
            continue

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith('.') and d not in {'__pycache__', 'backups'})
            filenames.sort()
            for name in filenames:
                if not name.lower().endswith(('.ttf', '.ttc', '.otf')):
                    continue
                full_path = os.path.join(dirpath, name)
                if full_path in seen:
                    continue
                seen.add(full_path)
                if filename_hint and name.lower() != filename_hint.lower():
                    continue
                if 'notosans' in full_path.lower():
                    preferred_paths.append(full_path)
                else:
                    fallback_paths.append(full_path)

    for candidate in preferred_paths + fallback_paths:
        if not os.path.exists(candidate):
            continue
        try:
            font = ImageFont.truetype(candidate, 12)
            if text:
                characters_to_test = [char for char in text if ord(char) > 127 and not is_emoji_character(char)]
                if characters_to_test and any(can_render_glyph(font, char) for char in characters_to_test):
                    return candidate
            else:
                return candidate
        except Exception:
            continue

    return None


def load_emoji_font(base_path: str | os.PathLike[str], size: int, fallback_font: ImageFont.ImageFont | None = None) -> ImageFont.ImageFont | None:
    base_path = str(base_path)
    candidate_paths = [
        os.path.join(base_path, 'NotoEmoji.ttf'),
        find_font_file(base_path, 'NotoEmoji.ttf'),
    ]
    for font_path in candidate_paths:
        if not font_path or not os.path.exists(font_path):
            continue
        try:
            font = ImageFont.truetype(font_path, size)
            if can_render_glyph(font, '😀'):
                return font
        except Exception:
            continue
    return fallback_font


def load_text_font(
    base_path: str | os.PathLike[str],
    text: str,
    size: int,
    fallback_font: ImageFont.ImageFont | None = None,
) -> ImageFont.ImageFont | None:
    if not text:
        return fallback_font

    # Use the single bundled Unicode fallback instead of searching through
    # the old collection of Noto fonts.
    if not any(ord(char) > 127 and not is_emoji_character(char) for char in text):
        return fallback_font

    font_path = find_font_file(base_path, UNICODE_FALLBACK_FONT_NAME, text=text)
    if not font_path:
        return fallback_font

    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        return fallback_font


def resolve_replacement_font(text: str, size: int, fallback_font: ImageFont.ImageFont | None) -> ImageFont.ImageFont | None:
    """Pick a Unicode-capable font when `text` contains characters the base font can't render."""
    for base in (UTILS_DIR, ROOT_DIR):
        font = load_text_font(base, text, size, fallback_font)
        if font is not fallback_font:
            return font
    return fallback_font


def resolve_emoji_font(size: int, fallback_font: ImageFont.ImageFont | None = None) -> ImageFont.ImageFont | None:
    for base in (UTILS_DIR, ROOT_DIR):
        font = load_emoji_font(base, size, None)
        if font is not None:
            return font
    return fallback_font


def measure_text_width(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, emoji_font: ImageFont.ImageFont | None = None) -> int:
    # Treat custom Discord emoji tags like `<:name:id>` as single glyphs with
    # approximate width equal to the font size (or emoji_font size when available).
    # Also enlarge normal Unicode emoji glyph widths slightly to account for
    # pilmoji's color emoji images which can be wider than the text bbox.
    EMOJI_WIDTH_MULTIPLIER = 1.25
    pattern = re.compile(r'(<a?:[A-Za-z0-9_]+:(\d+)>)')
    width = 0
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            segment = text[pos:m.start()]
            try:
                bbox = draw.textbbox((0, 0), segment, font=font)
                width += bbox[2] - bbox[0]
            except Exception:
                for ch in segment:
                    current_font = emoji_font if emoji_font and is_emoji_character(ch) else font
                    bbox = draw.textbbox((0, 0), ch, font=current_font)
                    w = bbox[2] - bbox[0]
                    if is_emoji_character(ch):
                        w = int(w * EMOJI_WIDTH_MULTIPLIER)
                    width += w
        # custom emoji tag
        glyph_w = getattr(emoji_font, 'size', None) or getattr(font, 'size', 18)
        width += int(glyph_w)
        pos = m.end()
    if pos < len(text):
        tail = text[pos:]
        try:
            bbox = draw.textbbox((0, 0), tail, font=font)
            tail_w = bbox[2] - bbox[0]
            # approximate extra width for emoji characters in the tail
            extra = sum(int((getattr(emoji_font, 'size', 0) or getattr(font, 'size', 0)) * (EMOJI_WIDTH_MULTIPLIER - 1)) for ch in tail if is_emoji_character(ch))
            width += tail_w + extra
        except Exception:
            for ch in tail:
                current_font = emoji_font if emoji_font and is_emoji_character(ch) else font
                bbox = draw.textbbox((0, 0), ch, font=current_font)
                w = bbox[2] - bbox[0]
                if is_emoji_character(ch):
                    w = int(w * EMOJI_WIDTH_MULTIPLIER)
                width += w
    return width


_ZWJ_CHAR = '\u200d'
_VARIATION_SELECTOR_CHARS = {'\ufe0f', '\ufe0e'}


def _split_emoji_clusters(text: str) -> list[str]:
    """Split `text` into a list of clusters, where each element is either one
    complete emoji (including any ZWJ-joined sequence, variation selector,
    skin tone modifier, or regional-indicator flag pair - grouped so it
    renders as a single glyph) or a single plain character.
    """
    clusters: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        cp = ord(ch)
        if is_emoji_character(ch) and ch != _ZWJ_CHAR and ch not in _VARIATION_SELECTOR_CHARS:
            j = i + 1
            # Regional indicator pair (2-letter flag).
            if 0x1F1E6 <= cp <= 0x1F1FF and j < n and 0x1F1E6 <= ord(text[j]) <= 0x1F1FF:
                j += 1
            # Absorb trailing variation selectors, skin tone modifiers, tag
            # characters, and ZWJ-joined continuations into the same cluster.
            while j < n:
                cp2 = ord(text[j])
                if text[j] in _VARIATION_SELECTOR_CHARS or 0x1F3FB <= cp2 <= 0x1F3FF or 0xE0020 <= cp2 <= 0xE007F:
                    j += 1
                    continue
                if text[j] == _ZWJ_CHAR and j + 1 < n and is_emoji_character(text[j + 1]):
                    j += 2
                    continue
                break
            clusters.append(text[i:j])
            i = j
        else:
            clusters.append(ch)
            i += 1
    return clusters


def _text_has_non_emoji_ink(text: str) -> bool:
    """True if `text` has at least one character that would draw real glyph
    ink (not whitespace, not a unicode emoji). See _draw_pure_emoji_segment
    for why this matters."""
    for ch in text or '':
        if ch.isspace() or is_emoji_character(ch):
            continue
        return True
    return False


def _draw_pure_emoji_segment(img: Image.Image, xy: tuple[int, int], text: str, font: ImageFont.ImageFont, fill=(255, 255, 255)) -> int:
    """Draw a text segment made up of only unicode emoji (and/or whitespace)
    by pasting each emoji cluster straight from the local color-emoji font,
    and return the pixel width consumed.

    Pilmoji is deliberately NOT used for this case. Internally, pilmoji
    reserves layout room for each emoji by substituting spaces for it, then
    asks Pillow to measure that substituted line to work out where to paste
    the emoji image. When a segment is *entirely* emoji, that substituted
    line is 100% whitespace - and Pillow's text-mask offset for an
    all-whitespace string with anchor="la" comes back as roughly the font's
    ascent instead of 0. Pilmoji adds that straight into the paste position,
    so a plain emoji sitting right next to a custom server emoji tag (which
    is exactly what collapses to an all-whitespace segment) ends up pasted
    far too low. Confirmed directly against pilmoji 2.0.5's own getmask2
    call. Rendering these ourselves sidesteps the bug entirely.
    """
    draw = ImageDraw.Draw(img)
    start_x, y = xy
    x = start_x
    target_px = int(getattr(font, 'size', 18) or 18)
    native_font = resolve_local_color_emoji_font()
    for cluster in _split_emoji_clusters(text):
        if cluster.isspace():
            try:
                w = int(draw.textlength(cluster, font=font))
            except Exception:
                w = max(1, round(target_px * 0.3)) * len(cluster)
            x += w
            continue
        glyph_image = render_emoji_cluster_image(cluster, native_font) if is_emoji_character(cluster[0]) else None
        if glyph_image is not None:
            w = max(1, round(glyph_image.width * (target_px / float(glyph_image.height or target_px))))
            resized = glyph_image.resize((w, target_px), resample=Image.LANCZOS)
            img.paste(resized, (int(x), int(y)), resized)
            x += w
            continue
        # Local font has no glyph for this cluster - draw with the base font
        # (likely a missing-glyph box, but keeps layout consistent instead of
        # reintroducing pilmoji's broken offset for this exact case).
        try:
            draw.text((x, y), cluster, fill=fill, font=font)
            bbox = draw.textbbox((0, 0), cluster, font=font)
            x += bbox[2] - bbox[0]
        except Exception:
            x += target_px
    return int(x - start_x)


def draw_text_with_font_fallback(target: Image.Image | ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont, emoji_font: ImageFont.ImageFont | None = None, fill=(255, 255, 255)) -> int:
    """Draw `text` (which may contain unicode emoji) and return the pixel
    width it actually consumed, so callers stitching multiple segments
    together (e.g. text followed by a custom Discord emoji image) can
    advance their cursor by the real drawn width instead of a separate,
    approximate measurement that can drift out of sync and overlap.
    """
    # Accept either an Image or an ImageDraw object as the drawing target.
    # Prefer receiving the Image so pilmoji can operate on the full Image
    # object; if an ImageDraw is provided, create a fresh ImageDraw from
    # the underlying image when possible.
    img = None
    draw = None
    if isinstance(target, Image.Image):
        img = target
        draw = ImageDraw.Draw(img)
    else:
        draw = target
        img = getattr(draw, 'image', None) or getattr(draw, 'im', None)

    # Prefer color emoji rendered from the bundled local Twemoji.ttf (kept up
    # to date by just dropping in a newer font file), and fall back to the
    # network source only for glyphs the local font doesn't have.
    if any(is_emoji_character(c) for c in (text or '')):
        if img is not None and isinstance(img, Image.Image) and not _text_has_non_emoji_ink(text):
            # Segment is only unicode emoji and/or whitespace - route around
            # pilmoji entirely (see _draw_pure_emoji_segment).
            return _draw_pure_emoji_segment(img, xy, text, font, fill=fill)

        if _PILMOJI_AVAILABLE and Pilmoji is not None and img is not None and isinstance(img, Image.Image):
            try:
                emoji_source = LocalTwemojiSource() if LocalTwemojiSource is not None else Twemoji()
                try:
                    p = Pilmoji(img, emoji_source=emoji_source)
                except TypeError:
                    try:
                        p = Pilmoji(img, source=emoji_source)
                    except TypeError:
                        p = Pilmoji(img)

                consumed_width = None
                with p as pctx:
                    pctx.text(xy, text, font=font, fill=fill)
                    # Ask pilmoji for the width it just used - this is the
                    # same sizing math it drew with (it doesn't just measure
                    # the raw text; it reserves space for each emoji image
                    # based on font.size), so it's the one value guaranteed
                    # to match what's actually on the canvas.
                    try:
                        consumed_width = int(pctx.getsize(text, font=font)[0])
                    except Exception:
                        consumed_width = None
                # The draw already happened at this point - if getsize failed,
                # fall back to the approximate measurer for sizing only, but
                # never re-render below (that would double-draw the text).
                if consumed_width is None:
                    consumed_width = measure_text_width(text, draw, font, emoji_font) if draw is not None else 0
                return consumed_width
            except Exception:
                # Nothing was drawn (the exception happened before/during
                # pctx.text) - fall through to the manual renderer below.
                pass

    # Fallback rendering keeps the quote usable without pilmoji/network access.
    # Still tries the local color-emoji font directly (character by character;
    # multi-codepoint sequences like ZWJ combos won't cluster correctly here,
    # but standalone emoji - the common case - render fine) before giving up
    # to a font that has no emoji glyphs at all.
    if draw is None:
        return 0
    start_x, y = xy
    x = start_x
    target_px = int(getattr(font, 'size', 18) or 18)
    for char in text:
        if is_emoji_character(char) and img is not None:
            glyph_image = render_emoji_cluster_image(char)
            if glyph_image is not None:
                w = max(1, round(glyph_image.width * (target_px / float(glyph_image.height or target_px))))
                resized = glyph_image.resize((w, target_px), resample=Image.LANCZOS)
                img.paste(resized, (int(x), int(y)), resized)
                x += w
                continue
        current_font = emoji_font if emoji_font and is_emoji_character(char) else font
        draw.text((x, y), char, fill=fill, font=current_font)
        bbox = draw.textbbox((0, 0), char, font=current_font)
        x += bbox[2] - bbox[0]
    return int(x - start_x)


_CUSTOM_EMOJI_TAG_RE = re.compile(r'<a?:[A-Za-z0-9_]+:\d+>')


def _break_oversized_token(token: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int, emoji_font: ImageFont.ImageFont | None = None) -> list[str]:
    """Hard-break a single space-free token that's wider than max_width into
    smaller chunks that each fit, so an unbroken run of characters (a long
    URL, repeated characters, etc.) can't overflow the text box horizontally
    no matter how small the font gets. A custom Discord emoji tag is left
    intact - it's short enough in practice, and breaking it mid-tag would
    corrupt it so it no longer renders as an emoji at all.
    """
    if _CUSTOM_EMOJI_TAG_RE.fullmatch(token):
        return [token]
    chunks: list[str] = []
    current = ''
    for ch in token:
        test = current + ch
        if current and measure_text_width(test, draw, font, emoji_font) > max_width:
            chunks.append(current)
            current = ch
        else:
            current = test
    if current:
        chunks.append(current)
    return chunks or [token]


def wrap_text(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int, emoji_font: ImageFont.ImageFont | None = None) -> list[str]:
    lines = []
    for paragraph in text.splitlines() or ['']:
        if not paragraph:
            lines.append('')
            continue
        raw_words = paragraph.split(' ')
        if not raw_words:
            lines.append('')
            continue

        # Expand any single word wider than the box into smaller pieces first,
        # so a long unbroken run of characters still wraps instead of
        # overflowing past the right edge.
        words = []
        for w in raw_words:
            if w and measure_text_width(w, draw, font, emoji_font) > max_width:
                words.extend(_break_oversized_token(w, draw, font, max_width, emoji_font))
            else:
                words.append(w)

        current_line = words[0]
        for word in words[1:]:
            test_line = f'{current_line} {word}'
            width = measure_text_width(test_line, draw, font, emoji_font)
            if width <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
    return lines


def _split_line_into_segments(line: str) -> list[tuple]:
    """Split a line into text and custom-discord-emoji segments.

    Returns a list of tuples ('text', text) or ('custom_emoji', emoji_id, animated).
    """
    pattern = re.compile(r'(<a?:([A-Za-z0-9_]+):(\d+)>)')
    segments: list[tuple] = []
    pos = 0
    for m in pattern.finditer(line):
        if m.start() > pos:
            segments.append(('text', line[pos:m.start()]))
        whole = m.group(1)
        name = m.group(2)
        eid = m.group(3)
        animated = whole.startswith('<a:')
        segments.append(('custom_emoji', eid, animated))
        pos = m.end()
    if pos < len(line):
        segments.append(('text', line[pos:]))
    return segments


async def _fetch_discord_emoji_image(emoji_id: str, animated: bool = False) -> Image.Image | None:
    """Fetch a Discord custom emoji image from the CDN and return a Pillow Image or None."""
    ext = 'gif' if animated else 'png'
    url = f'https://cdn.discordapp.com/emojis/{emoji_id}.{ext}'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
        img = Image.open(io.BytesIO(data))
        return img.convert('RGBA')
    except Exception:
        return None


async def _render_line_with_custom_emojis(img: Image.Image, x: int, y: int, line: str, font: ImageFont.ImageFont, emoji_font: ImageFont.ImageFont | None = None, fill=(255,255,255)) -> None:
    """Render a line that may contain custom Discord emoji tags onto `img` at x,y.

    Text segments are rendered with pilmoji (via draw_text_with_font_fallback).
    Custom emoji images are fetched and pasted inline.
    """
    draw = ImageDraw.Draw(img)
    segments = _split_line_into_segments(line)
    cur_x = x
    for seg in segments:
        if seg[0] == 'text':
            text = seg[1]
            # Draw text (pilmoji will run when needed) and advance the
            # cursor by exactly the width that was drawn - not a separate
            # approximation, which could (and did) drift out of sync with
            # pilmoji's actual emoji sizing and overlap the next segment.
            cur_x += draw_text_with_font_fallback(img, (cur_x, y), text, font, emoji_font, fill=fill)
        else:
            _, eid, animated = seg
            emoji_img = await _fetch_discord_emoji_image(eid, animated)
            if emoji_img:
                target_h = int(getattr(font, 'size', 18))
                w = max(1, round(emoji_img.width * (target_h / float(emoji_img.height or target_h))))
                try:
                    emoji_resized = emoji_img.resize((w, target_h), resample=Image.LANCZOS)
                except Exception:
                    emoji_resized = emoji_img
                img.paste(emoji_resized, (int(cur_x), int(y)), emoji_resized)
                cur_x += w
            else:
                # If fetch failed, skip placeholder width
                cur_x += int(getattr(font, 'size', 18))


async def create_banner_preview(member: discord.Member, kind: str = 'welcome', style_override: str | None = None, quest_text: str | None = None, level: int = 1):
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
        draw.text((center_x, 190), f"{format_banner_username(get_banner_name(member))} you are now Level {level}!", fill=text_color, font=font, anchor='mm', stroke_fill=stroke_color, stroke_width=2)
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


async def _create_member_card(member, kind: str, filename: str, **kwargs):
    # Real cards use the member's saved style, assigning a random one the first time.
    style = ensure_user_banner_assigned(str(member.id))
    card = await create_banner_preview(member, kind, style_override=style, **kwargs)
    if card is not None:
        card.filename = filename
    return card


async def create_welcome_card(member):
    return await _create_member_card(member, 'welcome', 'welcome.png')


async def create_goodbye_card(member):
    return await _create_member_card(member, 'goodbye', 'goodbye.png')


async def create_levelup_card(member, level: int):
    return await _create_member_card(member, 'levelup', 'levelup.png', level=level)


async def format_quote_content(message: discord.Message, viewer_id: int | None = None) -> str:
    """Resolve mentions/channels/roles/timestamps in a message's content into readable text.

    Self-contained (no bot instance needed): resolves against the message's own
    `mentions`/`channel_mentions`/`role_mentions` caches and the guild, falling back to
    leaving the raw `<@id>`-style tag in place if a target can't be resolved locally.
    """
    content = str(getattr(message, 'content', '') or '').strip() or '[Embed or media content]'

    content = re.sub(r'<@!?\$\d+>', '@game', content)
    # Keep custom Discord emoji tags like `<:name:id>` or `<a:name:id>` in
    # the content so we can render them as images later. Previously these
    # were stripped; we now handle them explicitly during rendering.
    content = re.sub(r'\s+', ' ', content).strip()
    if not content:
        return '[Embed or media content]'

    replacements: list[tuple[str, str]] = []

    for user_id in getattr(message, 'raw_mentions', []) or []:
        user = None
        for mention in getattr(message, 'mentions', []) or []:
            if getattr(mention, 'id', None) == user_id:
                user = mention
                break
        if user is None and getattr(message, 'guild', None):
            try:
                user = message.guild.get_member(user_id) or message.guild.get_user(user_id)
            except Exception:
                user = None
        if user is None:
            continue

        username = getattr(user, 'name', None) or str(user_id)
        replacements.append((f'<@{user_id}>', f'@{username}'))
        replacements.append((f'<@!{user_id}>', f'@{username}'))

    for channel_id in getattr(message, 'raw_channel_mentions', []) or []:
        channel = None
        for mention in getattr(message, 'channel_mentions', []) or []:
            if getattr(mention, 'id', None) == channel_id:
                channel = mention
                break
        if channel is None and getattr(message, 'guild', None):
            try:
                channel = message.guild.get_channel(channel_id)
            except Exception:
                channel = None
        if channel is None:
            continue

        channel_name = getattr(channel, 'name', None) or str(channel_id)
        replacements.append((f'<#{channel_id}>', f'#{channel_name}'))
        replacements.append((f'<# {channel_id}>', f'#{channel_name}'))

    if getattr(message, 'guild', None):
        for role in getattr(message, 'role_mentions', []) or []:
            role_name = getattr(role, 'name', None) or str(getattr(role, 'id', ''))
            replacements.append((f'<@&{role.id}>', f'@{role_name}'))

    for old, new in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        content = content.replace(old, new)

    tzinfo = timezone.utc
    if viewer_id is not None:
        try:
            settings = load_user_settings()
            entry = get_user_settings_entry(settings, str(viewer_id))
            off = entry.get('timezone_offset')
            offs = parse_utc_offset(off) if off else None
            if offs is not None:
                tzinfo = timezone(offs)
        except Exception:
            tzinfo = timezone.utc

    def _ts_repl(match: re.Match) -> str:
        ts = int(match.group(1))
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tzinfo)
        return dt.strftime('%A %B %H:%M')

    content = re.sub(r'<t:(\d+)(?::[^>]+)?>', _ts_repl, content)

    return content.replace('\n', ' ')


def _fit_quote_text(
    text: str,
    draw: ImageDraw.ImageDraw,
    font_path: str | None,
    max_width: int,
    available_height: int,
    max_size: int = QUOTE_MAX_FONT_SIZE,
    min_size: int = QUOTE_MIN_FONT_SIZE,
) -> tuple[ImageFont.ImageFont, list[str], int]:
    """Find the largest font size in [min_size, max_size] whose word-wrapped
    `text` fits within `max_width` x `available_height`, and return the font
    to render with, the wrapped lines, and the line height to use.

    Binary search relies on wrapped line count being (near enough)
    monotonic in font size - shrinking the font never needs more lines to
    hold the same text at the same wrap width. If even `min_size` doesn't
    fit, that size is used anyway (better than crashing or rendering at 0),
    and the caller's own truncation is the last-resort safety net.
    """
    def try_size(size: int) -> tuple[ImageFont.ImageFont, list[str], int, bool]:
        try:
            candidate_font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
        except Exception:
            candidate_font = ImageFont.load_default()
        candidate_font = resolve_replacement_font(text, size, candidate_font) or candidate_font
        candidate_lines = wrap_text(text, draw, candidate_font, max_width) or ['']
        candidate_line_height = int(max(getattr(candidate_font, 'size', size), 6) * 1.4)
        fits = len(candidate_lines) * candidate_line_height <= available_height
        return candidate_font, candidate_lines, candidate_line_height, fits

    min_size = max(1, min(min_size, max_size))
    best_font, best_lines, best_line_height, fits_at_max = try_size(max_size)
    if fits_at_max or max_size <= min_size:
        return best_font, best_lines, best_line_height

    # max_size overflows - binary-search downward for the largest size that fits.
    best_font, best_lines, best_line_height, _ = try_size(min_size)
    lo, hi = min_size, max_size
    while lo < hi:
        mid = (lo + hi + 1) // 2
        mid_font, mid_lines, mid_line_height, fits = try_size(mid)
        if fits:
            best_font, best_lines, best_line_height = mid_font, mid_lines, mid_line_height
            lo = mid
        else:
            hi = mid - 1
    return best_font, best_lines, best_line_height


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
            font_small = ImageFont.truetype(font_path, 16)
            font_display = ImageFont.truetype(font_path, 20)
        except Exception:
            font_small = ImageFont.load_default(); font_display = ImageFont.load_default()
    else:
        font_small = ImageFont.load_default(); font_display = ImageFont.load_default()

    content_text = await format_quote_content(message, viewer_id=viewer_id)
    quoted_text = f'"{content_text}"'

    text_x = 300
    text_y = 35
    max_text_width = max(200, background.width - text_x - 40)
    footer_y = background.height - 44
    # The display-name line is drawn starting at footer_y - 34 (see below), so
    # the quote text's actual usable bottom boundary sits there, not at
    # footer_y itself - leave a small gap so descenders don't touch it.
    text_bottom_limit = footer_y - 34 - 6
    available_height = max(1, text_bottom_limit - text_y)

    active_font, lines, line_height = _fit_quote_text(
        quoted_text, draw, font_path, max_text_width, available_height,
    )
    active_emoji_font = resolve_emoji_font(int(getattr(active_font, 'size', 18) or 18), None)

    visible_lines = lines[:max(1, available_height // line_height)]
    # Render each visible line, handling custom Discord emojis inline.
    for idx, line in enumerate(visible_lines):
        await _render_line_with_custom_emojis(
            background, text_x, text_y + idx * line_height, line,
            active_font, active_emoji_font, fill=(255, 255, 255),
        )

    # Display name (falls back to the raw username when the display name has
    # non-ASCII characters the font can't render), plus the @username underneath
    # it — but only when the two are actually different (i.e. display name was
    # ASCII and wasn't already substituted with the username).
    display_name_is_ascii = not any(ord(char) > 127 for char in message.author.display_name)
    display_name_value = message.author.display_name if display_name_is_ascii else message.author.name
    if len(display_name_value) > 65:
        display_name_value = display_name_value[:64] + '...'
    display_name_text = f'- {display_name_value}'

    username_value = message.author.name
    if len(username_value) > 62:
        username_value = username_value[:61] + '...'
    username_text = f'@{username_value}'
    show_username = display_name_is_ascii

    username_y = footer_y - 4
    display_name_limit = max(120, min(350, background.width - text_x - 30))
    display_font = font_display
    display_font_size = getattr(font_display, 'size', 20)

    if len(display_name_text) > 20:
        display_font_size = max(10, display_font_size // 2)
        try:
            display_font = ImageFont.truetype(font_path, display_font_size)
        except Exception:
            display_font = font_display

    if measure_text_width(display_name_text, draw, display_font) > display_name_limit:
        while display_name_text and measure_text_width(display_name_text, draw, display_font) > display_name_limit:
            display_name_text = display_name_text[:-1].rstrip()
    if not display_name_text:
        display_name_text = '-'

    display_x = background.width - 30
    draw.text((display_x, footer_y - 34), display_name_text, fill=(255, 255, 255), font=display_font, anchor='ra')
    if show_username:
        username_bbox = draw.textbbox((0, 0), username_text, font=font_small)
        username_x = background.width - 30 - (username_bbox[2] - username_bbox[0])
        draw.text((username_x, username_y), username_text, fill=(100, 100, 100), font=font_small)

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
    'is_emoji_character',
    'can_render_glyph',
    'find_font_file',
    'load_emoji_font',
    'resolve_local_color_emoji_font',
    'render_emoji_cluster_image',
    'load_text_font',
    'resolve_replacement_font',
    'resolve_emoji_font',
    'measure_text_width',
    'draw_text_with_font_fallback',
    'parse_utc_offset',
    'pick_text_color',
    'get_opposite_color',
    'create_welcome_card',
    'create_goodbye_card',
    'create_levelup_card',
    'create_banner_preview',
    'format_quote_content',
    'create_quote_card',
]