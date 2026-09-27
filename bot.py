print("------------------------ [starting] ------------------------")
import os
import sys

# Fail with a clear message when an upload missed project files (e.g. a new utils module).
_ROOT = os.path.dirname(os.path.abspath(__file__))
_REQUIRED_FILES = [
    'save.py',
    'cogs/__init__.py',
    'utils/__init__.py', 'utils/audit.py', 'utils/automod.py', 'utils/banners.py', 'utils/counters.py',
    'utils/economy.py', 'utils/formatting.py', 'utils/permissions.py', 'utils/reloader.py',
    'utils/runtime.py', 'utils/user_settings.py', 'utils/views.py',
]
_missing = [path for path in _REQUIRED_FILES if not os.path.isfile(os.path.join(_ROOT, path))]
if _missing:
    print(f"[bot] missing project files in {_ROOT}: {', '.join(_missing)}")
    sys.exit(1)

import re
import traceback

import discord
from discord.ext import commands
from dotenv import load_dotenv

import save
from utils import reloader, runtime

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
        # Runs after login, in the bot's own event loop, so cogs can start tasks right away.
        print('[bot] setup hook')
        await _load_all_cogs()
        reloader.remember_loaded_modules()
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

        loop_cog = self.get_cog('LoopCog')
        if loop_cog is not None:
            loop_cog.start_tasks()

        levels_cog = self.get_cog('LevelsCog')
        if levels_cog is not None and hasattr(levels_cog, 'start_tasks'):
            levels_cog.start_tasks()

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

runtime.bot = bot


def _module_name(cog_name: str) -> str:
    return f'cogs.{cog_name}'


def _load_cog_names() -> list[str]:
    raw_value = (
        os.getenv('COGS')
        or os.getenv('COG_NAMES')
        or os.getenv('BOT_COGS')
        or ''
    )
    if not raw_value:
        return []

    names = []
    seen = set()
    for part in re.split(r'[\n,]+', raw_value):
        candidate = str(part).strip().replace('-', '_').replace(' ', '_')
        if not candidate or candidate.lower() == 'none':
            continue
        if candidate not in seen:
            names.append(candidate)
            seen.add(candidate)
    return names


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

    COG_NAMES = filtered


COG_NAMES = _load_cog_names()
EXTERNAL_COGS: list[str] = []


def _resolve_cog_name(raw_name: str | None) -> str | None:
    if raw_name is None:
        return None
    normalized = raw_name.strip().lower().replace('-', '_').replace(' ', '_')
    if not normalized:
        return None
    if normalized == 'all':
        return 'all'
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
    cog_names = _all_cog_names()
    if not cog_names:
        print('[cog] no cogs configured from environment; nothing loaded')
        return

    for cog_name in cog_names:
        module_name = _module_name(cog_name)
        if module_name in bot.extensions:
            continue
        try:
            await bot.load_extension(module_name)
            print(f'[cog] loaded {module_name}')
        except Exception as exc:
            print(f'[cog] failed to load {module_name}: {type(exc).__name__}: {exc}')
            traceback.print_exc()


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
    valid_actions = {'start', 'load', 'stop', 'unload', 'restart', 'reload', 'status', 'add', 'remove', 'enable', 'disable'}
    if action not in valid_actions:
        await ctx.send('Usage: `cogs [add/start|remove/stop|reload/restart] <cog>` or `cogs` for the cog menu.')
        return

    if action in {'add', 'start', 'load', 'enable'}:
        if cog_name is None:
            await ctx.send('Please provide a cog name. Example: `cogs add economy`.')
            return
        candidate = cog_name.strip().replace('-', '_').replace(' ', '_')
        if not candidate:
            await ctx.send('Please provide a valid cog name.')
            return
        if candidate.lower() == 'all':
            await ctx.send('`ALL` is not valid here. Use a single cog name.')
            return
        if not _cog_file_exists(candidate):
            await ctx.send(f'`{candidate}` was not found in the `cogs/` folder.')
            return

        module_name = _module_name(candidate)
        current_names = list(COG_NAMES)
        if candidate not in current_names:
            _persist_cog_names([*current_names, candidate])
        try:
            if module_name not in bot.extensions:
                await bot.load_extension(module_name)
            print(f'[cog] started {module_name}')
            await ctx.send(f'<:approve:1517452125687513158> Cog `{candidate}` started.')
        except Exception as exc:
            print(f'[cog] failed to enable {module_name}: {type(exc).__name__}: {exc}')
            traceback.print_exc()
            await ctx.send(f'<:disapprove:1517452151012589662> Failed to enable `{candidate}`: {exc}')
        return

    if action in {'remove', 'stop', 'unload', 'disable'}:
        if cog_name is None:
            await ctx.send('Please provide a cog name. Example: `cogs remove economy`.')
            return
        candidate = cog_name.strip().replace('-', '_').replace(' ', '_')
        if not candidate:
            await ctx.send('Please provide a valid cog name.')
            return
        if candidate.lower() == 'all':
            await ctx.send('`ALL` is not valid here. Use a single cog name.')
            return
        if candidate not in _all_cog_names():
            await ctx.send(f'`{candidate}` is not active in the cog list.')
            return

        module_name = _module_name(candidate)
        try:
            if module_name in bot.extensions:
                await bot.unload_extension(module_name)
            _persist_cog_names([name for name in COG_NAMES if name != candidate])
            print(f'[cog] stopped {module_name}')
            await ctx.send(f'<:disapprove:1517452151012589662> Cog `{candidate}` stopped.')
        except Exception as exc:
            print(f'[cog] failed to stop {module_name}: {type(exc).__name__}: {exc}')
            traceback.print_exc()
            await ctx.send(f'<:disapprove:1517452151012589662> Failed to stop `{candidate}`: {exc}')
        return

    if action in {'reload', 'restart'}:
        if cog_name is None:
            await ctx.send('Please provide a cog name. Example: `cogs reload economy` or `cogs reload all`.')
            return
        resolved = _resolve_cog_name(cog_name)
        if resolved is None:
            await ctx.send('Please provide a valid cog name. Example: `cogs restart economy`.')
            return
        await _restart_cogs(ctx, resolved)
        return

    if action == 'status':
        if cog_name is None:
            await _show_cog_menu(ctx)
            return
        resolved = _resolve_cog_name(cog_name)
        if resolved is None:
            await _show_cog_menu(ctx)
            return
        state = 'loaded' if _module_name(resolved) in bot.extensions else 'stopped'
        await ctx.send(f'`{resolved}` is currently `{state}`.')
        return


async def _restart_cogs(ctx: commands.Context, resolved: str) -> None:
    """Restart one cog (or `all`), reloading the changed save.py/utils modules it uses first."""
    loaded_names = [name for name in _all_cog_names() if _module_name(name) in bot.extensions]
    targets = loaded_names if resolved == 'all' else [resolved]
    target_modules = [_module_name(name) for name in targets]

    try:
        reloaded_modules = reloader.reload_dependencies(target_modules)
    except RuntimeError as exc:
        print(f'[cog] dependency reload failed: {exc}')
        traceback.print_exc()
        await ctx.send(f'<:disapprove:1517452151012589662> Nothing was restarted, {exc}')
        return
    for module_name in reloaded_modules:
        print(f'[cog] reloaded dependency {module_name}')

    failed = []
    for name, module_name in zip(targets, target_modules):
        try:
            if module_name in bot.extensions:
                await bot.reload_extension(module_name)
            else:
                await bot.load_extension(module_name)
            print(f'[cog] restarted {module_name}')
        except Exception as exc:
            print(f'[cog] failed to restart {module_name}: {type(exc).__name__}: {exc}')
            traceback.print_exc()
            failed.append(f'`{name}`: {exc}')

    if failed:
        lines = ['<:disapprove:1517452151012589662> Failed to restart ' + ', '.join(failed)]
    elif resolved == 'all':
        lines = [f'<:approve:1517452125687513158> All {len(targets)} cogs restarted.']
    else:
        lines = [f'<:approve:1517452125687513158> Cog `{resolved}` restarted.']

    if reloaded_modules:
        lines.append('Also reloaded: ' + ', '.join(f'`{name}`' for name in reloaded_modules))
        others = reloader.modules_using(
            reloaded_modules,
            [_module_name(name) for name in loaded_names if name not in targets],
        )
        if others:
            names = ', '.join(f"`{module_name.removeprefix('cogs.')}`" for module_name in others)
            verb = 'uses' if len(others) == 1 else 'use'
            lines.append(f'<:warning:1517452174991556758> {names} also {verb} these and keep the old version until restarted (or use `cogs restart all`).')
    await ctx.send('\n'.join(lines))


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


if __name__ == '__main__':
    try:
        save.start_backup_scheduler(interval_seconds=12 * 60 * 60)
    except Exception as exc:
        print(f'[backup] startup scheduler failed before login: {exc}')
    # Cogs are loaded in setup_hook, after login.
    bot.run(TOKEN)
