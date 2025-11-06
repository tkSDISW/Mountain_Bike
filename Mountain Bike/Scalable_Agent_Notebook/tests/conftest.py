# tests/conftest.py
import importlib
import os
import pathlib
import sys
from types import ModuleType

def pytest_sessionstart(session):
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

def _iter_tools_from_registry(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield v
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            yield v
    elif isinstance(obj, ModuleType):
        for name in dir(obj):
            val = getattr(obj, name)
            if hasattr(val, "IO_SCHEMA") or hasattr(val, "io_schema"):
                if callable(getattr(val, "run", None)):
                    yield val

def _iter_tools_from_module(mod: ModuleType):
    reg = getattr(mod, "tool_registry", None) or getattr(mod, "TOOLS", None)
    if reg is not None:
        yield from _iter_tools_from_registry(reg)
    for name in dir(mod):
        val = getattr(mod, name)
        if hasattr(val, "IO_SCHEMA") or hasattr(val, "io_schema"):
            if callable(getattr(val, "run", None)):
                yield val

def discover_tools():
    # 1) Try central registry
    tools = []
    try:
        reg_mod = importlib.import_module("se_agent.core.tool_registry")
        tools.extend(list(_iter_tools_from_module(reg_mod)))
    except Exception:
        pass

    # 2) Scan se_agent.tools
    try:
        tools_pkg = importlib.import_module("se_agent.tools")
        pkg_path = pathlib.Path(tools_pkg.__file__).parent
        for py in pkg_path.rglob("*.py"):
            if py.name == "__init__.py" or py.name.startswith("test_"):
                continue
            mod_name = f"se_agent.tools.{py.relative_to(pkg_path).with_suffix('').as_posix().replace('/', '.')}"
            try:
                mod = importlib.import_module(mod_name)
                tools.extend(list(_iter_tools_from_module(mod)))
            except Exception:
                continue
    except Exception:
        pass

    # De-dupe by object id, preserve order
    seen = set(); uniq = []
    for t in tools:
        k = id(t)
        if k not in seen:
            uniq.append(t); seen.add(k)
    return uniq

def pytest_generate_tests(metafunc):
    if "tool_obj" in metafunc.fixturenames:
        metafunc.parametrize("tool_obj", discover_tools(),
                             ids=lambda t: getattr(t, "__name__", repr(t)))
