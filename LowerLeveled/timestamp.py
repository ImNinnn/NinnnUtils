import re
from datetime import datetime, timezone


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

def parse_reminder_time(value: str) -> int | None:
    if not value:
        return None
    text = value.strip()
    if text.lower().startswith("in "):
        seconds = parse_duration_to_seconds(text[3:])
        if seconds is None or seconds <= 0:
            return None
        return int(datetime.now(timezone.utc).timestamp()) + seconds

    match = re.fullmatch(r"at\s+(\d{2})/(\d{2})/(\d{2})\s+(\d{1,2}):(\d{2})", text, re.IGNORECASE)
    if match:
        year = 2000 + int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        hour = int(match.group(4))
        minute = int(match.group(5))
        try:
            reminder_dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        except ValueError:
            return None
        if reminder_dt <= datetime.now(timezone.utc):
            return None
        return int(reminder_dt.timestamp())

    return None

