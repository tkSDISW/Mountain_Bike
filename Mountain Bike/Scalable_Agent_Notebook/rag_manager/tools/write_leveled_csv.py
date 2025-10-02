import csv
from rag_manager.core.tool_registry import BaseTool
from rag_manager.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage, Artifact  
class WriteLeveledCSVTool(BaseTool):
    name = "write_leveled_csv"
    description = "Write a hierarchical breakdown into a CSV (Level, Name, Description)."

    def run(self, input_data, artifacts=None, package_name=None, **kwargs):
        filename = input_data.get("filename", "output.csv")
        hierarchy = input_data.get("hierarchy")

        # 🔹 If no hierarchy passed, try to fetch from artifacts
        if not hierarchy and artifacts and package_name:
            pkg = artifacts.get_package(package_name)
            if pkg:
                for a in pkg.artifacts.values():
                    if a.type == "hierarchy":
                        hierarchy = a.content
                        break

        if not hierarchy:
            raise ValueError("No hierarchy found. Load with read_leveled_csv first.")

        # 🔹 Optional column addition
        if "new_column" in input_data:
            col_name = input_data["new_column"]["name"]
            col_value = input_data["new_column"]["value"]
            for row in hierarchy:
                row[col_name] = col_value

        # 🔹 Persist updated hierarchy back to artifacts
        if artifacts and package_name:
            pkg = artifacts.get_package(package_name)
            if pkg:
                pkg.add_artifact(
                    Artifact(
                        type_="hierarchy",
                        content=hierarchy,
                        metadata={"source_file": filename, "updated": True}
                    )
                )

        # 🔹 Write to CSV
        fieldnames = list(hierarchy[0].keys())
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(hierarchy)

        return {
            "message": f"📂 Wrote leveled CSV to {filename}",
            "rows": len(hierarchy),
            "columns": fieldnames,
        }
