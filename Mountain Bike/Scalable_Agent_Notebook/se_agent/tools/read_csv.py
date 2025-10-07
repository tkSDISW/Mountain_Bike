# rag_manager/tools/read_csv.py

import pandas as pd
from se_agent.core.tool_registry import BaseTool


class ReadCSVTool(BaseTool):
    name = "read_csv"
    description = "Load a CSV file and return metadata + preview."

    def run(self, input_data, artifacts=None, **kwargs):
        filename = input_data["filename"]
        df = pd.read_csv(filename)

        return {
            "message": f"📂 Loaded CSV from {filename}",
            "rows": len(df),
            "columns": list(df.columns),
            "data_preview": df.head().to_dict(orient="records"),
        }
