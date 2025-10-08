from abc import ABC, abstractmethod
from se_agent.mcp.artifact_registry import Artifact
from se_agent.core.tool_registry import BaseTool

"""
tool_patterns.py
Unified base classes for import, export, display, transform, and generative tools.
All derive from BaseTool (from se_agent/core/tool_registry.py)
and integrate with ArtifactRegistry.
"""

from se_agent.core.tool_registry import BaseTool
from se_agent.mcp.artifact_registry import Artifact, ArtifactRegistry, ArtifactPackage


# ===============================================================
# 🟢 ImportTool
# ===============================================================

class ImportTool(BaseTool):
    """Base class for tools that import data and create artifacts."""
    category = "import"

    def __init__(self):
        super().__init__()

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        # Resolve package name
        pkg_name = package_name or getattr(artifacts, "active_package", None)
        if not artifacts or not pkg_name:
            # No registry context — still return content/metadata for debugging
            content, metadata = self.load(input_data)
            preview = content[:10] if isinstance(content, list) else None
            return {
                "message": f"📂 Loaded data via '{self.name}', but no artifact registry active.",
                "content": content,
                "metadata": metadata,
                "preview": preview,
            }

        # Import & register as artifact via REGISTRY method (expects type_ + content)
        content, metadata = self.load(input_data)
        artifact_type = getattr(self, "artifact_type", self.name)  # e.g., 'hierarchy'
        art = artifacts.add_artifact(pkg_name, type_=artifact_type, content=content, metadata=metadata or {})

        preview = content[:10] if isinstance(content, list) else None
        return {
            "message": f"📂 Loaded data via '{self.name}' into artifact.",
            "artifact_message": getattr(art, "_announce", None),
            "artifact_id": art.id,
            "artifact_type": art.type,
            "package_name": pkg_name,
            "preview": preview,
        }

    def load(self, input_data):
        """Subclasses must implement this to return (content, metadata)."""
        raise NotImplementedError("ImportTool.load() must be implemented by subclasses.")


# ===============================================================
# 🟣 TransformTool
# ===============================================================

class TransformTool(BaseTool):
    """Base class for tools that transform existing artifacts and create new ones."""
    category = "transform"

    def __init__(self):
        super().__init__()

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        pkg_name = package_name or getattr(artifacts, "active_package", None)
        new_content, metadata = self.transform(input_data, artifacts, package_name)

        if artifacts and pkg_name:
            artifact_type = getattr(self, "artifact_type", self.name)
            art = artifacts.add_artifact(pkg_name, type_=artifact_type, content=new_content, metadata=metadata or {})
            return {
                "message": f"🔄 Transformed artifact via '{self.name}'.",
                "artifact_message": getattr(art, "_announce", None),
                "artifact_id": art.id,
                "artifact_type": art.type,
                "package_name": pkg_name,
            }

        return {
            "message": f"🔄 Transformation completed via '{self.name}', no registry active.",
            "content": new_content,
            "metadata": metadata,
        }


    def transform(self, input_data, artifacts, package_name=None):
        raise NotImplementedError("TransformTool.transform() must be implemented by subclasses.")


# ===============================================================
# 🔵 GenerativeTool
# ===============================================================

class GenerativeTool(BaseTool):
    """Base class for AI-driven or procedural content generation tools."""
    category = "generative"

    def __init__(self):
        super().__init__()

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        content, metadata = self.generate(input_data, artifacts, package_name)
        create_artifact = getattr(self, "create_artifact", True)

        if create_artifact and artifacts:
            pkg_name = package_name or getattr(artifacts, "active_package", None)
            if pkg_name:
                artifact_type = getattr(self, "artifact_type", self.name)
                art = artifacts.add_artifact(pkg_name, type_=artifact_type, content=content, metadata=metadata or {})
                return {
                    "message": f"✨ Generated artifact via '{self.name}'.",
                    "artifact_message": getattr(art, "_announce", None),
                    "artifact_id": art.id,
                    "artifact_type": art.type,
                    "package_name": pkg_name,
                }

        # Display-only path (no artifact)
        return {
            "message": f"✨ Generated content via '{self.name}' (no artifact created).",
            "html": self._maybe_html(content),
            "displayed": True,
        }

    def _maybe_html(self, content):
        if isinstance(content, str):
            return f"<pre style='white-space: pre-wrap'>{content}</pre>"
        elif isinstance(content, (list, dict)):
            import json
            return f"<pre>{json.dumps(content, indent=2)}</pre>"
        return f"<pre>{str(content)}</pre>"
    def generate(self, input_data, artifacts, package_name=None):
        raise NotImplementedError("GenerativeTool.generate() must be implemented by subclasses.")

    def _maybe_html(self, content):
        if isinstance(content, str):
            return f"<pre style='white-space: pre-wrap'>{content}</pre>"
        elif isinstance(content, (list, dict)):
            import json
            return f"<pre>{json.dumps(content, indent=2)}</pre>"
        else:
            return f"<pre>{str(content)}</pre>"


# ===============================================================
# 🟡 ExportTool
# ===============================================================

class ExportTool(BaseTool):
    """Base class for exporting artifacts to external formats."""
    category = "export"

    def __init__(self):
        super().__init__()

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        result = self.export(input_data, artifacts, package_name)
        return {
            "message": f"💾 Export completed via '{self.name}'.",
            "export_result": result,
        } 

    def export(self, input_data, artifacts, package_name=None):
        raise NotImplementedError("ExportTool.export() must be implemented by subclasses.")


# ===============================================================
# 🖥️ DisplayTool
# ===============================================================

class DisplayTool(BaseTool):
    """Base class for tools that produce HTML/textual displays (no artifact)."""
    category = "display"

    def __init__(self):
        super().__init__()

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        html = self.render(input_data, artifacts, package_name)
        return {
            "message": f"🖥️ Display generated by '{self.name}'.",
            "html": html,
            "displayed": True,
        }

    def render(self, input_data, artifacts, package_name=None):
        raise NotImplementedError("DisplayTool.render() must be implemented by subclasses.")

