from discord.ext.commands import Context, Cog, hybrid_command
from discord import app_commands
from LowerLeveled.timestamp import discord_timestamp
import discord

from Shared.Boards import load_board_data
from Shared.Guilds import get_guild_config
from Shared.Leveling import load_levels
from Shared.Locks import load_lock_config
from Shared.User import format_user_reference

async def setup(bot):
    await bot.add_cog(Guild())

class Guild(Cog):
    @hybrid_command(name="serverinfo", description="Display detailed information about this server")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def serverinfo(self, ctx: Context):
        guild = ctx.guild
        created_at = discord_timestamp(guild.created_at)
        joined_at = discord_timestamp(ctx.author.joined_at) if ctx.author.joined_at else "Unknown"
        total_count = guild.member_count
        bot_count = len([m for m in guild.members if m.bot])
        human_count = total_count - bot_count

        embed = discord.Embed(title=f"Information for {guild.name}", color=discord.Color.blue())
        embed.add_field(name="<:chalice:1517579767573123092> Server Owner",
                        value=f"{format_user_reference(guild.owner)}", inline=True)
        embed.add_field(name="<:timer:1517996239583576194> Created At", value=created_at, inline=True)
        embed.add_field(name="<:plus:1518348756570079262> Joined At (user)", value=joined_at, inline=True)
        vanity = guild.vanity_url_code if guild.vanity_url_code else "-"
        embed.add_field(name="<:minus:1518348754111959150> Vanity Link", value=vanity, inline=True)
        embed.add_field(name="<:internet:1518376144246804672> Preferred Locale", value=f"{guild.preferred_locale}",
                        inline=True)
        embed.add_field(name="<:shield:1518340640801427566> Verification Level",
                        value=str(guild.verification_level).capitalize(), inline=True)
        boost_info = f"{guild.premium_subscription_count} (Level {guild.premium_tier})"
        embed.add_field(name="<:spark:1517583248421552305> Server Boosts", value=boost_info, inline=True)
        embed.add_field(name="<:drawer:1517497564189036574> Channels", value=f"{len(guild.channels)}", inline=True)
        embed.add_field(name="<:multi:1518348755261460661> Roles", value=f"{len(guild.roles)}", inline=True)
        embed.add_field(name="\n<:graph:1517584522877866065> Members", value=" ", inline=False)
        embed.add_field(name="<:approuve:1517452125687513158> Real Accounts", value=str(human_count), inline=True)
        embed.add_field(name="<:dissaprouve:1517452151012589662> Bots", value=str(bot_count), inline=True)
        embed.add_field(name="<:warning:1517452174991556758> Total", value=str(total_count), inline=True)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=embed)

    @hybrid_command(name="channelinfo",
                      description="Show configured channels from the bot's JSON settings for this server")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def channelinfo(self, ctx: Context):
        if ctx.guild is None:
            await ctx.send(
                "<:disapprove:1517452151012589662> This command must be used in a server.", ephemeral=True)
            return

        guild = ctx.guild
        guild_id = str(guild.id)

        guild_config, _ = get_guild_config(guild_id)
        levels = load_levels()
        board_data = load_board_data()
        locked, admin_log = load_lock_config()

        def fmt_channel(cid):
            if not cid:
                return "Not set"
            try:
                cid_int = int(cid)
            except Exception:
                return str(cid)
            ch = guild.get_channel(cid_int)
            if ch is not None:
                return ch.mention
            return f"<#{cid_int}>"

        welcome = fmt_channel(guild_config.get("welcome_channel_id"))
        goodbye = fmt_channel(guild_config.get("goodbye_channel_id"))

        lvl_channel = "Not set"
        if guild_id in levels:
            lvl_channel_id = levels[guild_id].get("config", {}).get("channel_id")
            if lvl_channel_id:
                lvl_channel = fmt_channel(lvl_channel_id)

        board_entries = []
        if guild_id in board_data:
            for emoji_key, cfg in board_data[guild_id].items():
                ch_id = cfg.get("channel_id")
                required = cfg.get("required_count") or cfg.get("required") or cfg.get("required_count", None)
                channel_repr = fmt_channel(ch_id)
                
                req_text = f"required {required}" if required is not None else "required ?"
                board_entries.append(f"{emoji_key} in {channel_repr} ({req_text})")
        board_channels = "\n".join(board_entries) if board_entries else "None"

        counter_entries = []
        counters = guild_config.get("counter_channels", {})
        for ch_key, cfg in counters.items():
            try:
                ch = guild.get_channel(int(ch_key))
                ch_repr = ch.mention if ch else f"<#{ch_key}"
            except Exception:
                ch_repr = str(ch_key)
            current_val = cfg.get("current_value", 0)
            counter_entries.append(f"{ch_repr}: {current_val}")
        counter_channels = "\n".join(counter_entries) if counter_entries else "None"

        admin_log_channels_list = []
        if admin_log and isinstance(admin_log, dict):
            for ch_id in admin_log.keys():
                try:
                    ch = guild.get_channel(int(ch_id))
                    if ch:
                        admin_log_channels_list.append(ch.mention)
                except Exception:
                    continue
        admin_log_channel = "\n".join(admin_log_channels_list) if admin_log_channels_list else "Not set"

        locked_channels_list = []
        if isinstance(locked, dict):
            for ch_key in locked.keys():
                try:
                    ch = guild.get_channel(int(ch_key))
                    if ch:
                        locked_channels_list.append(ch.mention)
                except Exception:
                    continue
        locked_channels = "\n".join(locked_channels_list) if locked_channels_list else "None"

        embed = discord.Embed(title=f"<:drawer:1517497564189036574> Configured Channels for {guild.name}",
                              color=discord.Color.blurple())
        embed.add_field(name="<:plus:1518348756570079262> Welcome Channel", value=welcome, inline=False)
        embed.add_field(name="<:minus:1518348754111959150> Goodbye Channel", value=goodbye, inline=False)
        embed.add_field(name="<:chalice:1517579767573123092> Level-up Announce Channel", value=lvl_channel,
                        inline=False)
        embed.add_field(name="<:graph:1517584522877866065> Board Channels", value=board_channels, inline=False)
        embed.add_field(name="<:list:1517497572770451567> Counter Channels", value=counter_channels, inline=False)
        embed.add_field(name="<:unlocked:1517574880034558102> Admin Log Channel", value=admin_log_channel, inline=False)
        embed.add_field(name="<:locked:1517574877257924809> Locked Channels", value=locked_channels, inline=False)
        embed.set_footer(text=f"Run /settings and go to channel settings to change these settings.")

        await ctx.send(embed=embed)
