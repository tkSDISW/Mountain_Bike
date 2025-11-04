# se_agent/tools/render_prompt.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from jinja2 import Environment, StrictUndefined

from se_agent.core.tool_patterns import register_tool, TransformTool
from se_agent.mcp.artifact_registry import ArtifactRegistry

__all__ = ["RenderPromptTool"]

@register_tool
class RenderPromptTool(TransformTool):
    """
    Transform: Render a prompt from a `prompt_spec` artifact using either a variables dict
    **or** an ordered list of quoted string arguments. Optionally persist a first‑class `prompt` artifact.

    Precedence per variable:
      1) user‑supplied variables dict
      2) positional args (mapped in the order of `spec.variables`)
      3) default in `spec.variables[i].default`
      4) error if marked required and still missing

    Returns a dict with a short message, the fully‑rendered prompt text, the resolved variables,
    and (if `persist=true`) the new `prompt` artifact id.
    """

    TOOL_NAME = "render_prompt"
    DESCRIPTION = (
        "RENDERS A PROMPT FROM A PROMPT_SPEC ARTIFACT USING QUOTED STRINGS OR A VARIABLES DICT; CAN PERSIST AS A PROMPT ARTIFACT."
    )
    CATEGORY = "transform"
    USAGE = (
        "Provide a prompt_spec by name or id, plus either `variables` (a dict) or `args` (a list of quoted strings)."
    )

    ARTIFACTS: Dict[str, Any] = {
        "prompt": {
            "fields": {
                "text": {"type": "string"},
                "resolved": {"type": "dict"},
                "prompt_key": {"type": "string"},
                "prompt_title": {"type": "string"},
                "source_prompt_spec": {"type": "string"},
                "generated_at": {"type": "string"}
            },
            "schema_version": "1.0",
            "description": "Rendered prompt text with resolved variables and provenance."
        }
    }

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "prompt_spec_name": {"type": "string", "required": False, "description": "Name of a prompt_spec artifact."},
            "prompt_spec_id": {"type": "string", "required": False, "description": "ID of a prompt_spec artifact."},
            "variables": {"type": "dict", "required": False, "description": "Dict of variable overrides {name: value}."},
            "args": {"type": "list", "required": False, "description": "Ordered list of quoted strings mapped to spec.variables order."},
            "persist": {"type": "boolean", "required": False, "description": "If true, creates a 'prompt' artifact with the rendered text."},
            "name": {"type": "string", "required": False, "description": "Optional name for the prompt artifact when persist=true."}
        },
        "outputs": {
            "prompt_artifact_id": {"type": "prompt", "remember": True, "description": "ID of created prompt artifact (when persist=true)."}
        }
    }

    # Classic attributes for listers
    name = TOOL_NAME
    description = "Render prompt text from a prompt_spec and inputs (variables or args); can persist as a prompt artifact."

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

    # ---------- variable resolution ----------
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

    def _resolve_variables(self, spec: Dict[str, Any], user_vars: Optional[Dict[str, Any]], args: Optional[List[Any]]) -> Dict[str, Any]:
        user_vars = user_vars or {}
        args = list(args or [])
        ordered_defs = list(spec.get("variables") or [])
        resolved: Dict[str, Any] = {}

        # Fill from args in declared order, overruled by variables dict
        for idx, vdef in enumerate(ordered_defs):
            name = vdef.get("name")
            val = user_vars.get(name, None)
            if val is None and idx < len(args):
                val = args[idx]
            if val is None:
                val = vdef.get("default")
            # Coerce/validate
            val = self._coerce(val, vdef)
            # Required check
            if vdef.get("required") and (val is None or (isinstance(val, str) and val == "")):
                raise ValueError(f"Missing required variable '{name}'")
            resolved[name] = val
        return resolved

    # ---------- core ----------
    def transform(
        self,
        input_data: Dict[str, Any],
        artifacts: ArtifactRegistry,
        package_name: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        pkg = self._pkg(artifacts, package_name)
        if not pkg:
            raise ValueError("No artifact registry or active package.")

        spec_name = input_data.get("prompt_spec_name")
        spec_id = input_data.get("prompt_spec_id")
        vars_input = input_data.get("variables")
        args_input = input_data.get("args")

        art = None
        if spec_name:
            art = self._get_by_name(artifacts, pkg, spec_name)
        if not art and spec_id:
            art = self._get_by_id(artifacts, pkg, spec_id)
        if not art:
            raise ValueError("prompt_spec artifact not found.")

        spec = getattr(art, "content", {}) or {}
        template = spec.get("template")
        if not isinstance(template, str) or not template.strip():
            raise ValueError("prompt_spec missing a 'template' string.")

        resolved = self._resolve_variables(spec, vars_input, args_input)

        env = Environment(undefined=StrictUndefined, autoescape=False, trim_blocks=True, lstrip_blocks=True)
        text = env.from_string(template).render(**resolved)

        meta = {
            "ui_summary": f"Rendered '{spec.get('title') or spec.get('key')}'",
            "resolved": resolved,
            "prompt_key": spec.get("key"),
            "prompt_title": spec.get("title"),
        }
        return text, meta

    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_: Any) -> Dict[str, Any]:
        text, meta = self.transform(input_data, artifacts, package_name)
        preview = text if len(text) <= 2000 else text[:2000] + "…"

        persist = bool(input_data.get("persist"))
        result = {
            "message": meta.get("ui_summary", "Rendered prompt"),
            "rendered": text,
            "resolved": meta.get("resolved", {}),
            "content_preview": preview,
        }
        if persist:
            pkg = package_name or getattr(artifacts, "active_package", None)
            if not pkg:
                raise ValueError("No artifact registry or active package to persist prompt.")
            content = {
                "text": text,
                "resolved": result["resolved"],
                "prompt_key": meta.get("prompt_key"),
                "prompt_title": meta.get("prompt_title"),
                "source_prompt_spec": meta.get("prompt_key"),
                "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            metadata = {"ui_summary": meta.get("ui_summary"), "name": input_data.get("name") or f"{meta.get('prompt_key','prompt')}_run"}
            art = artifacts.add_artifact(pkg, "prompt", content, metadata)
            result["artifact_ids"] = {"prompt_artifact_id": getattr(art, "id", None)}
        return result

