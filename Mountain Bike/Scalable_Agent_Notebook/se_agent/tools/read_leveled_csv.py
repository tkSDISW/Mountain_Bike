import csv
from se_agent.core.tool_patterns import ImportTool

class ReadLeveledCSVTool(ImportTool):
    """Import leveled CSV (Level, Name, Description) into hierarchy artifact."""

    name = "read_leveled_csv"
    description = "Read a leveled CSV (Level, Name, Description) into a hierarchy list."
    category = "import"
    artifact_type = "hierarchy"   

    def load(self, input_data):
        """Load and parse the leveled CSV into hierarchy structure."""
        filename = input_data.get("filename")
        if not filename:
            return [], {"error": "❌ No filename provided."}

        hierarchy = []
        with open(filename, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                hierarchy.append({
                    "level": int(row.get("Level", 0)),
                    "name": row.get("Name", "").strip(),
                    "description": row.get("Description", "").strip(),
                    "parent": None  # placeholder for future parent logic
                })

        metadata = {"source_file": filename, "rows": len(hierarchy)}
        return hierarchy, metadata

