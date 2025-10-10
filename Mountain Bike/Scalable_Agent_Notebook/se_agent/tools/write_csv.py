# se_agent/tools/write_csv.py
import pandas as pd
from se_agent.core.tool_patterns import ExportTool


class WriteCSVTool(ExportTool):
    """
    Write rows to a CSV file.
    Data can come directly from input_data['data'] (list of dicts),
    or be pulled from an existing 'table' artifact via name/id.
    """

    name = "write_csv"
    description = "Write a list of rows to a CSV file (source: input data or a 'table' artifact)."
    # ExportTool does not create new artifacts by design.

    def export(self, input_data, artifacts, package_name=None):
        filename = input_data.get("filename")
        if not filename:
            return {"error": "❌ No filename provided."}

        data = input_data.get("data")

        # If data not provided, try to resolve from an existing artifact
        if data is None and artifacts:
            name = input_data.get("name")
            art_id = input_data.get("id")
            pkg_name = package_name or getattr(artifacts, "active_package", None)
            art = None

            if name:
                art = artifacts.get_artifact(name=name, package_name=pkg_name)
            elif art_id:
                art = artifacts.get_artifact(id=art_id, package_name=pkg_name)

            if art and getattr(art, "type", None) == "table":
                data = art.content

        if data is None:
            return {"error": "❌ No data provided and no source artifact (name/id) resolved."}

        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)

        return {
            "filename": filename,
            "rows": len(df),
            "columns": [str(c) for c in df.columns],
        }
