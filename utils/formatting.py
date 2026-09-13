"""Pure formatting helpers for time and display strings."""

import re
from datetime import datetime, timezone

import discord


LANGUAGE_ALIASES = {
    "auto": "auto",
    "automatic": "auto",
    "detect": "auto",
    "english": "en",
    "en": "en",
    "en-us": "en",
    "en_us": "en",
    "french": "fr",
    "fr": "fr",
    "france": "fr",
    "german": "de",
    "de": "de",
    "spanish": "es",
    "es": "es",
    "italian": "it",
    "it": "it",
    "japanese": "ja",
    "ja": "ja",
    "korean": "ko",
    "ko": "ko",
    "portuguese": "pt",
    "pt": "pt",
    "portuguese-brazil": "pt",
    "pt-br": "pt",
    "pt_br": "pt",
    "russian": "ru",
    "ru": "ru",
    "chinese": "zh-cn",
    "zh": "zh-cn",
    "zh-cn": "zh-cn",
    "zh_cn": "zh-cn",
    "arabic": "ar",
    "ar": "ar",
    "hindi": "hi",
    "hi": "hi",
    "turkish": "tr",
    "tr": "tr",
    "dutch": "nl",
    "nl": "nl",
    "polish": "pl",
    "pl": "pl",
    "swedish": "sv",
    "sv": "sv",
    "norwegian": "no",
    "no": "no",
}


def normalize_language_code(value: str | None, *, default: str | None = None, strict: bool = False) -> str | None:
    if value is None:
        return default

    token = str(value).strip().lower().replace("_", "-")
    if not token:
        return default

    if token in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[token]

    if re.fullmatch(r"[a-z]{2,5}(?:-[a-z0-9]{2,5})?", token):
        return token

    if strict:
        return None
    return default


def is_valid_language_code(value: str | None) -> bool:
    if value is None:
        return False
    normalized = normalize_language_code(value, default=None, strict=True)
    return normalized is not None and normalized != ""


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


format_timedelta = format_duration
parse_duration_to_seconds = None
parse_reminder_time = None
get_reminder_display = None
get_reminder_repeat_text = None
format_repeat_interval = None


def discord_timestamp(dt: datetime | None, style: str = "f") -> str:
    if dt is None:
        return "Unknown"
    return discord.utils.format_dt(dt, style=style)


def format_user_reference(user: discord.abc.User | discord.Member, settings: dict | None = None) -> str:
    return getattr(user, "mention", str(user))


def format_user_reference_with_setting(user: discord.abc.User | discord.Member, settings: dict | None = None) -> str:
    if settings is None:
        return getattr(user, "mention", str(user))

    if isinstance(settings, dict):
        user_key = str(getattr(user, "id", ""))
        user_settings = settings.get("users", {}).get(user_key, {}) if isinstance(settings.get("users"), dict) else {}
        if user_settings.get("user_pings") is False:
            return getattr(user, "display_name", getattr(user, "name", str(user)))

    return getattr(user, "mention", str(user))


__all__ = [
    "datetime",
    "timezone",
    "LANGUAGE_ALIASES",
    "normalize_language_code",
    "is_valid_language_code",
    "format_duration",
    "format_timedelta",
    "parse_duration_to_seconds",
    "parse_reminder_time",
    "get_reminder_display",
    "get_reminder_repeat_text",
    "format_repeat_interval",
    "discord_timestamp",
    "format_user_reference",
    "format_user_reference_with_setting",
]
