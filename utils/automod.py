"""Shared automod engine: blocked words, warnings, warning sanctions and the honeypot channel check.

Used by the moderation cog, the /say-style commands of other cogs (through
run_automod_check_for_interaction) and the settings panels. Reading and writing
guild.json itself is in save.py.
"""

import re
from datetime import datetime, timedelta, timezone

import discord
from discord.automod import AutoModRuleAction, AutoModTrigger
from discord.enums import AutoModRuleActionType, AutoModRuleEventType, AutoModRuleTriggerType

import save

from utils.audit import add_bot_error_entry
from utils.formatting import format_duration, format_user_reference

# Discord rejects the whole rule when a single keyword or regex is over these limits.
MAX_DISCORD_KEYWORD_LENGTH = 60
MAX_DISCORD_REGEX_LENGTH = 260
MAX_DISCORD_REGEX_PER_RULE = 10



# ---------------------------------------------------------------- stored config

def get_guild_warnings(guild_id: str, member_id: int):
    data = save.load_guild_data()
    guild = data.setdefault(guild_id, {})
    warnings = guild.setdefault("warnings", {})
    user_warnings = warnings.setdefault(str(member_id), [])
    return user_warnings, data


def get_guild_automod_config(guild_id: str) -> tuple[dict, dict]:
    data = save.load_guild_data()
    guild = data.setdefault(guild_id, {})
    automod = guild.setdefault("automod", {})
    automod.setdefault("blocked_words", [])
    automod.setdefault("warning_sanctions", [])
    automod.setdefault("warning_sanction_state", {})
    automod.setdefault("blocked_rule_id", None)

    legacy_auto_sanctions = guild.pop("auto_sanctions", None)
    if isinstance(legacy_auto_sanctions, dict):
        migrated = []
        for warns_str, sanction in legacy_auto_sanctions.items():
            try:
                warns = int(warns_str)
            except (TypeError, ValueError):
                continue
            if not isinstance(sanction, dict):
                continue
            migrated.append({
                "warns": warns,
                "action": str(sanction.get("action", "timeout")),
                "duration_seconds": int(sanction.get("duration_seconds", 0) or 0),
                "duration": str(sanction.get("duration", "")) or str(sanction.get("duration_seconds", "")),
            })
        if migrated:
            automod.setdefault("warning_sanctions", []).extend(migrated)
            save.save_guild_data(data)

    return automod, data


# ---------------------------------------------------------------- matching

def get_automod_match_mode(entry: dict | None) -> str:
    if not isinstance(entry, dict):
        return "word"

    mode = str(entry.get("match_mode", "")).strip().lower()
    if mode in {"generated_regex", "generated", "regex", "true"}:
        return "generated_regex"
    if mode in {"custom_regex", "custom", "is", "raw_regex"}:
        return "custom_regex"
    if mode in {"word", "simple", "keyword", "false"}:
        return "word"

    if entry.get("use_regex", False):
        return "generated_regex"
    return "word"


def automod_text_matches(content: str, phrase: str, match_mode: str = "word") -> bool:
    if not content or not phrase:
        return False

    mode = str(match_mode or "word").strip().lower()
    if mode == "custom_regex":
        try:
            return re.search(phrase, content, re.IGNORECASE) is not None
        except re.error:
            return False

    if mode == "generated_regex":
        try:
            generated_pattern = generate_automod_regex_pattern(phrase)
            if not generated_pattern:
                return False
            return re.search(generated_pattern, content, re.IGNORECASE) is not None
        except re.error:
            return False

    return phrase.lower() in content.lower()


NUM_REPLACERS = {
    "i": ["1"],
    "l": ["1"],
    "e": ["3"],
    "a": ["4"],
    "s": ["5"],
    "t": ["7"],
    "b": ["8"],
    "g": ["9"],
    "o": ["0"],
}

SYM_REPLACERS = {
    "a": ["@", "∆", "/-\\", "/_\\", "/\\", "Д"],
    "b": ["|}", "|:", "|8", "ß", "ь"],
    "c": ["(", "€"],
    "e": ["£"],
    "f": ["ƒ", "£"],
    "h": ["|-|", "#", "}{"],
    "i": ["!", "|"],
    "j": ["ʝ"],
    "k": ["|<"],
    "l": ["!", "|"],
    "n": ["|\\|"],
    "s": ["$", "§"],
    "x": ["><"],
    "y": ["¥"],
}

LET_REPLACERS = {
    "i": ["l"],
    "l": ["i"],
    "u": ["v"],
    "m": ["nn", "rn"],
    "w": ["vv", "uu"],
}

EMO_REPLACERS = {
    "a": ["🇦", "🅰️"],
    "b": ["🇧", "🅱️"],
    "c": ["🇨", "©️"],
    "d": ["🇩"],
    "e": ["🇪"],
    "f": ["🇫"],
    "g": ["🇬"],
    "h": ["🇭"],
    "i": ["🇮", "ℹ️"],
    "j": ["🇯"],
    "k": ["🇰"],
    "l": ["🇱"],
    "m": ["🇲", "Ⓜ️"],
    "n": ["🇳"],
    "o": ["🇴", "🅾️", "⭕"],
    "p": ["🇵", "🅿️"],
    "q": ["🇶"],
    "r": ["🇷", "®️"],
    "s": ["🇸"],
    "t": ["🇹", "✝️"],
    "u": ["🇺"],
    "v": ["🇻"],
    "w": ["🇼"],
    "x": ["🇽", "❌", "❎", "✖️"],
    "y": ["🇾"],
    "z": ["🇿"],
    "1": ["1️⃣"],
    "2": ["2️⃣"],
    "3": ["3️⃣"],
    "4": ["4️⃣"],
    "5": ["5️⃣"],
    "6": ["6️⃣"],
    "7": ["7️⃣"],
    "8": ["8️⃣"],
    "9": ["9️⃣"],
    "0": ["0️⃣"],
}


def _collect_replacers(character: str) -> list[str]:
    replacers: list[str] = []
    for mapping in (NUM_REPLACERS, SYM_REPLACERS, LET_REPLACERS, EMO_REPLACERS):
        replacers.extend(mapping.get(character, []))

    seen: set[str] = set()
    ordered: list[str] = []
    for replacer in replacers:
        if replacer in seen:
            continue
        seen.add(replacer)
        ordered.append(replacer)
    return ordered


def generate_automod_regex_pattern(text: str) -> str:
    if not text:
        return ""

    parts: list[str] = []
    current_char: str | None = None
    repeat_count = 0
    current_pattern: str | None = None

    for character in text:
        if current_char == character and current_pattern is not None:
            repeat_count += 1
            continue

        if current_pattern is not None and repeat_count > 0:
            parts.append(f"(?:{current_pattern}){{{repeat_count + 1},}}")
            repeat_count = 0
            current_pattern = None

        variants = _collect_replacers(character)
        if not variants:
            pattern = re.escape(character)
        else:
            escaped_variants = [re.escape(value) for value in variants]
            pattern = f"(?:{re.escape(character)}|{'|'.join(escaped_variants)})"
        parts.append(pattern)

        current_char = character
        current_pattern = pattern

    if current_pattern is not None and repeat_count > 0:
        parts.append(f"(?:{current_pattern}){{{repeat_count + 1},}}")

    return "".join(parts)


def _build_discord_rule_filters(blocked_words: list) -> tuple[list[str], list[str], list[str]]:
    """Split blocked phrases into Discord keywords and regexes, respecting Discord's length limits.

    Returns (keywords, regex_patterns, skipped_phrases).
    """
    keyword_filter: list[str] = []
    regex_patterns: list[str] = []
    skipped: list[str] = []

    def add_literal(phrase: str) -> None:
        if len(phrase) <= MAX_DISCORD_KEYWORD_LENGTH:
            keyword_filter.append(phrase)
            return
        escaped = re.escape(phrase)
        if len(escaped) <= MAX_DISCORD_REGEX_LENGTH:
            regex_patterns.append(escaped)
        else:
            skipped.append(phrase)

    for entry in blocked_words:
        if not isinstance(entry, dict):
            continue
        phrase = str(entry.get("phrase", "")).strip()
        if not phrase:
            continue
        match_mode = get_automod_match_mode(entry)
        if match_mode == "custom_regex":
            if len(phrase) <= MAX_DISCORD_REGEX_LENGTH:
                regex_patterns.append(phrase)
            else:
                skipped.append(phrase)
        elif match_mode == "generated_regex":
            generated_pattern = generate_automod_regex_pattern(phrase)
            if generated_pattern and len(generated_pattern) <= MAX_DISCORD_REGEX_LENGTH:
                regex_patterns.append(generated_pattern)
            else:
                # Too long for Discord: still block the plain phrase instead of breaking the whole rule.
                add_literal(phrase)
        else:
            add_literal(phrase)

    return keyword_filter, regex_patterns, skipped


async def sync_guild_word_block_rule(guild: discord.Guild | None) -> None:
    """Mirror the guild's blocked words into Discord AutoMod "Word Block" rules."""
    if guild is None:
        return

    guild_id = str(guild.id)
    automod, _ = get_guild_automod_config(guild_id)
    keyword_filter, regex_patterns, skipped = _build_discord_rule_filters(automod.get("blocked_words", []))
    if skipped:
        add_bot_error_entry(
            guild.id, None, None, "automod rule sync",
            ValueError(f"Too long for Discord AutoMod, only checked in bot commands: {', '.join(skipped)[:900]}"),
        )

    created_rule_ids = []
    try:
        existing_rules = await guild.fetch_automod_rules()
        existing_word_rules = {rule.name: rule for rule in existing_rules if rule.name == "Word Block" or rule.name.startswith("Word Block ")}

        if not keyword_filter and not regex_patterns:
            for rule in existing_word_rules.values():
                await rule.delete(reason="No blocked words configured")
        else:
            action = AutoModRuleAction(
                type=AutoModRuleActionType.block_message,
                custom_message="Blocked word or phrase detected.",
            )

            regex_batches = [regex_patterns[i:i + MAX_DISCORD_REGEX_PER_RULE] for i in range(0, len(regex_patterns), MAX_DISCORD_REGEX_PER_RULE)] or [[]]
            batches = [("Word Block", keyword_filter, regex_batches[0])]
            for index, batch in enumerate(regex_batches[1:], start=2):
                batches.append((f"Word Block {index}", [], batch))

            for name, word_rules, regex_batch in batches:
                trigger = AutoModTrigger(
                    type=AutoModRuleTriggerType.keyword,
                    keyword_filter=word_rules or None,
                    regex_patterns=regex_batch or None,
                )
                existing_rule = existing_word_rules.get(name)
                if existing_rule is not None:
                    await existing_rule.edit(
                        name=name,
                        event_type=AutoModRuleEventType.message_send,
                        trigger=trigger,
                        actions=[action],
                        enabled=True,
                        reason="Updated blocked word settings",
                    )
                    created_rule_ids.append(existing_rule.id)
                else:
                    new_rule = await guild.create_automod_rule(
                        name=name,
                        event_type=AutoModRuleEventType.message_send,
                        trigger=trigger,
                        actions=[action],
                        enabled=True,
                        reason="Configured blocked word settings",
                    )
                    created_rule_ids.append(new_rule.id)

            wanted_names = {name for name, _, _ in batches}
            for rule_name, rule in existing_word_rules.items():
                if rule_name not in wanted_names:
                    await rule.delete(reason="Removed stale blocked word rule")
    except Exception as error:
        add_bot_error_entry(guild.id, None, None, "automod rule sync", error)
        return

    # Reload after the API calls so changes saved meanwhile (warnings, other settings) are kept.
    automod, data = get_guild_automod_config(guild_id)
    automod["blocked_rule_id"] = created_rule_ids[0] if created_rule_ids else None
    automod["blocked_rule_ids"] = created_rule_ids
    save.save_guild_data(data)


def find_blocked_word_match(automod: dict, content: str) -> dict | None:
    for entry in automod.get("blocked_words", []):
        if not isinstance(entry, dict):
            continue
        phrase = str(entry.get("phrase", "")).strip()
        if not phrase:
            continue
        if automod_text_matches(content, phrase, get_automod_match_mode(entry)):
            return entry
    return None


# ---------------------------------------------------------------- warnings and sanctions

async def add_guild_warning(guild_id: str, member_id: int, reason: str, moderator_id: int | None = None, moderator_name: str | None = None) -> tuple[list[dict], dict]:
    user_warnings, data = get_guild_warnings(guild_id, member_id)
    warn_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "moderator_id": moderator_id,
        "moderator_name": moderator_name,
    }
    user_warnings.append(warn_entry)
    save.save_guild_data(data)
    return user_warnings, data


def set_warning_sanction_state(guild_id: str, member_id: int, last_applied_warns: int | None) -> None:
    automod, data = get_guild_automod_config(guild_id)
    sanction_state = automod.setdefault("warning_sanction_state", {})
    if last_applied_warns is None:
        sanction_state.pop(str(member_id), None)
    else:
        sanction_state[str(member_id)] = {"last_applied_warns": last_applied_warns}
    save.save_guild_data(data)


async def send_warning_dm(member: discord.Member, guild: discord.Guild, reason: str, total_warnings: int | None = None, automod_triggered: bool = False, sanction: str | None = None) -> None:
    if member.bot:
        return

    title = "<:warning:1517452174991556758> You have received a warning"
    description = f"**Server:** {guild.name}\n**Reason:** {reason}"
    if automod_triggered:
        description += "\n**Triggered by:** Discord AutoMod"
    if total_warnings is not None:
        description += f"\n**Total warnings:** {total_warnings}"

    embed = discord.Embed(title=title, description=description[:4096], color=discord.Color.yellow())
    if sanction:
        embed.add_field(name="Sanction", value=sanction, inline=True)

    try:
        await member.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def send_automod_channel_reply(channel: discord.abc.GuildChannel | None, member: discord.Member | discord.User | None, member_id: int, reason: str, sanction: str | None = None, warning_given: bool = False, total_warnings: int | None = None) -> None:
    if channel is None:
        return

    mention = format_user_reference(member) if member is not None else f"<@{member_id}>"

    try:
        if warning_given:
            embed = discord.Embed(
                title="<:warning:1517452174991556758> You aren't allowed to say that.",
                description=f"**{mention}** is not allowed to say that.",
                color=discord.Color.yellow(),
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Total warnings", value=str(total_warnings if total_warnings is not None else 0), inline=False)
            if sanction:
                embed.add_field(name="Sanction", value=sanction, inline=True)
            await channel.send(embed=embed)
        else:
            await channel.send(f"<:warning:1517452174991556758> {mention}, you aren't allowed to say that.")
    except (discord.Forbidden, discord.HTTPException):
        pass


async def apply_warning_sanctions(member: discord.Member, guild: discord.Guild, total_warnings: int) -> str | None:
    automod, _ = get_guild_automod_config(str(guild.id))
    sanction_state = automod.get("warning_sanction_state", {})
    member_key = str(member.id)
    last_applied = int(sanction_state.get(member_key, {}).get("last_applied_warns", 0))
    if total_warnings <= last_applied:
        return None

    applicable = []
    for rule in automod.get("warning_sanctions", []):
        try:
            if isinstance(rule, dict) and int(rule.get("warns", 0)) <= total_warnings:
                applicable.append(rule)
        except (TypeError, ValueError):
            continue
    if not applicable:
        return None

    rule = max(applicable, key=lambda rule: int(rule.get("warns", 0)))
    threshold = int(rule.get("warns", 0))
    action = str(rule.get("action", "timeout")).lower()
    sanction_text = None
    try:
        if action == "timeout":
            # Discord caps timeouts at 28 days.
            duration_seconds = min(max(1, int(rule.get("duration_seconds", 86400) or 86400)), 28 * 86400)
            timed_out_until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            await member.edit(timed_out_until=timed_out_until, reason=f"Reached {threshold} warnings")
            sanction_text = f"Timeout for {format_duration(duration_seconds)}"
        elif action == "kick":
            await member.kick(reason=f"Reached {threshold} warnings")
            sanction_text = "Kick"
        elif action == "ban":
            await member.ban(reason=f"Reached {threshold} warnings")
            sanction_text = "Ban"
    except (discord.Forbidden, discord.HTTPException):
        pass

    # Reload before saving so nothing written during the API call is lost.
    set_warning_sanction_state(str(guild.id), member.id, total_warnings)
    return sanction_text


# ---------------------------------------------------------------- checks

def member_bypasses_automod(member: discord.Member | discord.User | None) -> bool:
    if not isinstance(member, discord.Member):
        return False
    perms = member.guild_permissions
    return bool(perms.manage_guild or perms.administrator)


async def run_automod_check_for_content(guild: discord.Guild | None, member: discord.Member | discord.User | None, channel: discord.abc.GuildChannel | None, content: str, *, source_label: str = "message") -> bool:
    """Check bot-sent text (e.g. /say) against the blocked words. Returns True when it was blocked."""
    if not guild or not content:
        return False

    if member_bypasses_automod(member):
        return False

    automod, _ = get_guild_automod_config(str(guild.id))
    matched_entry = find_blocked_word_match(automod, content)
    if matched_entry is None:
        return False
    should_warn = bool(matched_entry.get("warn_on_match", False))

    member_id = getattr(member, "id", None)
    reason = f"{source_label} triggered an AutoMod block"
    sanction_text = None
    warnings = None
    if should_warn and member_id is not None:
        warnings, _ = await add_guild_warning(
            str(guild.id),
            member_id,
            reason,
            moderator_id=None,
            moderator_name="Discord AutoMod",
        )

    if should_warn and isinstance(member, discord.Member) and not member.bot:
        sanction_text = await apply_warning_sanctions(member, guild, len(warnings) if warnings is not None else 0)
        await send_warning_dm(
            member,
            guild,
            reason,
            total_warnings=len(warnings) if warnings is not None else None,
            automod_triggered=True,
            sanction=sanction_text,
        )

    await send_automod_channel_reply(
        channel,
        member,
        member_id if member_id is not None else 0,
        reason,
        sanction=sanction_text,
        warning_given=should_warn,
        total_warnings=len(warnings) if warnings is not None else None,
    )
    return True


async def run_automod_check_for_interaction(interaction: discord.Interaction, content: str, *, source_label: str = "message") -> bool:
    """Run the blocked-word check for a slash command and answer the interaction when it blocks."""
    if not interaction or not getattr(interaction, "guild", None):
        return False

    if await run_automod_check_for_content(interaction.guild, interaction.user, interaction.channel, content, source_label=source_label):
        try:
            if interaction.response.is_done():
                await interaction.followup.send("Blocked word or phrase detected.", ephemeral=True)
            else:
                await interaction.response.send_message("Blocked word or phrase detected.", ephemeral=True)
        except (discord.NotFound, discord.HTTPException):
            pass
        return True
    return False


def is_honeypot_channel(guild: discord.Guild | None, channel: discord.abc.GuildChannel | None) -> bool:
    if not guild or not channel:
        return False
    try:
        guild_config, _ = save.get_guild_config(str(guild.id))
        configured_channel_id = guild_config.get("honeypot_channel_id")
        if configured_channel_id is None:
            return False
        return int(configured_channel_id) == channel.id
    except (TypeError, ValueError):
        return False
