from PIL import ImageDraw, ImageFont

from LowerLeveled.pillow import is_emoji_character


def wrap_text(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int, emoji_font: ImageFont.ImageFont | None = None) -> list[str]:
    lines = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph:
            lines.append("")
            continue

        words = paragraph.split(' ')
        if not words:
            lines.append("")
            continue

        current_line = words[0]
        for word in words[1:]:
            test_line = f"{current_line} {word}"
            if measure_text_width(test_line, draw, font, emoji_font) <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)

    return lines

def draw_text_with_font_fallback(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont, emoji_font: ImageFont.ImageFont | None = None, fill=(255, 255, 255)) -> None:
    x, y = xy
    for char in text:
        current_font = emoji_font if emoji_font and is_emoji_character(char) else font
        draw.text((x, y), char, fill=fill, font=current_font)
        bbox = draw.textbbox((0, 0), char, font=current_font)
        x += bbox[2] - bbox[0]

def measure_text_width(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, emoji_font: ImageFont.ImageFont | None = None) -> int:
    width = 0
    for char in text:
        current_font = emoji_font if emoji_font and is_emoji_character(char) else font
        bbox = draw.textbbox((0, 0), char, font=current_font)
        width += bbox[2] - bbox[0]
    return width
