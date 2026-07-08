from datetime import datetime

def discord_timestamp(dt: datetime, style: str = "f") -> str:
    if isinstance(dt, datetime):
        return f"<t:{int(dt.timestamp())}:{style}>"
    return str(dt)
