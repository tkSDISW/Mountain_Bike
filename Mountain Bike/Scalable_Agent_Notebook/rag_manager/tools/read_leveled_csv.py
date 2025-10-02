import csv
from rag_manager.core.tool_registry import BaseTool
from rag_manager.mcp.artifact_registry import Artifact

class ReadLeveledCSVTool(BaseTool):
    name = "read_leveled_csv"
    description = "Read a leveled CSV (Level, Name, Description) into a hierarchy list."

    def run(self, input_data, artifacts=None, package_name=None, **kwargs):
        filename = input_data.get("filename")
        if not filename:
            raise ValueError("Filename is required for read_leveled_csv")

        hierarchy = []
        with open(filename, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                hierarchy.append({
                    "level": int(row["Level"]),
                    "name": row["Name"],
                    "description": row["Description"],
                    "parent": None  # optional, depends on format
                })

        # 🔹 Save hierarchy into artifact memory
        if artifacts and package_name:
            pkg = artifacts.get_package(package_name)
            if pkg:
                pkg.add_artifact(
                    Artifact(
                        type_="hierarchy",
                        content=hierarchy,
                        metadata={"source_file": filename}
                    )
                )

        return {
            "message": f"📂 Loaded leveled CSV from {filename}",
            "rows": len(hierarchy),
            "columns": ["Level", "Name", "Description"],
            "hierarchy_preview": hierarchy[:10],
            "hierarchy_full": hierarchy,
        }
