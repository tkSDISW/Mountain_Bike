"""
agent.tools public API.

Re-exports:
- CSV tools
- Search tools
- BPMN tools
- Capella tools (present only if `capellambse` is installed)

Also exposes:
- available_tools(): list[str] of names actually importable (useful for sanity checks)
"""

from __future__ import annotations
import importlib.util

# ---- CSV (always available) ----
from .csv_tools import (
    write_csv,
    read_csv,
    write_leveled_csv,
    read_leveled_csv,
)

# ---- Search (always available) ----
from .search_tools import search_model_object

# ---- BPMN (stubs currently) ----
from .bpmn_tools import bpmn_to_capella, capella_to_bpmn

# ---- Capella tools (module imports fine even if capella isn't installed;
#      availability is detected via importlib.util.find_spec) ----
from .capella_tools import (
    apply_description,
    add_logical_components,
    show_context_diagram,
)

_HAS_CAPELLA = importlib.util.find_spec("capellambse") is not None


def available_tools() -> list[str]:
    """Return the names of tools that are actually usable in this environment."""
    names = [
        "write_csv", "read_csv", "write_leveled_csv", "read_leveled_csv",
        "search_model_object",
        "bpmn_to_capella", "capella_to_bpmn",
    ]
    if _HAS_CAPELLA:
        names += ["apply_description", "add_logical_components", "show_context_diagram"]
    return names


def __getattr__(name: str):
    """
    Friendly message if someone imports Capella tools directly when Capella isn't available.
    (PEP 562 module-level getattr)
    """
    capella_names = {"apply_description", "add_logical_components", "show_context_diagram"}
    if name in capella_names and not _HAS_CAPELLA:
        raise ImportError(
            f"{name} is unavailable because `capellambse` is not installed. "
            "Install Capella dependencies to enable Capella tools."
        )
    raise AttributeError(name)


__all__ = [
    # csv
    "write_csv",
    "read_csv",
    "write_leveled_csv",
    "read_leveled_csv",
    # search
    "search_model_object",
    # bpmn
    "bpmn_to_capella",
    "capella_to_bpmn",
]

if _HAS_CAPELLA:
    __all__ += ["apply_description", "add_logical_components", "show_context_diagram"]

