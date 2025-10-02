# rag_manager/tools/show_artifact.py
from rag_manager.core.tool_registry import BaseTool
from rag_manager.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage

class ShowArtifactTool(BaseTool):
    name = "show_artifact"
    description = "Return an artifact by id, or the latest artifact of a given type."

    def run(self, input_data, artifacts=None, package_name=None, **kwargs):
        art_id = input_data.get("id")
        art_type = input_data.get("type")

        # resolve package
        pkg = None
        if isinstance(artifacts, ArtifactRegistry):
            pkg = artifacts.get_package(package_name) if hasattr(artifacts, "get_package") else None
        elif isinstance(artifacts, ArtifactPackage):
            pkg = artifacts

        if not pkg or not pkg.artifacts:
            return {"message": "No artifacts available in the current package."}

        # direct by id
        if art_id:
            art = pkg.artifacts.get(art_id)
            if not art:
                return {"message": f"No artifact found with id '{art_id}'."}
            return {
                "message": f"✅ Found artifact id='{art_id}' type='{getattr(art, 'type', None)}'.",
                "artifact": {
                    "id": getattr(art, "id", None),
                    "type": getattr(art, "type", None),
                    "created_at": getattr(art, "_created_at", None),
                    "metadata": getattr(art, "metadata", None),
                    "content": getattr(art, "content", None),
                }
            }

        # otherwise, latest by type
        if art_type:
            # newest by _created_at if present; else by insertion order
            arts = [a for a in pkg.artifacts.values() if getattr(a, "type", None) == art_type]
            if not arts:
                return {"message": f"No artifacts of type '{art_type}' were found."}
            arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
            a = arts[0]
            return {
                "message": f"✅ Latest artifact of type '{art_type}'.",
                "artifact": {
                    "id": getattr(a, "id", None),
                    "type": getattr(a, "type", None),
                    "created_at": getattr(a, "_created_at", None),
                    "metadata": getattr(a, "metadata", None),
                    "content": getattr(a, "content", None),
                }
            }

        return {"message": "Provide 'id' or 'type' to retrieve an artifact."}
