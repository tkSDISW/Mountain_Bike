# rag_manager/tools/save_artifact.py
from se_agent.core.tool_registry import BaseTool
from se_agent.mcp.artifact_registry import ArtifactRegistry

class RememberArtifactTool(BaseTool):
    name = "create_artifact"
    description = "Create or modifies content back as a new artifact (optionally with name and type)."

    def run(self, input_data, artifacts: ArtifactRegistry, package_name=None, **kwargs):
        content = input_data.get("content")
        name = input_data.get("name")
        type_ = input_data.get("type", "note")

        if not content:
            return {"error": "❌ Must provide 'content' to save an artifact."}

        # Resolve package
        pkg = artifacts.get_active_package() if package_name is None else artifacts.get_package(package_name)
        if not pkg:
            return {"error": f"❌ No package found (package_name={package_name})"}

        # If name exists, overwrite that artifact’s content instead of always adding new
        existing = pkg.get_by_name(name) if name else None
        if existing:
            existing.content = content
            existing.type = type_
            existing.metadata.update({"name": name} if name else {})
            return {
                "message": f"📋 Updated artifact id='{existing.id}' type='{existing.type}' name='{name}'",
                "id": existing.id,
                "type": existing.type,
                "name": name,
                "artifact_message": getattr(existing, "_announce", f"📌 Updated artifact '{name}'"),
            }

        # Otherwise, create a new artifact
        artifact = artifacts.add_artifact(
            pkg.name,
            type_=type_,
            content=content,
            metadata={"name": name} if name else None
        )

        return {
            "message": f"📋 Remembered new artifact id='{artifact.id}' type='{artifact.type}' name='{name}'",
            "id": artifact.id,
            "type": artifact.type,
            "name": name,
            "artifact_message": artifact._announce,
        }
