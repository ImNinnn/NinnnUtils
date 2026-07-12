import os
from PIL import ImageFont, Image, ImageDraw

def is_emoji_character(char: str) -> bool:
    if not char:
        return False

    codepoint = ord(char)
    if codepoint in {0x200D, 0xFE0F}:
        return True

    return (
        0x1F300 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
        or 0x1F1E6 <= codepoint <= 0x1F1FF
    )

def can_render_glyph(font: ImageFont.ImageFont, char: str) -> bool:
    if not font or not char:
        return False

    try:
        test_image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        test_draw = ImageDraw.Draw(test_image)
        test_draw.text((8, 8), char, fill=(255, 255, 255), font=font)
        return test_image.getbbox() is not None
    except Exception:
        return False


def find_font_file(base_path: str, filename_hint: str | None = None, text: str | None = None) -> str | None:
    fonts_dir = os.path.join(base_path, "fonts")
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
            dirnames.sort()
            filenames.sort()
            for name in filenames:
                if not name.lower().endswith((".ttf", ".ttc")):
                    continue
                full_path = os.path.join(dirpath, name)
                if full_path in seen:
                    continue
                seen.add(full_path)
                if filename_hint and name.lower() != filename_hint.lower():
                    continue
                if "notosans" in full_path.lower():
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

def load_emoji_font(base_path: str, size: int, fallback_font: ImageFont.ImageFont | None = None) -> ImageFont.ImageFont | None:
    candidate_paths = [
        os.path.join(base_path, "NotoEmoji.ttf"),
        find_font_file(base_path, "NotoEmoji.ttf"),
    ]

    for font_path in candidate_paths:
        if not font_path or not os.path.exists(font_path):
            continue
        try:
            font = ImageFont.truetype(font_path, size)
            if can_render_glyph(font, "😀"):
                return font
        except Exception:
            continue

    return fallback_font

def load_text_font(base_path: str, text: str, size: int, fallback_font: ImageFont.ImageFont | None = None) -> ImageFont.ImageFont | None:
    if not text:
        return fallback_font

    font_path = find_font_file(base_path)

    if not font_path:
        return fallback_font

    try:
        font = ImageFont.truetype(font_path, size)
        if any(ord(char) > 127 and not is_emoji_character(char) for char in text):
            if can_render_glyph(font, text[0]):
                return font
        return fallback_font
    except Exception:
        return fallback_font