from discord.ext.commands import Cog, Context
import discord

from Shared.Guilds import save_guild_data
from Shared.Moderation import get_guild_automod_config, automod_text_matches, add_guild_warning, send_warning_dm, \
    apply_warning_sanctions


async def setup(bot):
    await bot.add_cog(Moderation(bot))

class Moderation(Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_automod_action(self, action: discord.AutoModAction) -> None:
        guild = action.guild
        if guild is None:
            return

        automod, data = get_guild_automod_config(str(guild.id))
        blocked_rule_id = automod.get("blocked_rule_id")

        if blocked_rule_id is None or action.rule_id != blocked_rule_id:
            resolved_id = None
            try:
                rule = await action.fetch_rule()
                if rule.name == "Word Block":
                    resolved_id = action.rule_id
            except Exception:
                try:
                    rules = await guild.fetch_automod_rules()
                    matching = next((r for r in rules if r.id == action.rule_id and r.name == "Word Block"), None)
                    if matching is not None:
                        resolved_id = action.rule_id
                except Exception:
                    resolved_id = None

            if resolved_id is None:

                blocked_rule_id = None
            else:
                blocked_rule_id = resolved_id
                automod["blocked_rule_id"] = resolved_id
                save_guild_data(data)

        text = action.matched_content or action.matched_keyword or action.content or ""
        if not text:
            return

        blocked_words = automod.get("blocked_words", [])
        should_warn = False
        for entry in blocked_words:
            if not entry.get("warn_on_match", False):
                continue
            phrase = str(entry.get("phrase", "")).strip()
            if not phrase:
                continue
            if automod_text_matches(text, phrase, bool(entry.get("use_regex", False))):
                should_warn = True
                break

        if not should_warn:
            return

        member_id = action.user_id
        warnings, _ = await add_guild_warning(str(guild.id), member_id,
                                              f"Discord AutoMod blocked a message via rule {action.rule_id}",
                                              moderator_id=None, moderator_name="Discord AutoMod")

        member = action.member or guild.get_member(member_id)
        if member is None:
            try:
                member = await guild.fetch_member(member_id)
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                member = None

        if member is not None and not member.bot:
            sanction_text = await apply_warning_sanctions(member, guild, len(warnings))
            await send_warning_dm(
                member,
                guild,
                f"Discord AutoMod blocked a message via rule {action.rule_id}",
                total_warnings=len(warnings),
                automod_triggered=True,
                sanction=sanction_text
            )

        if member is None:
            return