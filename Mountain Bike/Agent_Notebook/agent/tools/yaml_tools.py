# agent/tools/yaml_tools.py
from typing import Optional
from pydantic import BaseModel
from langchain_core.tools import tool


class DirectYamlQueryArgs(BaseModel):
    prompt: str
    yaml_content: str | None = None


import yaml  # ✅ REQUIRED
# (if you prefer not to parse, remove yaml usage)

import yaml

def direct_yaml_query_function(prompt: str, yaml_content: str) -> str:
    if not yaml_content:
        return "No YAML content is loaded."
    try:
        data = yaml.safe_load(yaml_content)
    except Exception as e:
        return f"YAML parse error: {e}"

    # VERY simple demo: you can expand this later
    text = yaml_content.lower()
    if "logical component" in prompt.lower():
        # naive filter
        # replace with a real traversal in time
        return "Listing logical components is not yet implemented in this stub."
    return "Handled YAML query, but no specific extractor matched."


# Optional: also expose a decorated tool (if you want to register it directly)
@tool("direct_yaml_query")
def direct_yaml_query_tool(prompt: str, yaml_content: str | None = None) -> str:
    """
    Run a direct-mode RAG query against YAML content.

    - If `yaml_content` is provided, it will be used.
    - Otherwise, caller (e.g., MBSEAgent) should bind this tool to inject its own YAML context.
    """
    if not yaml_content:
        return "⚠️ No YAML provided."
    return direct_yaml_query_fn(prompt=prompt, yaml_content=yaml_content)

