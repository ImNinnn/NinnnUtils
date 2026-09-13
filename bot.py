print("------------------------ [starting] ------------------------")
import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

import helper as main

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = os.getenv('PREFIX', '!')
SHARD_COUNT = int(os.getenv('SHARD_COUNT', '0'))


class Bot(commands.AutoShardedBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def is_owner(self, user: discord.User | None) -> bool:
        if user is None:
            return False

        candidate_ids = []
        for attr in ("owner_id", "_owner_id"):
            value = getattr(self, attr, None)
            if value is not None:
                try:
                    candidate_ids.append(int(value))
                except (TypeError, ValueError):
                    pass

        if user.id in set(candidate_ids):
            return True

        try:
            return await super().is_owner(user)
        except Exception:
            return False

    async def setup_hook(self):
        print('[bot] setup hook')
        # Remove legacy prefix command registrations originating from main.py to avoid
        # duplicate prefix-command handling when the migrated cogs also register wrappers.
        removed = 0
        for cmd in list(self.commands):
            try:
                mod = getattr(cmd.callback, '__module__', '')
                if mod == 'main' or mod.startswith('main.'):
                    self.remove_command(cmd.name)
                    removed += 1
            except Exception:
                continue
        if removed:
            print(f'[bot] removed {removed} legacy prefix command(s) from main module')

        await _load_all_cogs()
        await self.tree.sync()
        print('[bot] slash commands synced')

    async def on_ready(self):
        # Run once (or on reconnect) to log status and restore lightweight runtime state from main
        shard_info = (
            f"{len(self.shards)} shard(s), IDs {list(self.shards.keys())}"
            if self.shards
            else "single process (no sharding)"
        )
        print(f"[bot] logged in as {self.user} (ID: {self.user.id}) - {shard_info}")
        print(f"[bot] serving {len(self.guilds)} guilds and {len(self.users)} users")
        print("------------------------ [startup finished] ------------------------")

        try:
            if not getattr(main, '_BACKUP_SCHEDULER_THREAD', None) or not main._BACKUP_SCHEDULER_THREAD.is_alive():
                main.start_backup_scheduler(interval_seconds=12 * 60 * 60)
                print('[backup] scheduler started for 12 hour interval')
        except Exception as exc:
            print(f'[backup] failed to start backup scheduler: {exc}')

        try:
            await main.restore_ticket_announce_views()
            await main.restore_ticket_thread_views()
        except Exception:
            pass

        try:
            settings = main.load_user_settings()
            users = settings.get('users', {}) if isinstance(settings, dict) else {}
            for uid, uentry in users.items():
                afk_dict = uentry.get('afk') if isinstance(uentry, dict) else None
                if not isinstance(afk_dict, dict):
                    continue
                for gid, afk_entry in afk_dict.items():
                    if not afk_entry or not afk_entry.get('enabled'):
                        continue
                    guild_obj = self.get_guild(int(gid)) if gid and str(gid).isdigit() else None
                    if not guild_obj:
                        continue
                    member = guild_obj.get_member(int(uid)) if uid and str(uid).isdigit() else None
                    key = main.get_afk_status_key(gid, uid)
                    main.afk_status[key] = {
                        'reason': afk_entry.get('reason', 'No reason provided.'),
                        'original_nickname': afk_entry.get('original_nickname'),
                        'message_times': [],
                    }
                    if member:
                        me = getattr(member.guild, 'me', None)
                        if me and me.guild_permissions.manage_nicknames:
                            try:
                                await member.edit(
                                    nick=main.build_afk_nickname(afk_entry.get('original_nickname') or member.name),
                                    reason='AFK status restored on bot startup',
                                )
                            except Exception:
                                pass
        except Exception:
            pass

        loop_cog = self.get_cog('LoopCog')
        if loop_cog is not None:
            loop_cog.start_tasks()

        levels_cog = self.get_cog('LevelsCog')
        if levels_cog is not None and hasattr(levels_cog, 'start_tasks'):
            levels_cog.start_tasks()

    async def on_message(self, message: discord.Message):
        # Centralized message routing: run the existing monolith message handler first
        # (it performs AFK checks, auto-replies, XP, etc.), then run command processing
        # once via the Bot's process_commands to avoid duplicate prefix command execution.
        try:
            # If main.on_message exists, call it. It should not call bot.process_commands any more.
            if hasattr(main, 'on_message'):
                await main.on_message(message)
        except Exception:
            # swallow errors to avoid crashing the client on unhandled exceptions in legacy logic
            import traceback
            traceback.print_exc()
        try:
            await self.process_commands(message)
        except Exception:
            # let discord.py handle command errors separately
            pass

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandNotFound):
            try:
                is_owner = await self.is_owner(ctx.author)
            except Exception:
                is_owner = False

            if is_owner:
                await ctx.send('<:disapprove:1517452151012589662> you typed it wrong, or maybe you\'re just hallucinating and this command doesn\'t exist, try again with a command that exists.')
            else:
                await ctx.send('<:disapprove:1517452151012589662> this command doesn\'t exist, even if it did, you couldn\'t even be able to run it, but hey! you can still use the / commands :)')
            return



intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = False
intents.auto_moderation_execution = True

bot = Bot(
    command_prefix=PREFIX,
    intents=intents,
    shard_count=SHARD_COUNT or None,
    help_command=None,
)

main.bot = bot


@bot.event
async def on_audit_log_entry_create(entry: discord.AuditLogEntry) -> None:
    await main.on_audit_log_entry_create(entry)


@bot.event
async def on_automod_action(action: discord.AutoModAction) -> None:
    await main.on_automod_action(action)


@bot.event
async def on_voice_state_update(member, before, after):
    await main.on_voice_state_update(member, before, after)


@bot.event
async def on_raw_reaction_add(payload):
    await main.on_raw_reaction_add(payload)


@bot.event
async def on_raw_reaction_remove(payload):
    await main.on_raw_reaction_remove(payload)


@bot.event
async def on_guild_channel_delete(channel):
    await main.on_guild_channel_delete(channel)


def _module_name(cog_name: str) -> str:
    return f'cogs.{cog_name}'


DEFAULT_COG_NAMES = [
    'economy',
    'fun',
    'games',
    'legacy',
    'levels',
    'loop',
    'media',
    'misc',
    'moderation',
    'music',
    'settings_notes_lists_reminders',
    'utils',
]


def _load_cog_names() -> list[str]:
    return DEFAULT_COG_NAMES.copy()


def _persist_cog_names(names: list[str]) -> None:
    global COG_NAMES
    filtered = []
    seen = set()
    for name in names:
        normalized = str(name).strip().replace('-', '_').replace(' ', '_')
        if not normalized:
            continue
        if normalized not in seen:
            filtered.append(normalized)
            seen.add(normalized)

    COG_NAMES = filtered or DEFAULT_COG_NAMES.copy()


COG_NAMES = _load_cog_names()
EXTERNAL_COGS: list[str] = []


def _resolve_cog_name(raw_name: str | None) -> str | None:
    if raw_name is None:
        return None
    normalized = raw_name.strip().lower().replace('-', '_').replace(' ', '_')
    if not normalized:
        return None
    for name in COG_NAMES:
        if normalized == name or normalized == name.replace('_', ''):
            return name
    return normalized if normalized in COG_NAMES else None


def _all_cog_names() -> list[str]:
    combined = [*COG_NAMES, *EXTERNAL_COGS]
    seen = set()
    ordered = []
    for name in combined:
        normalized = str(name).strip().replace('-', '_').replace(' ', '_')
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


async def _load_all_cogs() -> None:
    for cog_name in _all_cog_names():
        module_name = _module_name(cog_name)
        if module_name in bot.extensions:
            continue
        try:
            await bot.load_extension(module_name)
            print(f'[cog] loaded {module_name}')
        except Exception as exc:
            print(f'[cog] failed to load {module_name}: {exc}')


async def _show_cog_menu(ctx: commands.Context) -> None:
    lines = ['Cog manager', 'Usage: `cogs [start|stop|restart|add|remove] <name>`', '']
    for name in _all_cog_names():
        status = 'loaded' if _module_name(name) in bot.extensions else 'stopped'
        lines.append(f'- `{name}`: {status}')
    embed = discord.Embed(title='Cog Manager', description='\n'.join(lines), color=discord.Color.blurple())
    embed.set_footer(text=f'Prefix: {PREFIX}')
    await ctx.send(embed=embed)


def _cog_file_exists(cog_name: str) -> bool:
    module_path = os.path.join(os.path.dirname(__file__), 'cogs', f'{cog_name}.py')
    return os.path.isfile(module_path)


@bot.group(name='cogs', invoke_without_command=True)
async def cog_manager(ctx: commands.Context, action: str | None = None, cog_name: str | None = None) -> None:
    if not await ctx.bot.is_owner(ctx.author):
        return await ctx.send(f"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    if action is None and cog_name is None:
        await _show_cog_menu(ctx)
        return
    if action is None:
        action = 'status'
    action = action.lower()
    valid_actions = {'start', 'load', 'stop', 'unload', 'restart', 'reload', 'status', 'add', 'remove'}
    if action not in valid_actions:
        await ctx.send('Usage: `cogs [start|stop|restart|add|remove] <cog>` or `cogs` for the cog menu.')
        return
    resolved = _resolve_cog_name(cog_name)
    if action == 'status':
        if resolved is None:
            await _show_cog_menu(ctx)
            return
        state = 'loaded' if _module_name(resolved) in bot.extensions else 'stopped'
        await ctx.send(f'`{resolved}` is currently `{state}`.')
        return
    if action == 'add':
        if cog_name is None:
            await ctx.send('Please provide a cog name. Example: `cogs add economy`.')
            return
        candidate = cog_name.strip().replace('-', '_').replace(' ', '_')
        if not candidate:
            await ctx.send('Please provide a valid cog name.')
            return
        if candidate in _all_cog_names():
            await ctx.send(f'`{candidate}` is already enabled in the cog list.')
            return
        if not _cog_file_exists(candidate):
            await ctx.send(f'`{candidate}` was not found in the `cogs/` folder.')
            return
        module_name = _module_name(candidate)
        try:
            if module_name not in bot.extensions:
                await bot.load_extension(module_name)
            _persist_cog_names([*COG_NAMES, candidate])
            EXTERNAL_COGS[:] = [name for name in EXTERNAL_COGS if name != candidate]
            await ctx.send(f'<:approve:1517452125687513158> Cog `{candidate}` added and loaded.')
            print(f'[cog] added {module_name}')
        except Exception as exc:
            await ctx.send(f'<:disapprove:1517452151012589662> Failed to load `{candidate}`: {exc}')
            print(f'[cog] failed to add {module_name}: {exc}')
        return
    if action == 'remove':
        if cog_name is None:
            await ctx.send('Please provide a cog name. Example: `cogs remove economy`.')
            return
        candidate = cog_name.strip().replace('-', '_').replace(' ', '_')
        if not candidate:
            await ctx.send('Please provide a valid cog name.')
            return
        if candidate not in _all_cog_names():
            await ctx.send(f'`{candidate}` is not active in the cog list.')
            return
        module_name = _module_name(candidate)
        if module_name in bot.extensions:
            await bot.unload_extension(module_name)
        if candidate in EXTERNAL_COGS:
            EXTERNAL_COGS.remove(candidate)
        _persist_cog_names([name for name in COG_NAMES if name != candidate])
        await ctx.send(f'<:disapprove:1517452151012589662> Cog `{candidate}` removed and unloaded.')
        print(f'[cog] removed {module_name}')
        return
    if resolved is None:
        await ctx.send('Please provide a valid cog name. Example: `cogs restart economy`.')
        return
    module_name = _module_name(resolved)
    if action == 'start' or action == 'load':
        if module_name in bot.extensions:
            await ctx.send(f'`{resolved}` is already loaded.')
            return
        await bot.load_extension(module_name)
        await ctx.send(f'<:approve:1517452125687513158> Cog `{resolved}` started')
        print(f'[cog] started {module_name}')
        return
    if action == 'stop' or action == 'unload':
        if module_name not in bot.extensions:
            await ctx.send(f'`{resolved}` is not loaded.')
            return
        await bot.unload_extension(module_name)
        await ctx.send(f'<:disapprove:1517452151012589662> Cog `{resolved}` stopped')
        print(f'[cog] stopped {module_name}')
        return
    if module_name not in bot.extensions:
        await ctx.send(f'<:approve:1517452125687513158> Cog `{resolved}` restarted by loading it first')
        print(f'[cog] restarted {module_name}')
        return
    await bot.reload_extension(module_name)
    await ctx.send(f'<:approve:1517452125687513158> Cog `{resolved}` restarted')
    print(f'[cog] restarted {module_name}')


@bot.command(name='sync')
async def sync_commands(ctx: commands.Context) -> None:
    if not await ctx.bot.is_owner(ctx.author):
        return await ctx.send(f"<:disapprove:1517452151012589662> the {PREFIX} prefix is restricted to the bot owner only.")

    try:
        async with ctx.typing():
            if ctx.guild is not None:
                await ctx.bot.tree.sync(guild=ctx.guild)
            await ctx.bot.tree.sync()
        await ctx.send('<:approve:1517452125687513158> Command tree synced successfully.')
        print('[bot] synced application commands')
    except Exception as exc:
        await ctx.send(f'<:disapprove:1517452151012589662> Failed to sync commands: {exc}')
        print(f'[bot] failed to sync command tree: {exc}')


async def _startup() -> None:
    await _load_all_cogs()


if __name__ == '__main__':
    try:
        main.start_backup_scheduler(interval_seconds=12 * 60 * 60)
        print('[backup] scheduler started before bot login')
    except Exception as exc:
        print(f'[backup] startup scheduler failed before login: {exc}')
    asyncio.run(_startup())
    bot.run(TOKEN)