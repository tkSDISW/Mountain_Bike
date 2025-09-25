# agent/tools/yaml_tools.py
from typing import Optional
from pydantic import BaseModel
from langchain_core.tools import tool

try:
    from Open_AI_RAG_manager import ChatGPTAnalyzer
except Exception:
    from capella_tools import Open_AI_RAG_manager  # type: ignore
    ChatGPTAnalyzer = Open_AI_RAG_manager.ChatGPTAnalyzer  # type: ignore


class DirectYamlQueryArgs(BaseModel):
    prompt: str
    yaml_content: Optional[str] = None


@tool("direct_yaml_query", args_schema=DirectYamlQueryArgs)
def direct_yaml_query(args: DirectYamlQueryArgs) -> str:
    """
    Run a direct-mode RAG query against YAML content.

    - If `yaml_content` is provided, it will be used.
    - Otherwise, caller (e.g., MBSEAgent) should bind this tool to inject its own YAML context.
    """
    if not args.yaml_content:
        return ("⚠️ No YAML content provided. "
                "Pass 'yaml_content' or call the bound wrapper that uses the agent's YAML context.")

    rag = ChatGPTAnalyzer(args.yaml_content)

    full_prompt = (
        "The following is a YAML file describing a Capella/MBSE design:\n"
        "---\n"
        f"{args.yaml_content}\n"
        "---\n"
        f"{args.prompt}\n"
        "Please format the response in .html format where appropriate."
    )

    if hasattr(rag, "initial_prompt"):
        rag.initial_prompt(full_prompt)
    elif hasattr(rag, "submit_prompt"):
        rag.submit_prompt(full_prompt)
    else:
        return "⚠️ ChatGPTAnalyzer missing expected methods."

    return rag.get_response() if hasattr(rag, "get_response") else "⚠️ Missing get_response()"
