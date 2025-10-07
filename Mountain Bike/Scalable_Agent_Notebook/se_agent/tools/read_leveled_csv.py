import csv
from se_agent.core.tool_registry import BaseTool

class ReadLeveledCSVTool(BaseTool):
    name = "read_leveled_csv"
    description = "Read a leveled CSV (Level, Name, Description) into a hierarchy list."

    def run(self, input_data, artifacts=None, package_name=None, **kwargs):
        filename = input_data.get("filename")
        if not filename:
            return {"message": "❌ No filename provided."}

        hierarchy = []
        with open(filename, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                hierarchy.append({
                    "level": int(row.get("Level", 0)),
                    "name": row.get("Name", ""),
                    "description": row.get("Description", ""),
                    "parent": None  # keep placeholder for parent if needed
                })

        # ✅ Save full hierarchy as artifact
        if artifacts:
            art = artifacts.add_artifact(
                package_name,
                type_="hierarchy",
                content=hierarchy,
                metadata={"source_file": filename}
            )

        # ✅ Only return summary + preview
        preview = hierarchy[:10]  # first 10 rows
        return {
            "message": f"📂 Loaded leveled CSV '{filename}' into hierarchy artifact.",
            #"rows": len(hierarchy),
            #"columns": ["Level", "Name", "Description"],
            #"preview": preview,
            "artifact_message": getattr(art, "_announce", None) if artifacts else None
        }

