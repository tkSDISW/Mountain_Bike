# agent/mcp.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict

@dataclass
class MCP:
    """Model Context Package (MCP): a versioned bundle of model artifacts."""
    id: str
    capella_project: Optional[str] = None         # path to .aird or project folder
    resources_dir: Optional[str] = None           # path to resources (images, libs)
    embeddings_index: Optional[str] = None        # path to embeddings json
    yaml_snapshot: Optional[str] = None           # path to last YAML snapshot on disk
    yaml_content: Optional[str] = None            # in-memory YAML (agent-loaded)
    notes: Optional[str] = None
    write_enabled: bool = True                    # guardrails for write tools
    tags: list[str] = field(default_factory=list)

class MCPStore:
    """In-memory registry of MCPs with a single 'current' selection."""
    def __init__(self):
        self._mcps: Dict[str, MCP] = {}
        self._current_id: Optional[str] = None

    def ensure_default(self) -> MCP:
        if "default" not in self._mcps:
            self._mcps["default"] = MCP(id="default")
        if self._current_id is None:
            self._current_id = "default"
        return self._mcps["default"]

    def create(self, mcp_id: str, **kwargs) -> MCP:
        if mcp_id in self._mcps:
            raise ValueError(f"MCP '{mcp_id}' already exists")
        mcp = MCP(id=mcp_id, **kwargs)
        self._mcps[mcp_id] = mcp
        self._current_id = mcp_id
        return mcp

    def use(self, mcp_id: str) -> MCP:
        if mcp_id not in self._mcps:
            raise KeyError(f"MCP '{mcp_id}' not found")
        self._current_id = mcp_id
        return self._mcps[mcp_id]

    def current(self) -> MCP:
        if self._current_id is None:
            return self.ensure_default()
        return self._mcps[self._current_id]

    def get(self, mcp_id: str) -> MCP:
        return self._mcps[mcp_id]

    def list(self) -> list[MCP]:
        return list(self._mcps.values())

    def upsert_yaml_content(self, text: str, mcp_id: Optional[str] = None):
        mcp = self.current() if mcp_id is None else self.get(mcp_id)
        mcp.yaml_content = text

    def set_artifacts(
        self,
        mcp_id: Optional[str] = None,
        *,
        capella_project: Optional[str] = None,
        resources_dir: Optional[str] = None,
        embeddings_index: Optional[str] = None,
        yaml_snapshot: Optional[str] = None,
    ):
        mcp = self.current() if mcp_id is None else self.get(mcp_id)
        if capella_project is not None:
            mcp.capella_project = capella_project
        if resources_dir is not None:
            mcp.resources_dir = resources_dir
        if embeddings_index is not None:
            mcp.embeddings_index = embeddings_index
        if yaml_snapshot is not None:
            mcp.yaml_snapshot = yaml_snapshot
