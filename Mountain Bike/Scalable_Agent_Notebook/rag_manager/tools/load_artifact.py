from rag_manager.core.tool_registry import BaseTool
from ..mcp.artifact_registry import ArtifactRegistry

class LoadArtifactTool(BaseTool):
    name = "load_artifact"
    description = "Load an artifact (by alias or id) into the conversation memory for editing or translation."

    def run(self, input_data, artifacts: ArtifactRegistry, package_name=None, **kwargs):
        alias = input_data.get("alias")
        artifact_id = input_data.get("id")

        if not (alias or artifact_id):
            return {"error": "❌ Must provide 'alias' or 'id' to load an artifact."}

        # Resolve package
        pkg = artifacts.get_active_package() if package_name is None else artifacts.get_package(package_name)
        if not pkg:
            return {"error": f"❌ No package found (package_name={package_name})"}

        # Resolve artifact
        artifact = None
        if alias:
            artifact = pkg.get_by_alias(alias)
        elif artifact_id:
            artifact = pkg.get_by_id(artifact_id)

        if not artifact:
            return {"error": f"❌ Artifact not found (alias={alias}, id={artifact_id})"}

        # --- Put into conversation memory ---
        # Attach to the agent’s memory buffer (simulating context injection)
        if not hasattr(artifacts, "_loaded_context"):
            artifacts._loaded_context = {}
        artifacts._loaded_context["active_artifact"] = {
            "id": artifact.id,
            "alias": artifact.alias,
            "type": artifact.type,
            "content": artifact.content,
        }

        # --- Prepare return message ---
        content_str = str(artifact.content)
        warning = ""
        if len(content_str) > 2000:
            warning = f"⚠️ Warning: Artifact '{alias or artifact_id}' content is large (~{len(content_str)} chars). Only a snippet shown."
        
        snippet = content_str[:2000]
        return {
            "message": f"📥 Loaded artifact '{alias or artifact_id}' (type={artifact.type}) into conversational memory.",
            "alias": alias,
            "id": artifact.id,
            "type": artifact.type,
            "content_snippet": snippet,
            "warning": warning,
        }
