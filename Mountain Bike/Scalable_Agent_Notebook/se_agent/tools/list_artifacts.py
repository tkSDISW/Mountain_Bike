# rag_manager/tools/list_artifacts.py
from se_agent.core.tool_registry import BaseTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage

class ListArtifactsTool(BaseTool):
    name = "list_artifacts"
    description = "List artifacts in the current package (id, type, created_at, metadata)."

    def run(self, input_data, artifacts=None, package_name=None, **kwargs):
        # resolve package name
        if not package_name and hasattr(artifacts, "get_active_package"):
            active = artifacts.get_active_package()
            package_name = active.name if active else None
        if not package_name:
            return {"message": "No active package; use or create a package first."}

        # support both Registry or Package (Registry preferred)
        if isinstance(artifacts, ArtifactRegistry):
            items = artifacts.list_artifacts(package_name)
        elif isinstance(artifacts, ArtifactPackage):
            # build minimal list if a package was passed directly
            items = [{
                "id": getattr(a, "id", None),
                "type": getattr(a, "type", None),
                "created_at": getattr(a, "_created_at", None),
                "metadata": getattr(a, "metadata", None),
            } for a in artifacts.artifacts.values()]
        else:
            items = []

        return {
            "message": f"📚 {len(items)} artifacts in '{package_name}'.",
            "artifacts": items[:200]  # safety cap
        }
