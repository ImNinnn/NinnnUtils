"""AFK status: /afk, the [AFK] nickname, mention replies and auto-clear when the user talks again."""

import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import save
from utils.audit import add_bot_error_entry
from utils.permissions import run_automod_check_for_interaction
from utils.user_settings import get_user_settings_entry

AFK_PREFIX = "[AFK]"
AFK_MESSAGE_WINDOW_SECONDS = 60
AFK_MESSAGE_LIMIT = 3


def get_afk_status_key(guild_id: int | str, user_id: int | str) -> str:
    return f"{guild_id}:{user_id}"


def build_afk_nickname(display_name: str) -> str:
    base_nickname = display_name.strip()
    if not base_nickname:
        base_nickname = "AFK"

    if len(base_nickname) + len(AFK_PREFIX) + 1 <= 32:
        return f"{AFK_PREFIX} {base_nickname}"

    max_base_length = max(0, 32 - len(AFK_PREFIX) - 1)
    return f"{AFK_PREFIX} {base_nickname[:max_base_length].rstrip()}"


def get_afk_reason(entry: dict | None) -> str:
    if not entry:
        return "No reason provided."
    reason = entry.get("reason")
    return str(reason or "No reason provided.")


class AfkCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.afk_status: dict[str, dict[str, object]] = {}
        self._restored = False

    async def cog_load(self):
        if self.bot.is_ready():
            await self.restore_afk_statuses()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.restore_afk_statuses()

    async def restore_afk_statuses(self) -> None:
        """Rebuild AFK state from user settings after a restart or a cog reload."""
        if self._restored:
            return
        self._restored = True
        try:
            settings = save.load_user_settings()
            users = settings.get("users", {}) if isinstance(settings, dict) else {}
            for uid, uentry in users.items():
                afk_dict = uentry.get("afk") if isinstance(uentry, dict) else None
                if not isinstance(afk_dict, dict):
                    continue
                for gid, afk_entry in afk_dict.items():
                    try:
                        if not afk_entry or not afk_entry.get("enabled"):
                            continue
                        guild_obj = self.bot.get_guild(int(gid)) if gid and str(gid).isdigit() else None
                        if not guild_obj:
                            continue
                        member = guild_obj.get_member(int(uid)) if uid and str(uid).isdigit() else None
                        key = get_afk_status_key(gid, uid)
                        self.afk_status[key] = {
                            "reason": afk_entry.get("reason", "No reason provided."),
                            "original_nickname": afk_entry.get("original_nickname"),
                            "display_name": afk_entry.get("display_name"),
                            "message_times": [],
                        }
                        if member:
                            base_name = afk_entry.get("display_name") or afk_entry.get("original_nickname") or member.global_name or member.name
                            wanted_nick = build_afk_nickname(base_name)
                            me = getattr(member.guild, "me", None)
                            if member.nick != wanted_nick and me and me.guild_permissions.manage_nicknames:
                                try:
                                    await member.edit(nick=wanted_nick, reason="AFK status restored on bot startup")
                                except Exception:
                                    pass
                    except Exception:
                        continue
        except Exception:
            pass

    async def set_afk_status(self, member: discord.Member, reason: str | None = None) -> bool:
        key = get_afk_status_key(member.guild.id, member.id)
        reason_text = (reason or "No reason provided.").strip() or "No reason provided."

        existing_state = self.afk_status.get(key)
        if existing_state:
            existing_state["reason"] = reason_text
            existing_state["message_times"] = [ts for ts in existing_state.get("message_times", []) if time.time() - ts <= AFK_MESSAGE_WINDOW_SECONDS]
            return False

        # Keep the real nickname (None when the member has none) so clearing AFK restores it exactly.
        original_nickname = member.nick
        display_name = getattr(member, "display_name", None)
        self.afk_status[key] = {
            "reason": reason_text,
            "original_nickname": original_nickname,
            "display_name": display_name,
            "message_times": [],
        }

        try:
            settings = save.load_user_settings()
            uentry = get_user_settings_entry(settings, str(member.id))
            if "afk" not in uentry or not isinstance(uentry.get("afk"), dict):
                uentry["afk"] = {}
            uentry["afk"][str(member.guild.id)] = {
                "enabled": True,
                "reason": reason_text,
                "original_nickname": original_nickname,
                "display_name": display_name,
                "since": datetime.now(timezone.utc).isoformat(),
            }
            save.save_user_settings(settings)
        except Exception:
            pass

        me = getattr(member.guild, "me", None)
        can_manage_nicknames = bool(me and me.guild_permissions.manage_nicknames)

        if not can_manage_nicknames:
            add_bot_error_entry(
                member.guild.id,
                None,
                member,
                "afk nickname update",
                PermissionError("Bot lacks manage_nicknames permission to update AFK nickname")
            )
            return True

        try:
            await member.edit(nick=build_afk_nickname(display_name or member.name), reason=f"AFK status enabled: {reason_text}")
        except (discord.Forbidden, discord.HTTPException) as error:
            add_bot_error_entry(member.guild.id, None, member, "afk nickname update", error)

        return True

    async def clear_afk_status(self, member: discord.Member, channel: discord.abc.Messageable | None = None) -> None:
        key = get_afk_status_key(member.guild.id, member.id)
        state = self.afk_status.pop(key, None)
        if not state:
            return

        original_nickname = state.get("original_nickname")
        me = getattr(member.guild, "me", None)
        if me and me.guild_permissions.manage_nicknames:
            try:
                await member.edit(nick=original_nickname or None, reason="AFK status removed")
            except (discord.Forbidden, discord.HTTPException):
                pass

        if channel is not None:
            try:
                await channel.send(f"<:approve:1517452125687513158> **{member.display_name}** is no longer AFK.")
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            settings = save.load_user_settings()
            uentry = get_user_settings_entry(settings, str(member.id))
            afk_dict = uentry.get("afk")
            if isinstance(afk_dict, dict) and str(member.guild.id) in afk_dict:
                afk_dict.pop(str(member.guild.id), None)
                uentry["afk"] = afk_dict
                save.save_user_settings(settings)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        for mention in message.mentions:
            if mention.id == message.author.id or mention.bot:
                continue

            afk_entry = self.afk_status.get(get_afk_status_key(message.guild.id, mention.id))
            if afk_entry:
                try:
                    await message.reply(f"<:warning:1517452174991556758> **{mention.display_name}** is AFK right now. Reason: {get_afk_reason(afk_entry)}")
                except (discord.Forbidden, discord.HTTPException):
                    pass
                break

        afk_entry = self.afk_status.get(get_afk_status_key(message.guild.id, message.author.id))
        if afk_entry:
            now = time.time()
            timestamps = [timestamp for timestamp in afk_entry.get("message_times", []) if now - timestamp <= AFK_MESSAGE_WINDOW_SECONDS]
            timestamps.append(now)
            afk_entry["message_times"] = timestamps
            if len(timestamps) >= AFK_MESSAGE_LIMIT:
                await self.clear_afk_status(message.author, channel=message.channel)

    @app_commands.command(name='afk', description='Set yourself as AFK with a reason')
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.describe(reason='Why you are going AFK')
    async def afk(self, interaction: discord.Interaction, reason: str = None):
        if interaction.guild is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        reason_text = (reason or "No reason provided.").strip() or "No reason provided."
        if interaction.guild and await run_automod_check_for_interaction(interaction, reason_text, source_label="/afk"):
            return

        newly_afk = await self.set_afk_status(member, reason_text)
        if newly_afk:
            await interaction.response.defer(); await interaction.followup.send(f"<:afk:1525440143245180970> {member.mention} is now AFK. Reason: `{reason_text}`")
        else:
            current_reason = get_afk_reason(self.afk_status.get(get_afk_status_key(member.guild.id, member.id)))
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:warning:1517452174991556758> You are already AFK. Reason: `{current_reason}`", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AfkCog(bot))
