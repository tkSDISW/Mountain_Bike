"""
agent package public API.

Exports:
- MBSEAgent: Dual-mode agent (RAG Manager + LangGraph tools)
- ToolRegistry, ToolInfo, build_list_tools_tool: registry utilities
- version / __version__: package/version string
- make_default_agent: convenience factory (optional)
"""

from __future__ import annotations
import os

# Lightweight metadata
version: str = "0.1.0"
__version__ = version

# Re-export the agent (primary entrypoint)
from .mbse_agent import MBSEAgent

# Re-export registry helpers so callers don’t hunt for paths
from .tool_registry import ToolRegistry, ToolInfo, build_list_tools_tool

def make_default_agent(debug: bool = False) -> "MBSEAgent":
    """
    Convenience factory that reads env vars:
      OPENAI_MODEL, OPENAI_BASE_URL, OPENAI_API_KEY
    """
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    api_key = os.getenv("OPENAI_API_KEY")
    return MBSEAgent(model=model, base_url=base_url, api_key=api_key, debug=debug)

__all__ = (
    "MBSEAgent",
    "ToolRegistry",
    "ToolInfo",
    "build_list_tools_tool",
    "version",
    "__version__",
    "make_default_agent",
)
