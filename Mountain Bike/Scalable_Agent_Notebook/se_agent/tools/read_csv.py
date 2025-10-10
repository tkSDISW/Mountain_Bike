# se_agent/tools/read_csv.py
import pandas as pd
from se_agent.core.tool_patterns import ImportTool


class ReadCSVTool(ImportTool):
    """Import a CSV file into a 'table' artifact (list of row dicts)."""

    name = "read_csv"
    description = "Import a CSV into an artifact of type 'table'."
    artifact_type = "table"  # <-- important

    def load(self, input_data):
        filename = input_data.get("filename")
        if not filename:
            # ImportTool.run() will still return this content/metadata if no registry is available
            return [], {"error": "❌ No filename provided."}

        df = pd.read_csv(filename)
        content = df.to_dict(orient="records")  # store full rows as list[dict]
        metadata = {
            "source_file": filename,
            "rows": len(df),
            "columns": [str(c) for c in df.columns],
        }
        return content, metadata
