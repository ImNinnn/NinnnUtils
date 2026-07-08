import re
from datetime import datetime, timezone, timedelta

import discord
from discord import AutoModTrigger, AutoModRuleTriggerType, AutoModRuleAction, AutoModRuleActionType, \
    AutoModRuleEventType

from Shared.Guilds import load_guild_data, save_guild_data, get_guild_config
from Shared.Locks import get_guild_admin_log_channel_ids


def get_guild_warnings(guild_id: str, member_id: int):
    data = load_guild_data()
    guild = data.setdefault(guild_id, {})
    warnings = guild.setdefault("warnings", {})
    user_warnings = warnings.setdefault(str(member_id), [])
    return user_warnings, data

async def add_guild_warning(guild_id: str, member_id: int, reason: str, moderator_id: int | None = None, moderator_name: str | None = None) -> tuple[list[dict], dict]:
    user_warnings, data = get_guild_warnings(guild_id, member_id)
    warn_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "moderator_id": moderator_id,
        "moderator_name": moderator_name,
    }
    user_warnings.append(warn_entry)
    save_guild_data(data)
    return user_warnings, data

def get_guild_automod_config(guild_id: str) -> tuple[dict, dict]:
    data = load_guild_data()
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
                "duration_seconds": int(sanction.get("duration_seconds", sanction.get("duration_seconds", 0) or 0)),
                "duration": str(sanction.get("duration", "")) or str(sanction.get("duration_seconds", "")),
            })
        if migrated:
            automod.setdefault("warning_sanctions", []).extend(migrated)
            save_guild_data(data)

        return automod, data

def automod_text_matches(content: str, phrase: str, use_regex: bool = False) -> bool:
    if not content or not phrase:
        return False
    if use_regex:
        try:
            return re.search(phrase, content, re.IGNORECASE) is not None
        except re.error:
            return False
    return phrase.lower() in content.lower()

async def sync_guild_word_block_rule(bot, guild_id: str) -> None:
    guild = bot.get_guild(int(guild_id)) if guild_id.isdigit() else None
    if guild is None:
        return

    automod, data = get_guild_automod_config(guild_id)
    blocked_words = automod.get("blocked_words", [])
    keyword_filter = [entry.get("phrase", "").strip() for entry in blocked_words if
                      not entry.get("use_regex", False) and entry.get("phrase", "").strip()]
    regex_patterns = [entry.get("phrase", "").strip() for entry in blocked_words if
                      entry.get("use_regex", False) and entry.get("phrase", "").strip()]

    try:
        existing_rules = await guild.fetch_automod_rules()
        existing_rule = next((rule for rule in existing_rules if rule.name == "Word Block"), None)

        if not keyword_filter and not regex_patterns:
            if existing_rule is not None:
                await existing_rule.delete(reason="No blocked words configured")
                automod.pop("blocked_rule_id", None)
                save_guild_data(data)
            return

        trigger = AutoModTrigger(
            type=AutoModRuleTriggerType.keyword,
            keyword_filter=keyword_filter or None,
            regex_patterns=regex_patterns or None,
        )
        action = AutoModRuleAction(
            type=AutoModRuleActionType.block_message,
            custom_message="Blocked word or phrase detected.",
        )
        if existing_rule is not None:
            await existing_rule.edit(
                name="Word Block",
                event_type=AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=[action],
                enabled=True,
                reason="Updated blocked word settings",
            )
            automod["blocked_rule_id"] = existing_rule.id
            save_guild_data(data)
        else:
            new_rule = await guild.create_automod_rule(
                name="Word Block",
                event_type=AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=[action],
                enabled=True,
                reason="Configured blocked word settings",
            )
            automod["blocked_rule_id"] = new_rule.id
            save_guild_data(data)
    except Exception:
        pass

async def send_warning_dm(member: discord.Member, guild: discord.Guild, reason: str, total_warnings: int | None = None, automod_triggered: bool = False) -> None:
    if member.bot:
        return

    title = "<:warning:1517452174991556758> You have received a warning"
    description = f"**Server:** {guild.name}\n**Reason:** {reason}"
    if automod_triggered:
        description += "\n**Triggered by:** Discord AutoMod"
    if total_warnings is not None:
        description += f"\n**Total warnings:** {total_warnings}"

    embed = discord.Embed(title=title, description=description, color=discord.Color.gold())
    try:
        await member.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass

async def apply_warning_sanctions(member: discord.Member, guild: discord.Guild, total_warnings: int) -> None:
    automod, data = get_guild_automod_config(str(guild.id))
    sanction_state = automod.setdefault("warning_sanction_state", {})
    member_key = str(member.id)
    last_applied = int(sanction_state.get(member_key, {}).get("last_applied_warns", 0))
    if total_warnings <= last_applied:
        return

    applicable = [
        rule for rule in automod.get("warning_sanctions", [])
        if isinstance(rule, dict) and int(rule.get("warns", 0)) <= total_warnings
    ]
    if not applicable:
        return

    rule = max(applicable, key=lambda rule: int(rule.get("warns", 0)))
    threshold = int(rule.get("warns", 0))
    action = str(rule.get("action", "timeout")).lower()
    try:
        if action == "timeout":
            duration_seconds = max(1, int(rule.get("duration_seconds", 86400)))
            timed_out_until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            await member.edit(timed_out_until=timed_out_until, reason=f"Reached {threshold} warnings")
        elif action == "kick":
            await member.kick(reason=f"Reached {threshold} warnings")
        elif action == "ban":
            await member.ban(reason=f"Reached {threshold} warnings")
    except (discord.Forbidden, discord.HTTPException):
        pass
    sanction_state[member_key] = {"last_applied_warns": total_warnings}
    save_guild_data(data)

async def apply_honeypot_sanction(member: discord.Member | discord.User, guild: discord.Guild, channel: discord.abc.GuildChannel, message_content: str | None = None) -> bool:
    if member.bot or not guild or not isinstance(member, discord.Member):
        return False

    guild_config, _ = get_guild_config(str(guild.id))
    configured_channel_id = guild_config.get("honeypot_channel_id")
    if not configured_channel_id or int(configured_channel_id) != channel.id:
        return False

    sanction = guild_config.get("honeypot_sanction") or {}
    action = str(sanction.get("action", "timeout")).lower()
    if action not in {"timeout", "kick", "ban"}:
        return False

    content_preview = (message_content or "").strip()
    if not content_preview:
        content_preview = "[no text content]"
    if len(content_preview) > 500:
        content_preview = content_preview[:497] + "..."

    for log_id in get_guild_admin_log_channel_ids(guild):
        log_channel = guild.get_channel(log_id)
        if log_channel is None:
            continue
        try:
            await log_channel.send(
                f"**[HONEYPOT]** `{member.display_name}`: {content_preview}\n-# <:honey:1524116282075512842> **Honeypot triggered** by {member.mention} | Action: {action.title()}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    try:
        if action == "timeout":
            duration_seconds = max(1, int(sanction.get("duration_seconds", 86400)))
            timed_out_until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            await member.edit(timed_out_until=timed_out_until, reason="Sent a message in the honeypot channel")
        elif action == "kick":
            await member.kick(reason="Sent a message in the honeypot channel")
        elif action == "ban":
            await member.ban(reason="Sent a message in the honeypot channel")
    except (discord.Forbidden, discord.HTTPException):
        return False

    return True