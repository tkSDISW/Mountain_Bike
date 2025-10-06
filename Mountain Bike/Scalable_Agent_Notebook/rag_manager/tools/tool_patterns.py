from abc import ABC, abstractmethod
from ..mcp.artifact_registry import Artifact

class BaseTool(ABC):
    """Abstract base class for all tools."""

    category = "base"

    def __init__(self, name, description, category=None):
        self.name = name
        self.description = description
        if category:   # allow explicit override
            self.category = category

    def _make_artifact(self, package, type_, content, metadata=None):
        """Helper to create and register an artifact in a package."""
        artifact = package.add_artifact(
            Artifact(type_=type_, content=content, metadata=metadata or {})
        )
        return {
            "id": artifact.id,
            "type": artifact.type,
            "alias": artifact.alias,
            "content": artifact.content,
            "metadata": artifact.metadata,
            "artifact_message": artifact._announce,
        }

    @abstractmethod
    def run(self, input_data, artifacts, package_name=None, **kwargs):
        """All tools must implement this entrypoint."""
        pass


# --- Category scaffolds ---
class ImportTool(BaseTool):
    category = "import"

    @abstractmethod
    def load(self, input_data):
        """Load content from external source (file, API, etc.)."""
        pass

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        pkg = artifacts.get_package(package_name) or artifacts.get_active_package()
        content, metadata = self.load(input_data)
        return self._make_artifact(pkg, self.name, content, metadata)


class ExportTool(BaseTool):
    category = "export"

    @abstractmethod
    def save(self, artifact, target, **kwargs):
        """Save artifact to external destination."""
        pass

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        pkg = artifacts.get_package(package_name) or artifacts.get_active_package()
        artifact_ref = input_data.get("artifact") or input_data.get("alias")
        artifact = pkg.get_by_alias(artifact_ref) or pkg.get_by_id(artifact_ref)
        result = self.save(artifact, input_data.get("filename"))
        return {"message": f"✅ Exported {artifact.type} to {input_data.get('filename')}", "result": result}


class TransformTool(BaseTool):
    category = "transform"

    @abstractmethod
    def transform(self, artifact, params):
        """Apply a transformation to an artifact."""
        pass

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        pkg = artifacts.get_package(package_name) or artifacts.get_active_package()
        artifact_ref = input_data.get("artifact") or input_data.get("alias")
        artifact = pkg.get_by_alias(artifact_ref) or pkg.get_by_id(artifact_ref)
        new_content = self.transform(artifact.content, input_data)
        return self._make_artifact(pkg, self.name, new_content, {"source": artifact.id})


class GenerativeTool(BaseTool):
    category = "generate"

    @abstractmethod
    def generate(self, prompt, context=None):
        """Generate a new artifact from a prompt (optionally with context)."""
        pass

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        pkg = artifacts.get_package(package_name) or artifacts.get_active_package()
        prompt = input_data.get("prompt", "")
        context = input_data.get("context", "")
        result = self.generate(prompt, context)
        return self._make_artifact(pkg, self.name, result, {"prompt": prompt})
