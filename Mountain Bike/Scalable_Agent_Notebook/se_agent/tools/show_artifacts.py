# se_agent/tools/show_artifact.py
from se_agent.tools.tool_patterns import DisplayTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage


class ShowArtifactTool(DisplayTool):
    """Display a stored artifact by id, alias, or type in an HTML summary."""

    name = "show_artifact"
    description = "Display a stored artifact by id, alias, or type."
    category = "display"

    def render(self, input_data, artifacts=None, package_name=None):
        if not input_data:
            return "<p style='color:red'>❌ Must provide at least 'id', 'alias', or 'type'.</p>"

        # Resolve package
        pkg = None
        if isinstance(artifacts, ArtifactRegistry):
            pkg = artifacts.get_package(package_name)
        elif isinstance(artifacts, ArtifactPackage):
            pkg = artifacts

        if not pkg:
            return f"<p style='color:red'>❌ No package found for '{package_name}'.</p>"

        # --- Lookup by ID ---
        if "id" in input_data:
            art = pkg.artifacts.get(input_data["id"])
            if not art:
                return f"<p>No artifact with id <b>{input_data['id']}</b>.</p>"
            return self._artifact_to_html(art)

        # --- Lookup by alias ---
        if "alias" in input_data:
            alias = input_data["alias"]
            arts = [a for a in pkg.artifacts.values() if a.alias == alias]
            if not arts:
                return f"<p>No artifact with alias <b>{alias}</b>.</p>"
            arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
            return self._artifact_to_html(arts[0])

        # --- Lookup by type ---
        if "type" in input_data:
            art_type = input_data["type"]
            arts = [a for a in pkg.artifacts.values() if a.type == art_type]
            if not arts:
                return f"<p>No artifacts of type <b>{art_type}</b>.</p>"
            arts.sort(key=lambda a: getattr(a, "_created_at", ""), reverse=True)
            return self._artifact_to_html(arts[0])

        return "<p style='color:red'>❌ Must specify 'id', 'alias', or 'type'.</p>"

    # --------------------------------------------------------------
    # 🧩 Helper to format an artifact nicely in HTML
    # --------------------------------------------------------------
    def _artifact_to_html(self, art):
        """Render an artifact in human-readable HTML."""
        html = [
            f"<h3>Artifact: {art.alias or art.id}</h3>",
            f"<p><b>Type:</b> {art.type}</p>",
            "<table border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse;'>"
            "<tr><th>Key</th><th>Value</th></tr>"
        ]
        meta = art.metadata or {}
        for k, v in meta.items():
            html.append(f"<tr><td>{k}</td><td>{v}</td></tr>")
        html.append("</table>")

        # Include brief preview of content if small enough
        if isinstance(art.content, list) and len(art.content) <= 20:
            html.append("<h4>Content Preview</h4><ul>")
            for i in art.content:
                if isinstance(i, dict):
                    html.append(
                        f"<li>{i.get('name','(no name)')} - {i.get('description','')}</li>"
                    )
                else:
                    html.append(f"<li>{i}</li>")
            html.append("</ul>")
        elif isinstance(art.content, (dict, list)):
            html.append("<p>📄 (Content too large to preview)</p>")
        else:
            html.append(f"<pre>{str(art.content)[:800]}</pre>")

        return "\n".join(html)
