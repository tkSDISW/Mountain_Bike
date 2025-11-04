# se_agent/tools/build_prompt_from_notebook.py
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import nbformat
from nbclient import NotebookClient

from se_agent.core.tool_patterns import  register_tool, TransformTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage

__all__ = ["BuildPromptFromNotebookTool"]

@register_tool
class BuildPromptFromNotebookTool(TransformTool):
    """
    Transform: Execute a notebook (found by name within a prompt_path artifact) that emits
    a prompt JSON via cell output, and save it as a typed prompt_spec artifact.

    Requires a previously created prompt_path artifact (from load_prompt_path).

    Inputs (contract):
      • prompt_path_name | prompt_path_id : existing prompt_path artifact (directory of notebooks)
      • prompt_name                      : notebook name to execute (basename without extension or exact filename)
      • name                             : optional friendly name for created prompt_spec artifact
      • timeout_sec                      : optional execute timeout (default 180s)
      • recursive                        : optional search subdirectories (default False)
      • kernel_name                      : optional kernel override (defaults to notebook kernelspec or 'python3')

    Behavior:
      1) Resolve the prompt_path artifact to a directory.
      2) Find an .ipynb matching the given prompt_name.
      3) Execute notebook with nbclient.
      4) Capture the first JSON payload from a cell tagged 'prompt_json' (application/json preferred).
      5) Persist as prompt_spec artifact (adds source_notebook + generated_at).

    Returns:
      {"message": "✅ Prompt built: id='xxxx' (key)", "artifact_ids": {"prompt_spec_artifact_id": "..."}}
    """

    TOOL_NAME = "build_prompt_from_notebook"
    DESCRIPTION = (
        "EXECUTES A PROMPT NOTEBOOK (FOUND USING A PROMPT_PATH ARTIFACT) AND SAVES ITS JSON AS A PROMPT_SPEC ARTIFACT."
    )
    CATEGORY = "transform"
    USAGE = "Use after load_prompt_path. Pass the prompt_path and a prompt_name to run."

    ARTIFACTS: Dict[str, Any] = {
        "prompt_spec": {
            "fields": {
                "key": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "version": {"type": "string"},
                "template": {"type": "string"},
                "variables": {"type": "list"},
                "tags": {"type": "list"},
                "source_notebook": {"type": "path"},
                "generated_at": {"type": "string"},
            },
            "schema_version": "1.0",
            "description": "Executable-prompt specification produced by a notebook.",
        }
    }

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "prompt_path_name": {"type": "string", "required": False, "description": "Name of a prompt_path artifact."},
            "prompt_path_id": {"type": "string", "required": False, "description": "ID of a prompt_path artifact."},
            "prompt_name": {"type": "string", "required": True, "description": "Notebook name (with or without .ipynb)."},
            "name": {"type": "string", "required": False, "description": "Friendly name for the created prompt_spec."},
            "timeout_sec": {"type": "integer", "required": False, "description": "Execution timeout in seconds (default 180)."},
            "recursive": {"type": "boolean", "required": False, "description": "Search subdirectories for notebook (default False)."},
            "kernel_name": {"type": "string", "required": False, "description": "Jupyter kernel to use (defaults to notebook kernelspec or 'python3')."}
        },
        "outputs": {
            "prompt_spec_artifact_id": {"type": "prompt_spec", "remember": True, "description": "Created prompt_spec artifact id."}
        }
    }

    # Classic attributes for listers
    name = TOOL_NAME
    description = "Execute notebook → capture prompt JSON (cell tagged 'prompt_json') → persist prompt_spec."
    artifact_type = "prompt_spec"

    # ---------- helpers ----------
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

    def _walk(self, root: str):
        for r, _, files in os.walk(root):
            for f in files:
                yield os.path.join(r, f)

    def _find_notebook(self, root: str, prompt_name: str, recursive: bool) -> str:
        want = prompt_name if prompt_name.lower().endswith(".ipynb") else f"{prompt_name}.ipynb"
        # Try exact file in root
        candidate = os.path.join(root, want)
        if os.path.exists(candidate):
            return candidate
        # Try relaxed variants (spaces/underscores/case)
        normalized = want.lower().replace(" ", "_")
        if recursive:
            entries = list(self._walk(root))
        else:
            entries = [os.path.join(root, e) for e in os.listdir(root)]
        for path in entries:
            base = os.path.basename(path)
            if not base.lower().endswith(".ipynb"):
                continue
            if base == want or base.lower() == want.lower() or base.lower().replace(" ", "_") == normalized:
                return path
        raise ValueError(f"Prompt notebook not found: '{prompt_name}' under {root}")

    def _resolve_kernel(self, nb: nbformat.NotebookNode, prefer: Optional[str]) -> str:
        if isinstance(prefer, str) and prefer.strip():
            return prefer
        ks = (nb.metadata or {}).get("kernelspec", {}) if hasattr(nb, "metadata") else {}
        return ks.get("name") or ks.get("kernel_name") or "python3"

    def _execute_notebook(self, nb_path: str, timeout: Optional[int], kernel_name: Optional[str]) -> nbformat.NotebookNode:
        nb = nbformat.read(nb_path, as_version=4)
        kname = self._resolve_kernel(nb, kernel_name)
        client = NotebookClient(nb, timeout=timeout or 180, kernel_name=kname, allow_errors=False)
        client.execute()
        return nb

    def _collect_prompt_from_outputs(self, nb: nbformat.NotebookNode) -> Dict[str, Any]:
        # Prefer a code cell tagged 'prompt_json' with JSON output
        for cell in nb.cells:
            if cell.get("cell_type") != "code":
                continue
            tags = set(cell.get("metadata", {}).get("tags", []))
            if "prompt_json" not in tags:
                continue
            for out in cell.get("outputs", []):
                data = out.get("data", {})
                if "application/json" in data:
                    return data["application/json"]
                if "text/plain" in data:
                    try:
                        return json.loads(data["text/plain"])
                    except Exception:
                        pass
        raise RuntimeError("No JSON found in executed notebook cells tagged 'prompt_json'.")

    # ---------- core ----------
    def transform(
        self,
        input_data: Dict[str, Any],
        artifacts: ArtifactRegistry,
        package_name: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        pkg = self._pkg(artifacts, package_name)
        if not pkg:
            raise ValueError("No artifact registry or active package.")

        path_name = input_data.get("prompt_path_name")
        path_id = input_data.get("prompt_path_id")
        prompt_name = input_data.get("prompt_name")
        recursive = bool(input_data.get("recursive"))

        if not (path_name or path_id):
            raise ValueError("Provide prompt_path_name or prompt_path_id.")
        if not isinstance(prompt_name, str) or not prompt_name.strip():
            raise ValueError("prompt_name must be a non-empty string.")

        art = None
        if path_name:
            art = self._get_by_name(artifacts, pkg, path_name)
        if not art and path_id:
            art = self._get_by_id(artifacts, pkg, path_id)
        if not art:
            raise ValueError("prompt_path artifact not found.")

        content = getattr(art, "content", {}) or {}
        root = content.get("directory_path")
        if not isinstance(root, str) or not root:
            raise ValueError("prompt_path artifact is missing a valid 'directory_path'.")

        nb_path = self._find_notebook(root, prompt_name, recursive)
        nb = self._execute_notebook(nb_path, input_data.get("timeout_sec"), input_data.get("kernel_name"))
        prompt = self._collect_prompt_from_outputs(nb)

        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        prompt["source_notebook"] = nb_path
        prompt["generated_at"] = now
        # Minimal validation
        for k in ("key", "template"):
            if not prompt.get(k):
                raise ValueError(f"Prompt JSON missing required field: {k}")

        meta = {
            "ui_summary": f"Prompt: {prompt.get('title') or prompt.get('key')} • v{prompt.get('version','')}",
            "key": prompt.get("key"),
            "title": prompt.get("title"),
            "generated_at": now,
            "source_notebook": nb_path,
            "prompt_path_name": getattr(art, "name", None),
        }
        name = input_data.get("name") or f"{prompt.get('key','prompt')}_spec"
        meta["name"] = name
        return prompt, meta

    # ---------- entrypoint ----------
    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_: Any) -> Dict[str, Any]:
        content, meta = self.transform(input_data, artifacts, package_name)
        pkg = self._pkg(artifacts, package_name)
        art = artifacts.add_artifact(pkg, "prompt_spec", content, meta)
        if meta.get("name"):
            art.name = meta["name"]
        return {
            "message": f"✅ Prompt built: id='{getattr(art,'id','')[:8]}' ({content.get('key')})",
            "artifact_ids": {"prompt_spec_artifact_id": getattr(art, "id", None)},
        }
