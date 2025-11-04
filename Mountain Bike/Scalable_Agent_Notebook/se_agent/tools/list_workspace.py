
# ------------------------------
# se_agent/tools/list_workspace.py  (updated to include memory entries)
# ------------------------------
from __future__ import annotations
from typing import Any, Dict, Optional

from se_agent.core.tool_patterns import register_tool, DisplayTool
from se_agent.mcp.artifact_registry import ArtifactRegistry
from ._workspace_store import _pkg_name, _load_ws

__all__ = ["ListWorkspaceTool"]

@register_tool
class ListWorkspaceTool(DisplayTool):
    """
    Display: List the artifacts and memory entries currently registered in the active workspace store.

    - Shows `artifacts` (name → {type, artifact_id, updated_at})
    - Shows `memory` (name → {type, updated_at})
    """

    TOOL_NAME = "list_workspace"
    DESCRIPTION = "DISPLAYS THE CURRENT WORKSPACE CONTENTS: ARTIFACTS AND MEMORY ENTRIES."
    CATEGORY = "display"

    ARTIFACTS: Dict[str, Any] = {}

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "section": {"type": "string", "required": False, "description": "Optional: 'artifacts' or 'memory' to filter."},
            "type": {"type": "string", "required": False, "description": "Optional: filter by artifact or memory 'type'."}
        },
        "outputs": {
            "artifacts": {"type": "list", "remember": False, "description": "Workspace artifacts (sorted by updated_at desc)."},
            "memory": {"type": "list", "remember": False, "description": "Workspace memory entries (sorted by updated_at desc)."}
        }
    }

    name = TOOL_NAME
    description = "List workspace artifacts and memory for the active package."

    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_: Any) -> Dict[str, Any]:
        pkg = _pkg_name(artifacts, package_name)
        if not pkg:
            return {"message": "❌ No active package.", "displayed": False}

        section_filter = (input_data or {}).get("section")
        type_filter = (input_data or {}).get("type")

        _, ws = _load_ws(artifacts, pkg)
        entries = ws.get("artifacts", {}) or {}
        mem = ws.get("memory", {}) or {}

        def _sorted_items(d: Dict[str, Dict[str, Any]]):
            items = []
            for name, meta in d.items():
                row = {
                    "name": name,
                    "type": meta.get("type"),
                    "updated_at": meta.get("updated_at"),
                }
                if "artifact_id" in meta:
                    row["artifact_id"] = meta.get("artifact_id")
                items.append(row)
            # Sort by updated_at desc (missing last)
            def _key(x):
                t = x.get("updated_at")
                return (0, t) if isinstance(t, str) and t else (1, "")
            items.sort(key=_key, reverse=True)
            return items

        items_art = _sorted_items(entries)
        items_mem = _sorted_items(mem)

        if type_filter:
            items_art = [x for x in items_art if (x.get("type") == type_filter)]
            items_mem = [x for x in items_mem if (x.get("type") == type_filter)]
        if section_filter == "artifacts":
            items_mem = []
        elif section_filter == "memory":
            items_art = []

        msg = f"🧰 Workspace for '{pkg}' — artifacts: {len(items_art)}, memory: {len(items_mem)}"
        return {
            "message": msg,
            "artifacts": items_art,
            "memory": items_mem,
            "displayed": True,
        }
