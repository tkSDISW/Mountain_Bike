
# se_agent/tools/list_artifacts.py
from se_agent.core.tool_patterns import DisplayTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage  # adjust import if needed

class ListArtifactsTool(DisplayTool):
    name = "list_artifacts"
    description = (
        "Show all artifacts in the active (or specified) package. "
        "Optional: type_filter to only show a specific artifact type."
    )

    def render(self, input_data, artifacts, package_name=None):
        # Resolve package
        package_name = (
            input_data.get("package_name")
            or package_name
            or getattr(artifacts, "active_package", None)
        )
        if not package_name:
            md = "⚠️ No active package; set one or pass package_name."
            return {"message": md, "ui": md, "html": md}

        # Pull items from the registry/package
        type_filter = input_data.get("type_filter")
        if isinstance(artifacts, ArtifactRegistry):
            items = artifacts.list_artifacts(package_name, type_filter=type_filter)
        elif isinstance(artifacts, ArtifactPackage):
            items = []
            for a in artifacts.artifacts.values():
                if type_filter and getattr(a, "type", None) != type_filter:
                    continue
                items.append({
                    "id": getattr(a, "id", None),
                    "type": getattr(a, "type", None),
                    "name": getattr(a, "name", None),
                    "created_at": getattr(a, "_created_at", None),
                    "metadata": getattr(a, "metadata", None),
                })
            items.sort(key=lambda x: (x.get("created_at") or ""), reverse=True)
        else:
            items = []

        # Nothing to show
        if not items:
            md = f"📭 No artifacts found in '{package_name}'."
            return {"message": md, "ui": md, "html": md}

        # Build Markdown + HTML
        header = f"📚 {len(items)} artifact(s) in '{package_name}'."
        rows = [
            f"- **{(a.get('name') or '(unnamed)')}** "
            f"(`{a.get('type','?')}`, id=`{str(a.get('id',''))[:8]}`)"
            for a in items
        ]
        md = header + "\n\n" + "\n".join(rows)
        html = (
            "<div style='font-family:system-ui;line-height:1.35'>"
            + md.replace("\n", "<br/>")
            + "</div>"
        )

        # Let the agent render (do NOT set displayed=True here)
        return {
            "message": header,
            "ui": md,
            "html": html
        }
