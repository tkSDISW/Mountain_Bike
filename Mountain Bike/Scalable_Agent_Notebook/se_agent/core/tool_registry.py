# se_agent/core/tool_registry.py

import importlib
import pkgutil
import inspect
from typing import Dict, Callable, Any, Optional
from se_agent.mcp.artifact_registry import Artifact, ArtifactPackage, ArtifactRegistry


class BaseTool:
    """
    Abstract base class for tools.
    Every tool must implement a `run(input_data, artifacts, **kwargs)` method.
    """

    name: str = "base_tool"
    description: str = "Base tool interface"

    def run(self, input_data: Any, artifacts: Optional[Dict] = None, **kwargs) -> Any:
        raise NotImplementedError("Tools must implement the run method.")


    # ===========================================================
    # 🧩 Shared artifact creation helper for Import/Transform tools
    # ===========================================================
    def _make_artifact(self, pkg: ArtifactPackage, tool_name: str, content, metadata=None):
        """
        Create and register an artifact within the given package.
        Returns a dictionary containing user- and agent-facing messages.
        """
        if pkg is None:
            raise ValueError("Package is None — cannot create artifact. Did you set an active package?")

        # --- Create the artifact ---
        artifact = Artifact(tool_name, content, metadata or {})
        pkg.add_artifact(artifact)

        # --- Return standard dictionary used by tools ---
        return {
            "message": (
                f"📌 Artifact created: id='{artifact.id}' "
                f"type='{artifact.type}' in package '{pkg.name}'"
            ),
            "artifact_message": (
                f"📌 Artifact created: id='{artifact.id}' "
                f"type='{artifact.type}' in package '{pkg.name}'"
            ),
            "artifact_id": artifact.id,
            "artifact_type": artifact.type,
            "package_name": pkg.name,
        }

class ToolRegistry:
    """
    Dynamically discovers and manages tools under a given package.
    """

    def __init__(self, tools_package: str = "se_agent.tools"):
        self.tools_package = tools_package
        self.tools: Dict[str, BaseTool] = {}
        self.discover_tools()

    def discover_tools(self):
        """Auto-discover tools inside the tools package."""
        package = importlib.import_module(self.tools_package)

        for _, module_name, _ in pkgutil.iter_modules(package.__path__):
            module = importlib.import_module(f"{self.tools_package}.{module_name}")

            # Look for subclasses of BaseTool
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseTool) and obj is not BaseTool:
                    tool_instance = obj()
                    self.tools[tool_instance.name] = tool_instance

    def get_tool(self, name: str) -> BaseTool:
        """Retrieve a tool by name."""
        if name not in self.tools:
            raise ValueError(f"Tool '{name}' not found in registry.")
        return self.tools[name]
    
    def list_tools(self):
        return [
            {"name": tool.name, "description": tool.description}
            for tool in self.tools.values()
        ]

    def run_tool(self, name: str, input_data: Any, artifacts: Optional[Dict] = None, **kwargs) -> Any:
        """Run a tool by name."""
        tool = self.get_tool(name)
        return tool.run(input_data, artifacts, **kwargs)


# --- Example usage ---
if __name__ == "__main__":
    registry = ToolRegistry()
    print("Available tools:", registry.list_tools())

    # Example: run summarizer tool
    if "summarizer" in registry.tools:
        output = registry.run_tool("summarizer", "This is a long text that should be summarized.")
        print("Summarizer output:", output)
