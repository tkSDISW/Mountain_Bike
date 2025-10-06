# rag_manager/tools/save_artifact.py
from rag_manager.core.tool_registry import BaseTool
from ..mcp.artifact_registry import ArtifactRegistry

class SaveArtifactTool(BaseTool):
    name = "save_artifact"
    description = "Save modified content back as a new artifact (optionally with alias and type)."

    def run(self, input_data, artifacts: ArtifactRegistry, package_name=None, **kwargs):
        content = input_data.get("content")
        alias = input_data.get("alias")
        type_ = input_data.get("type", "note")

        if not content:
            return {"error": "❌ Must provide 'content' to save an artifact."}

        # Resolve package
        pkg = artifacts.get_active_package() if package_name is None else artifacts.get_package(package_name)
        if not pkg:
            return {"error": f"❌ No package found (package_name={package_name})"}

        # If alias exists, overwrite that artifact’s content instead of always adding new
        existing = pkg.get_by_alias(alias) if alias else None
        if existing:
            existing.content = content
            existing.type = type_
            existing.metadata.update({"alias": alias} if alias else {})
            return {
                "message": f"💾 Updated artifact id='{existing.id}' type='{existing.type}' alias='{alias}'",
                "id": existing.id,
                "type": existing.type,
                "alias": alias,
                "artifact_message": getattr(existing, "_announce", f"📌 Updated artifact '{alias}'"),
            }

        # Otherwise, create a new artifact
        artifact = artifacts.add_artifact(
            pkg.name,
            type_=type_,
            content=content,
            metadata={"alias": alias} if alias else None
        )

        return {
            "message": f"💾 Saved new artifact id='{artifact.id}' type='{artifact.type}' alias='{alias}'",
            "id": artifact.id,
            "type": artifact.type,
            "alias": alias,
            "artifact_message": artifact._announce,
        }
