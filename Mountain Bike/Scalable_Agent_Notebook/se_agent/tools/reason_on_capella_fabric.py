# se_agent/tools/reason_on_capella_fabric.py
from __future__ import annotations

import io
from contextlib import redirect_stdout
from typing import Any, Dict, List, Optional

from jinja2 import Environment, StrictUndefined
from se_agent.core.tool_patterns import DisplayTool
from se_agent.mcp.artifact_registry import ArtifactRegistry

__all__ = ["ReasonOnCapellaFabricTool"]


class ReasonOnCapellaFabricTool(DisplayTool):
    """
    Display: Reason on a **capella_fabric** artifact and render compact engineer-friendly HTML.

    Contracted inputs (preferred; no direct string fallbacks):
      • capella_fabric_name | capella_fabric_id : identifies a 'capella_fabric' artifact (REQUIRED)
      • prompt_spec_name    | prompt_spec_id    : identifies a 'prompt_spec' artifact   (OPTIONAL)
      • variables                               : dict of variable overrides for the prompt_spec (OPTIONAL)
      • args                                     : list of positional string args mapped to spec.variables order (OPTIONAL)

    Behavior:
      1) Load YAML from the capella_fabric artifact (expects content["yaml"]).
      2) If a prompt_spec is provided, render it with variables/args to produce a prompt string.
      3) Use Open_AI_RAG_manager.ChatGPTAnalyzer to generate HTML from YAML (+ optional prompt).
      4) Return {'message', 'html', 'displayed': True} for single-display runners.
    """

    TOOL_NAME = "reason_on_capella_fabric"
    DESCRIPTION = (
        "REASONS ON A CAPELLA_FABRIC ARTIFACT AND PRODUCES COMPACT ENGINEER-FRIENDLY HTML."
    )
    CATEGORY = "display"
    USAGE = (
        "Provide a capella_fabric by name or id; optionally pass a prompt_spec with variables or args to steer the analysis."
    )

    # No new artifacts created by this display tool
    ARTIFACTS: Dict[str, Any] = {}

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "capella_fabric_name": {"type": "string", "required": False, "description": "Name of a capella_fabric artifact."},
            "capella_fabric_id":   {"type": "string", "required": False, "description": "ID of a capella_fabric artifact."},
            "prompt_spec_name":    {"type": "string", "required": False, "description": "Name of a prompt_spec artifact (optional)."},
            "prompt_spec_id":      {"type": "string", "required": False, "description": "ID of a prompt_spec artifact (optional)."},
            "variables":           {"type": "dict",   "required": False, "description": "Variable overrides for the prompt_spec."},
            "args":                {"type": "list",   "required": False, "description": "Positional args mapped to spec.variables order."},
        },
        "outputs": {
            # display-only, but expose the HTML in case callers want to save it
            "html": {"type": "string", "remember": False, "description": "Generated HTML output."}
        }
    }

    # Classic attributes for listers
    name = TOOL_NAME
    description = "Reason on a capella_fabric; optional prompt_spec steering; returns HTML."

    # ---------- registry helpers ----------
    def _pkg(self, artifacts: ArtifactRegistry, package_name: Optional[str]) -> str:
        return package_name or getattr(artifacts, "active_package", None)

    def _get_by_name(self, artifacts: ArtifactRegistry, pkg_name: str, name: str):
        try:
            pkg = artifacts.get_package(pkg_name)
            if not pkg or not hasattr(pkg, "artifacts"):
                return None
            arts = list(pkg.artifacts.values())
            matches = [a for a in arts if getattr(a, "name", None) == name]
            if not matches:
                return None
            matches.sort(key=lambda a: getattr(a, "_created_at", 0), reverse=True)
            return matches[0]
        except Exception:
            return None

    def _get_by_id(self, artifacts: ArtifactRegistry, pkg_name: str, art_id: str):
        try:
            return artifacts.get_artifact(pkg_name, art_id)
        except Exception:
            return None

    # ---------- prompt rendering (inlined, consistent with render_prompt tool) ----------
    def _coerce(self, val: Any, vdef: Dict[str, Any]) -> Any:
        vtype = (vdef.get("type") or "string").lower()
        if val is None:
            return None
        try:
            if vtype in ("string", "uuid", "path"):
                return str(val)
            if vtype == "integer":
                return int(val)
            if vtype == "number":
                return float(val)
            if vtype == "boolean":
                if isinstance(val, bool):
                    out = val
                else:
                    s = str(val).strip().lower()
                    out = s in ("1", "true", "t", "yes", "y", "on")
                return out
            if vtype == "enum":
                enum_vals = vdef.get("enum") or []
                sval = str(val)
                if enum_vals and sval not in enum_vals:
                    raise ValueError(f"Value '{sval}' not in enum {enum_vals}")
                return sval
        except Exception as e:
            raise ValueError(f"Failed to coerce variable '{vdef.get('name')}' to type {vtype}: {e}")
        return val

    def _resolve_prompt_text(self, spec: Dict[str, Any], variables: Optional[Dict[str, Any]], args: Optional[List[Any]]) -> str:
        template = spec.get("template")
        if not isinstance(template, str) or not template.strip():
            return ""
        ordered_defs = list(spec.get("variables") or [])
        vars_in = variables or {}
        args_in = list(args or [])
        resolved: Dict[str, Any] = {}
        for idx, vdef in enumerate(ordered_defs):
            name = vdef.get("name")
            val = vars_in.get(name, None)
            if val is None and idx < len(args_in):
                val = args_in[idx]
            if val is None:
                val = vdef.get("default")
            val = self._coerce(val, vdef)
            if vdef.get("required") and (val is None or (isinstance(val, str) and val == "")):
                raise ValueError(f"Missing required variable '{name}' for prompt_spec.")
            resolved[name] = val
        env = Environment(undefined=StrictUndefined, autoescape=False, trim_blocks=True, lstrip_blocks=True)
        return env.from_string(template).render(**resolved)

    # ---------- core ----------
    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_: Any) -> Dict[str, Any]:
        pkg = self._pkg(artifacts, package_name)
        if not pkg:
            return {"message": "❌ No artifact registry or active package.", "displayed": False}

        # Resolve capella_fabric
        fab_name = input_data.get("capella_fabric_name")
        fab_id = input_data.get("capella_fabric_id")
        fab = None
        if fab_name:
            fab = self._get_by_name(artifacts, pkg, fab_name)
        if not fab and fab_id:
            fab = self._get_by_id(artifacts, pkg, fab_id)
        if not fab or getattr(fab, "type", None) != "capella_fabric":
            return {"message": "❌ capella_fabric artifact not found.", "displayed": False}

        fab_content = getattr(fab, "content", {}) or {}
        yaml_text = fab_content.get("yaml")
        if not isinstance(yaml_text, str) or not yaml_text.strip():
            return {"message": "❌ capella_fabric missing 'yaml' string content.", "displayed": False}

        # Optional prompt_spec rendering
        prompt_text = ""
        ps_name = input_data.get("prompt_spec_name")
        ps_id = input_data.get("prompt_spec_id")
        if ps_name or ps_id:
            ps = None
            if ps_name:
                ps = self._get_by_name(artifacts, pkg, ps_name)
            if not ps and ps_id:
                ps = self._get_by_id(artifacts, pkg, ps_id)
            if not ps or getattr(ps, "type", None) != "prompt_spec":
                return {"message": "❌ prompt_spec artifact not found.", "displayed": False}
            ps_content = getattr(ps, "content", {}) or {}
            try:
                prompt_text = self._resolve_prompt_text(ps_content, input_data.get("variables"), input_data.get("args"))
            except Exception as e:
                return {"message": f"❌ Failed to render prompt_spec: {e}", "displayed": False}

        # Call RAG manager
        try:
            from capella_tools import Open_AI_RAG_manager
        except Exception as e:
            return {"message": f"❌ Failed to import Open_AI_RAG_manager: {e}", "displayed": False}

        try:
            fmt = Open_AI_RAG_manager.ChatGPTAnalyzer(yaml_content=yaml_text)
            if isinstance(prompt_text, str) and prompt_text.strip():
                fmt.initial_prompt(prompt_text)

            buf = io.StringIO()
            with redirect_stdout(buf):
                html = fmt.get_response()

            return {
                "message": f"🧠 Reasoned on fabric: {getattr(fab, 'name', '')}",
                "html": html,
                "displayed": True,
            }
        except Exception as e:
            return {"message": f"❌ Reasoning failed: {e}", "displayed": False}

