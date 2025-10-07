# se_agent/tools/show_artifact.py
from se_agent.core.tool_registry import BaseTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage


class ShowArtifactTool(BaseTool):
    name = "show_artifact"
    description = "Display a stored artifact by id, alias, or type."

    def run(self, input_data, artifacts=None, package_name=None, **kwargs):
        if not input_data:
            return {"message": "❌ Must provide at least 'id', 'alias', or 'type'."}

        # Resolve package
        pkg = None
        if isinstance(artifacts, ArtifactRegistry):
            pkg = artifacts.get_package(package_name)
        elif isinstance(artifacts, ArtifactPackage):
            pkg = artifacts

        if not pkg:
            return {"message": f"❌ No package found for '{package_name}'."}

        # --- Look up by ID ---
        if "id" in input_data:
            art = pkg.artifacts.get(input_data["id"])
            if not art:
                return {"message": f"No artifact with id {input_data['id']}."}
            return {
                "id": art.id,
                "type": art.type,
                "alias": art.alias,
                "content": art.content,
                "metadata": art.metadata,
            }

        # --- Look up by alias ---
        if "alias" in input_data:
            alias = input_data["alias"]
            arts = [a for a in pkg.artifacts.values() if a.alias == alias]
            if not arts:
                return {"message": f"No artifact with alias '{alias}'."}
            # return most recent
            arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
            art = arts[0]
            return {
                "id": art.id,
                "type": art.type,
                "alias": art.alias,
                "content": art.content,
                "metadata": art.metadata,
            }

        # --- Look up latest by type ---
        if "type" in input_data:
            art_type = input_data["type"]
            arts = [a for a in pkg.artifacts.values() if a.type == art_type]
            if not arts:
                return {"message": f"No artifacts of type '{art_type}'."}
            arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
            art = arts[0]
            return {
                "id": art.id,
                "type": art.type,
                "alias": art.alias,
                "content": art.content,
                "metadata": art.metadata,
            }

        return {"message": "❌ Must specify 'id', 'alias', or 'type'."}
