from se_agent.core.tool_registry import BaseTool
from se_agent.core.notebook_exporter import NotebookExporter

class NotebookExportTool(BaseTool):
    name = "notebook_export"
    description = "Export agent history as a Jupyter notebook for replay."

    def run(self, input_data, artifacts=None, **kwargs):
        agent = kwargs.get("agent")
        if not agent:
            raise ValueError("NotebookExportTool requires the agent instance in kwargs")

        filename = input_data.get("filename", "agent_replay.ipynb")
        exporter = NotebookExporter(agent)
        return exporter.export(filename=filename)
