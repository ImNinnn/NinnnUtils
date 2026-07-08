import re
from datetime import datetime

def discord_timestamp(dt: datetime, style: str = "f") -> str:
    if isinstance(dt, datetime):
        return f"<t:{int(dt.timestamp())}:{style}>"
    return str(dt)

def parse_duration_to_seconds(value: str) -> int | None:
    if not value:
        return None

    text = value.strip().lower()
    if not re.fullmatch(r'(?:\d+[dhms]\s*)+', text):
        return None

    total_seconds = 0
    for amount, unit in re.findall(r'(\d+)([dhms])', text):
        amount = int(amount)
        if unit == 'd':
            total_seconds += amount * 86400
        elif unit == 'h':
            total_seconds += amount * 3600
        elif unit == 'm':
            total_seconds += amount * 60
        else:
            total_seconds += amount

    return total_seconds
