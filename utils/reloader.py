"""Reloading a cog together with the project modules it depends on (save.py and utils/*).

A dependency is reloaded when its file changed since it was loaded, or when one of its own
dependencies was reloaded (so it picks up the new code). Unchanged modules are left alone, so
restarting one cog does not reset the state of modules nothing changed in.

Module-level state listed in a module's `_KEEP_ON_RELOAD` survives the reload.
"""

import ast
import importlib
import importlib.util
import os
import sys

# Never reloaded: this module itself and the package marker.
_NEVER_RELOAD = {"utils", "utils.reloader"}

# module name -> file modification time when it was last (re)loaded
_loaded_mtimes: dict[str, float] = {}


def _is_project_dependency(name: str) -> bool:
    return (name == "save" or name.startswith("utils.")) and name not in _NEVER_RELOAD


def _module_path(name: str) -> str | None:
    module = sys.modules.get(name)
    path = getattr(module, "__file__", None)
    if path is None:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            return None
        path = getattr(spec, "origin", None) if spec else None
    return path if path and os.path.isfile(path) else None


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def direct_dependencies(module_name: str) -> set[str]:
    """Project modules imported anywhere in the module's source, including inside functions."""
    path = _module_path(module_name)
    if path is None:
        return set()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), path)
    except (OSError, SyntaxError):
        return set()

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
            # "from utils import runtime" imports the module utils.runtime
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return {name for name in names if _is_project_dependency(name) and _module_path(name)}


def dependencies(module_name: str) -> list[str]:
    """All project modules the module depends on, each one listed after its own dependencies."""
    ordered: list[str] = []
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in ordered or name in visiting:
            return
        visiting.add(name)
        for dependency in sorted(direct_dependencies(name)):
            visit(dependency)
        visiting.discard(name)
        ordered.append(name)

    for dependency in sorted(direct_dependencies(module_name)):
        visit(dependency)
    return ordered


def remember_loaded_modules() -> None:
    """Record the file times of the project modules that are loaded right now."""
    for name in list(sys.modules):
        if _is_project_dependency(name) and name not in _loaded_mtimes:
            path = _module_path(name)
            if path:
                _loaded_mtimes[name] = _mtime(path)


def _changed(name: str) -> bool:
    path = _module_path(name)
    if path is None:
        return False
    if name not in _loaded_mtimes:
        # Imported after startup and never reloaded: its current file is what is running.
        _loaded_mtimes[name] = _mtime(path)
        return False
    return _mtime(path) != _loaded_mtimes[name]


def _reload_module(name: str) -> None:
    module = sys.modules[name]
    path = _module_path(name)
    # Fail on syntax errors before touching the running module.
    with open(path, "r", encoding="utf-8") as handle:
        compile(handle.read(), path, "exec")

    kept = {key: getattr(module, key) for key in getattr(module, "_KEEP_ON_RELOAD", ()) if hasattr(module, key)}
    backup = dict(module.__dict__)
    try:
        importlib.reload(module)
    except Exception:
        # Put the old module back exactly as it was.
        module.__dict__.clear()
        module.__dict__.update(backup)
        raise
    for key, value in kept.items():
        setattr(module, key, value)
    _loaded_mtimes[name] = _mtime(path)


def reload_dependencies(module_names: list[str]) -> list[str]:
    """Reload the changed project dependencies of the given cog modules. Returns what was reloaded."""
    order: list[str] = []
    for module_name in module_names:
        for name in dependencies(module_name):
            if name not in order:
                order.append(name)

    reloaded: list[str] = []
    for name in order:
        if name not in sys.modules:
            continue  # not imported yet: the next import loads the current file anyway
        if _changed(name) or direct_dependencies(name) & set(reloaded):
            try:
                _reload_module(name)
            except Exception as error:
                raise RuntimeError(f"could not reload `{name}`: {type(error).__name__}: {error}") from error
            reloaded.append(name)
    return reloaded


def modules_using(module_names: list[str], candidates: list[str]) -> list[str]:
    """The candidate modules (loaded cogs) that depend on any of the given modules."""
    targets = set(module_names)
    return [candidate for candidate in candidates if targets & set(dependencies(candidate))]
