
# ------------------------------
# se_agent/tools/save_into_workspace_memory.py
# ------------------------------
from __future__ import annotations
from typing import Any, Dict, Optional
import hashlib
import json

from se_agent.core.tool_patterns import register_tool, TransformTool
from se_agent.mcp.artifact_registry import ArtifactRegistry
from ._workspace_store import _pkg_name, _load_ws, _save_ws, _now_iso
from se_agent.core.governance import check_token_budget, sanitize_ok, json_serializable

__all__ = ["SaveIntoWorkspaceMemoryTool"]

@register_tool
class SaveIntoWorkspaceMemoryTool(TransformTool):
    """
    Save an arbitrary JSON-serializable value into the package-scoped workspace memory under a name.
    Also returns a one-shot injection snippet (string) the agent can append to the prompt THIS TURN ONLY.
    Governance checks: token budget and prompt-safety scan.
    """
    TOOL_NAME = "save_into_workspace_memory"
    DESCRIPTION = "SAVES A VALUE INTO WORKSPACE MEMORY UNDER A NAME; RETURNS A ONE-SHOT PROMPT INJECTION SNIPPET."
    CATEGORY = "transform"

    ARTIFACTS: Dict[str, Any] = {}

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "name": {"type": "string", "required": True, "description": "Workspace memory entry name."},
            "value": {"type": "any", "required": True, "description": "JSON-serializable content to save."},
            "max_tokens": {"type": "integer", "required": False, "description": "Override default token cap for injection governance."},
            "type": {"type": "string", "required": False, "description": "Optional semantic type hint (e.g., 'table','capella_fabric')."},
        },
        "outputs": {
            "inject_once": {"type": "string", "remember": False, "description": "Snippet to append to LLM prompt for this turn only."},
            "tokens": {"type": "integer", "remember": False},
        },
    }

    name = TOOL_NAME
    description = "Save into workspace memory and return a safe, one-shot prompt snippet."

    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_: Any) -> Dict[str, Any]:
        pkg = _pkg_name(artifacts, package_name)
        if not pkg:
            return {"message": "❌ No active package."}

        name = input_data.get("name")
        value = input_data.get("value")
        max_tokens = input_data.get("max_tokens")
        typ = input_data.get("type")

        # Governance checks
        ser = json_serializable(value)
        if not ser["ok"]:
            return {"message": ser["message"]}
        safe = sanitize_ok(value)
        if not safe["ok"]:
            return {"message": safe["message"]}
        budget = check_token_budget(name, value, max_tokens)
        if not budget["ok"]:
            return {"message": budget["message"]}

        ws_art, ws = _load_ws(artifacts, pkg)
        ws["memory"][name] = {
            "type": typ or "value",
            "value": value,
            "updated_at": _now_iso(),
        }

        # Prepare one-shot injection and digest so the agent can avoid re-injecting duplicate content in the same turn
        try:
            as_text = json.dumps(value, ensure_ascii=False)
        except Exception:
            as_text = str(value)
        digest = hashlib.sha1(as_text.encode("utf-8", errors="ignore")).hexdigest()
        ws.setdefault("injections_once", {})[name] = digest

        _save_ws(artifacts, pkg, ws_art, ws)

        snippet = (
            f"Workspace memory: {name} (type={typ or 'value'})\n"
            f"Content:\n{as_text}"
        )
        return {
            "message": f"✅ Saved '{name}' into workspace memory (tokens~{budget['tokens']:,}).",
            "inject_once": snippet,
            "tokens": budget["tokens"],
        }


