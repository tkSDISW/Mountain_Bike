from rag_manager.core.tool_registry import BaseTool
from rag_manager.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage

class AliasArtifactTool(BaseTool):
    name = "alias_artifact"
    description = """Assign a human-friendly alias to the most recent artifact of a given type in the active package.
    Parameters (JSON required):
    - type (string, required): The artifact type (e.g. "hierarchy", "csv", "conversation").
    - alias (string, required): The alias to assign.
    """

    def run(self, input_data, artifacts=None, package_name=None, **kwargs):
        alias = input_data.get("alias")
        art_type = input_data.get("type") or input_data.get("artifact_type")

        # ✅ Better error messages
        if not alias and not art_type:
            return {"message": "❌ Must provide both 'alias' and 'type'. Example: run:alias_artifact {\"type\":\"hierarchy\",\"alias\":\"bike BOM\"}"}
        if not alias:
            return {"message": "❌ Missing 'alias'. Example: run:alias_artifact {\"type\":\"hierarchy\",\"alias\":\"bike BOM\"}"}
        if not art_type:
            return {"message": "❌ Missing 'type'. Example: run:alias_artifact {\"type\":\"hierarchy\",\"alias\":\"bike BOM\"}"}

        # Resolve package
        pkg = None
        if isinstance(artifacts, ArtifactRegistry):
            pkg = artifacts.get_package(package_name)
        elif isinstance(artifacts, ArtifactPackage):
            pkg = artifacts

        if not pkg or not pkg.artifacts:
            return {"message": "❌ No artifacts found in the current package."}

        # Find latest artifact of requested type
        arts = [a for a in pkg.artifacts.values() if a.type == art_type]
        if not arts:
            return {"message": f"❌ No artifacts of type '{art_type}' found."}

        arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
        target = arts[0]

        # Assign alias
        target.metadata["alias"] = alias
        announce = (
            f"📌 Alias '{alias}' assigned to artifact id='{target.id[:8]}' "
            f"type='{target.type}' in package '{pkg.name}'"
        )
        target._announce = announce

        print(announce)

        return {
            "message": announce,
            "id": target.id,
            "type": target.type,
            "alias": target.alias,
            "metadata": target.metadata,
        }

