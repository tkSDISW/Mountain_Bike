from typing import Any, Optional
import json
from langchain_core.tools import tool



# --- Capella model resolver (accepts model OR path/resources) ---
def _resolve_capella_model(model_or_path: Any, resources: Optional[dict] = None):
    """
    Accept either:
      - a live capellambse.MelodyModel instance, or
      - a string path to the .melodymod / project dir, optionally with resources,
      - a dict like {"path": "...", "resources": {...}}.
    Returns (model, opened_here: bool) where opened_here says if we constructed it.
    """
    try:
        import capellambse
    except ImportError:
        return None, False  # caller will stub/skip

    # Already a model?
    if hasattr(model_or_path, "__class__") and model_or_path.__class__.__name__ == "MelodyModel":
        return model_or_path, False

    # dict payload?
    if isinstance(model_or_path, dict):
        p = model_or_path.get("path")
        r = model_or_path.get("resources", resources)
        if not p:
            return None, False
        return capellambse.MelodyModel(p, resources=r), True

    # plain path?
    if isinstance(model_or_path, str):
        return capellambse.MelodyModel(model_or_path, resources=resources), True

    return None, False



@tool
def apply_description(model_or_path: object, uuid: str, description: str, resources: dict | None = None) -> dict:
    """
    Update the textual description of a Capella element.
    Accepts either a live model or a path (+ optional resources).
    """
    model, opened_here = _resolve_capella_model(model_or_path, resources)
    if model is None:
        # STUB: no capellambse — return intended action
        return {"ok": False, "message": "[STUB] capellambse not available", "uuid": uuid, "description": description}

    # TODO: replace with actual model indexing & property update
    try:
        # exemplar (pseudo): elem = model.by_uuid(uuid); elem.description = description; model.save()
        # For now, just pretend:
        updated = True
        return {"ok": updated, "uuid": uuid, "message": "Description updated"}
    finally:
        # if you opened a model here and want to close, do so (capellambse usually uses on-disk project)
        pass
@tool
def add_logical_components(model_or_path: object, names: list[str], parent_uuid: str | None = None, resources: dict | None = None) -> dict:
    """
    Create Logical Components in the Capella model under an optional parent UUID.
    Accepts either a live model or a path (+ optional resources).
    """
    model, opened_here = _resolve_capella_model(model_or_path, resources)
    if model is None:
        return {"ok": False, "message": "[STUB] capellambse not available", "created": names}

    # TODO: replace with actual creation via capellambse APIs
    created = [{"name": n, "uuid": f"uuid-{abs(hash(n)) % 10**8:08d}"} for n in names]
    return {"ok": True, "created": created, "parent_uuid": parent_uuid}

@tool
def show_context_diagram(model_or_path: object, uuid: str, resources: dict | None = None) -> dict:
    """
    Stub: Render a context diagram for a model element (wire to capellambse later).
    Accepts either a live model or a path (+ optional resources).
    """
    model, _ = _resolve_capella_model(model_or_path, resources)
    if model is None:
        return {"ok": False, "message": "[STUB] capellambse not available", "uuid": uuid}
    # TODO: hook capellambse context diagram export, return file path
    return {"ok": True, "uuid": uuid, "message": "[STUB] Context diagram would be rendered"}



