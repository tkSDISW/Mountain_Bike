# rag_manager/tools/describe_state.py
from collections import Counter
from se_agent.core.tool_registry import BaseTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage

class DescribeStateTool(BaseTool):
    name = "describe_state"
    description = "Summarize the current package memory (artifact counts by type)."

    def run(self, input_data, artifacts=None, package_name=None, **kwargs):
        # resolve package
        pkg = None
        if isinstance(artifacts, ArtifactRegistry):
            pkg = artifacts.get_package(package_name) if hasattr(artifacts, "get_package") else None
        elif isinstance(artifacts, ArtifactPackage):
            pkg = artifacts

        if not pkg or not pkg.artifacts:
            return {"message": "No artifacts in memory."}

        counts = Counter(getattr(a, "type", None) for a in pkg.artifacts.values())
        summary = [{"type": t, "count": c} for t, c in counts.most_common()]
        return {"message": f"🧠 Memory summary for '{pkg.name}'.", "summary": summary}
