from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List, Dict, Iterable
from functools import partial
from collections import OrderedDict
from pydantic import BaseModel
from langchain_core.tools import StructuredTool

@dataclass
class ToolInfo:
    name: str
    tool: Any              # @tool or StructuredTool
    category: str
    tags: List[str] = field(default_factory=list)
    description: str = ""  # optional override

class ToolRegistry:
    """Simple, explicit registry for LangChain/LangGraph tools."""
    def __init__(self):
        self._tools: "OrderedDict[str, ToolInfo]" = OrderedDict()

    # --- CRUD ---
    def add(self, info: ToolInfo, *, overwrite: bool = True) -> None:
        if not overwrite and info.name in self._tools:
            raise ValueError(f"Tool '{info.name}' already exists")
        self._tools[info.name] = info

    def get(self, name: str) -> ToolInfo | None:
        return self._tools.get(name)

    def remove(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None

    def clear(self) -> None:
        self._tools.clear()

    def count(self) -> int:
        return len(self._tools)

    # --- Views ---
    def names(self) -> List[str]:
        return list(self._tools.keys())

    def all(self) -> List[Any]:
        """Return the tool callables/StructuredTool objects for agent wiring."""
        return [ti.tool for ti in self._tools.values()]

    def by_category(self, category: str) -> List[Any]:
        return [ti.tool for ti in self._tools.values() if ti.category == category]

    def by_tags(self, *tags: str) -> List[Any]:
        tset = set(tags)
        return [ti.tool for ti in self._tools.values() if tset.issubset(ti.tags)]

    # --- Describe / list_tools support ---
    @staticmethod
    def _first_line(s: str) -> str:
        s = (s or "").strip()
        return s.splitlines()[0] if s else ""

    @staticmethod
    def _tool_description(tool: Any, override: str = "") -> str:
        if override:
            return ToolRegistry._first_line(override)
        # Prefer LangChain tool.description, then __doc__
        desc = getattr(tool, "description", "") or getattr(tool, "__doc__", "") or ""
        return ToolRegistry._first_line(desc)

    def describe(self, *, sort: bool = True) -> List[Dict]:
        items = []
        for ti in self._tools.values():
            items.append({
                "name": ti.name,
                "category": ti.category,
                "tags": ti.tags,
                "description": self._tool_description(ti.tool, ti.description),
            })
        if sort:
            items.sort(key=lambda x: (x["category"], x["name"]))
        return items

# --- list_tools plumbing (zero-arg StructuredTool) ---
class _NoArgs(BaseModel):
    """No arguments required."""
    pass

def _list_tools_impl(registry: ToolRegistry) -> dict:
    return {"message": "Here are the available MBSE tools:", "tools": registry.describe()}

def build_list_tools_tool(registry: ToolRegistry) -> StructuredTool:
    """Bind list_tools to a specific registry (no `self` in schema)."""
    return StructuredTool.from_function(
        func=partial(_list_tools_impl, registry),
        name="list_tools",
        description="List all available MBSE tools with descriptions, categories, and tags.",
        args_schema=_NoArgs,
    )
