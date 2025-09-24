from typing import Any, Optional
from langchain_core.tools import tool

@tool
def bpmn_to_capella(bpmn_path: str) -> dict:
    """Stub: Convert BPMN to Capella function chain (wire later)."""
    return {"ok": True, "message": f"[STUB] Would convert BPMN at {bpmn_path} to Capella function chain"}

@tool
def capella_to_bpmn(capella_yaml: str) -> dict:
    """Stub: Convert Capella YAML to BPMN (wire later)."""
    return {"ok": True, "message": f"[STUB] Would convert Capella YAML to BPMN (input length {len(capella_yaml)})"}