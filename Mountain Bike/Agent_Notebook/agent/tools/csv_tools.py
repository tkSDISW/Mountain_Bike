
import pandas as pd
from langchain_core.tools import tool

@tool
def write_csv(filename: str, data: list[dict]) -> dict:
    """Save a list of dicts to a CSV file."""
    df = pd.DataFrame(data)
    df.to_csv(filename, index=False)
    return {"message": f"💾 Saved CSV to {filename}", "rows": len(df), "columns": list(df.columns)}

@tool
def read_csv(filename: str) -> dict:
    """Load a CSV; return metadata + preview."""
    df = pd.read_csv(filename)
    return {
        "message": f"📂 Loaded CSV from {filename}",
        "rows": len(df),
        "columns": list(df.columns),
        "data_preview": df.head().to_dict(orient="records"),
    }

@tool
def write_leveled_csv(filename: str, hierarchy: list[dict]) -> dict:
    """
    Write a hierarchical breakdown (with levels) into a CSV file.

    Input JSON schema:
    {
        "filename": "mtb_hierarchy.csv",
        "hierarchy": [
            {"level": 1, "name": "Mountain Bike", "description": "Top-level system"},
            {"level": 2, "name": "Frame", "description": "Supports components"},
            {"level": 2, "name": "Suspension", "description": "Absorbs shocks"},
            {"level": 3, "name": "Front Fork", "description": "Handles front wheel"},
            {"level": 3, "name": "Rear Shock", "description": "Handles rear wheel"}
        ]
    }

    Rules:
    - Columns are fixed: **Level, Name, Description**.
    - `level` must be an integer (1 = top-level).
    - `description` may be empty but should be included if known.
    - Example: Mountain Bike breakdown with Frame, Suspension, Drivetrain, Brakes, etc.
    """
    rows = [
        {
            "Level": int(n.get("level", 1)),
            "Name": n.get("name", ""),
            "Description": n.get("description", "")
        }
        for n in hierarchy
    ]
    df = pd.DataFrame(rows, columns=["Level", "Name", "Description"])
    df.to_csv(filename, index=False)
    return {
        "message": f"✅ Leveled CSV written to {filename}",
        "rows": len(df),
        "columns": list(df.columns)
    }


@tool
def read_leveled_csv(filename: str) -> dict:
    """Read a leveled CSV (Level, Name, Description) and return a simple hierarchy list."""
    df = pd.read_csv(filename)
    stack, hierarchy = {}, []
    for _, row in df.iterrows():
        level = int(row.get("Level", 1))
        name = str(row.get("Name", ""))
        desc = str(row.get("Description", ""))
        parent = stack.get(level - 1)
        node = {"level": level, "name": name, "description": desc, "parent": parent}
        hierarchy.append(node)
        stack[level] = name
    return {
        "message": f"📂 Loaded leveled CSV from {filename}",
        "rows": len(df),
        "columns": list(df.columns),
        "hierarchy_preview": hierarchy[:10],
        "hierarchy_full": hierarchy,
    }
