# rag_manager/tools/write_csv.py

import pandas as pd
from se_agent.core.tool_registry import BaseTool


class WriteCSVTool(BaseTool):
    name = "write_csv"
    description = "Save a list of dicts to a CSV file."

    def run(self, input_data, artifacts=None, **kwargs):
        filename = input_data["filename"]
        data = input_data["data"]

        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)

        return {
            "message": f"💾 Saved CSV to {filename}",
            "rows": len(df),
            "columns": list(df.columns)
        }
