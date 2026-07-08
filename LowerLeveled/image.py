from PIL import ImageDraw, ImageFont


def wrap_text(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int) -> list[str]:
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
            if draw.textbbox((0, 0), test_line, font=font)[2] <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)

    return lines
