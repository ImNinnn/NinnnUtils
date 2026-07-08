from datetime import datetime, timedelta, timezone
from main import message_cache, deleted_cache, edited_cache, bot_error_cache

message_cache = message_cache
deleted_cache = deleted_cache
edited_cache = edited_cache
bot_error_cache = bot_error_cache

def clean_cache():
    global message_cache, deleted_cache, edited_cache, bot_error_cache
    now = datetime.now(timezone.utc)
    message_cache = [m for m in message_cache if now - m['time'] < timedelta(minutes=120)]
    deleted_cache = [m for m in deleted_cache if now - m['time'] < timedelta(minutes=120)]
    edited_cache = [m for m in edited_cache if now - m['time'] < timedelta(minutes=120)]
    bot_error_cache = [m for m in bot_error_cache if now - m['time'] < timedelta(minutes=120)]

def trim_cache(cache: list, max_len: int = 10) -> list:
    return cache[-max_len:]
