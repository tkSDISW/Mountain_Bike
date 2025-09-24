from typing import Any, Optional
from langchain_core.tools import tool
@tool
def search_model_object(json_path: str, query: str | None = None, max_results: int = 10) -> dict:
    """
    Search a JSON file of model objects. JSON can be a list[dict] or
    a dict with key 'objects' -> list[dict]. Each object ideally has 'name' and 'uuid'.
    Does a simple case-insensitive contains match on 'name' if query provided.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "objects" in data:
        objs = data["objects"]
    elif isinstance(data, list):
        objs = data
    else:
        return {"ok": False, "message": "Unrecognized JSON structure"}

    if not query:
        return {"ok": True, "count": len(objs), "results_preview": objs[:max_results]}

    q = query.lower()
    hits = [o for o in objs if str(o.get("name", "")).lower().find(q) >= 0]
    return {"ok": True, "query": query, "count": len(hits), "results": hits[:max_results]}