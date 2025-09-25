import os
import json
import time
import codecs
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import ipywidgets as widgets
from IPython.display import display, Markdown
from jupyter_ui_poll import ui_events

import yaml
from pydantic import BaseModel

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import StructuredTool



# --- Agent tool registry (unchanged from your pattern) ---
from agent.tool_registry import ToolRegistry, ToolInfo, build_list_tools_tool
from agent.tools import (
    write_csv,
    read_csv,
    write_leveled_csv,
    read_leveled_csv,
    # stubs / optional
    search_model_object,
    bpmn_to_capella,
    capella_to_bpmn,
    apply_description,
    add_logical_components,
    show_context_diagram,
)
# direct YAML (stateless core function + args)
from agent.tools.yaml_tools import (
    DirectYamlQueryArgs,
    direct_yaml_query,  # the stateless function we wrap with fallback
)

# Optional registry (nice-to-have). If you prefer pure list, you can remove this import and related use.
try:
    from agent.tool_registry import ToolRegistry, build_list_tools_tool
    _HAS_REGISTRY = True
except Exception:
    _HAS_REGISTRY = False

# ============================
# Standalone MBSE Agent
# (no inheritance from RAG Manager)
# ============================
class MBSEAgent:
    """
    Clean, standalone MBSE Agent built with LangGraph.
    - Reads model/LLM secrets from ~/.secrets/model_configs.json
    - Holds YAML/text context in-memory and injects a safe snippet into the agent prompt
    - Provides CSV tools + optional Capella/BPMN stubs
    - Interactive chat with file-loader wired to the agent's context
    """

    # -------------
    # Construction
    # -------------
    def __init__(
        self,
        yaml_content: str | None = None,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        config_name: str | None = None,
        debug: bool = False,
    ):
        self.debug = debug
        self.yaml_content: str | None = yaml_content
        

        # --- Secrets / model config resolution ---
        config: Dict[str, Any] = {}
        cfg_path = Path.home() / ".secrets" / "model_configs.json"
        if config_name and cfg_path.exists():
            with cfg_path.open() as f:
                all_cfg = json.load(f)
            config = all_cfg.get(config_name, {})
            if not config:
                raise ValueError(f"No config named '{config_name}' in {cfg_path}")
        elif not (model or base_url or api_key) and cfg_path.exists():
            with cfg_path.open() as f:
                all_cfg = json.load(f)
            default_name = all_cfg.get("_default")
            if default_name:
                config = all_cfg.get(default_name, {})

        # Merge priority: passed args > named config > env/secrets fallbacks
        self.api_key = api_key   or  config.get("api_key") 
        self.llm_url = base_url  or config.get("base_url") 
        self.llm_model =  model     or config.get("model") 

        print("✅ Agent initialized")
        print(f"🔐 API Key: {'Provided' if api_key or (config_name and 'api_key' in config) else 'Loaded from secrets'}")
        print(f"🌐 Base URL: {self.llm_url}")
        print(f"🤖 Model: {self.llm_model}")

        # --- LLM ---
        self.langchain_llm = ChatOpenAI(
            model=self.llm_model,
            api_key=self.api_key,
            base_url=self.llm_url,
            temperature=0,
        )
        from agent.tools.yaml_tools import direct_yaml_query, DirectYamlQueryArgs
        from .tool_registry import ToolInfo
        # --- Tool registry ---
        self.registry = ToolRegistry()
        # CSV tools
        self.registry.add(ToolInfo("write_csv", write_csv, "csv", ["io", "export"]))
        self.registry.add(ToolInfo("read_csv", read_csv, "csv", ["io", "import"]))
        self.registry.add(ToolInfo("write_leveled_csv", write_leveled_csv, "csv", ["io", "hierarchy", "export"]))
        self.registry.add(ToolInfo("read_leveled_csv", read_leveled_csv, "csv", ["io", "hierarchy", "import"]))

        # Optional/Stubbed tools
        self.registry.add(ToolInfo("search_model_object", search_model_object, "search", ["uuid", "lookup"]))
        self.registry.add(ToolInfo("bpmn_to_capella", bpmn_to_capella, "bpmn", ["convert"]))
        self.registry.add(ToolInfo("capella_to_bpmn", capella_to_bpmn, "bpmn", ["convert"]))
        if apply_description is not None:
            self.registry.add(ToolInfo("apply_description", apply_description, "capella", ["update", "description"]))
        if add_logical_components is not None:
            self.registry.add(ToolInfo("add_logical_components", add_logical_components, "capella", ["create", "structure"]))
        if show_context_diagram is not None:
            self.registry.add(ToolInfo("show_context_diagram", show_context_diagram, "capella", ["visualize", "context"]))
        self.registry.add(ToolInfo(
            name="direct_yaml_query",
            tool=direct_yaml_query,
            category="YAML",
            tags=["direct", "rag", "yaml"],
            description="Query YAML content directly using RAG Manager."
        ))
        # Built-in list_tools (zero-arg)
        self.list_tools = build_list_tools_tool(self.registry)

        # YAML context helper tools (agent-callable)
        self._register_yaml_context_tools()

        # Final toolset
        self.tools = self.registry.all() + [self.list_tools, self.set_yaml_context, self.load_yaml_file, self.direct_yaml_query]  


        # --- Static prompt (no dynamic injection) ---
        self.prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are an MBSE assistant. Prefer calling tools to read or transform data. "
             "If YAML detail is needed, call `direct_yaml_query`, `set_yaml_context`, or `load_yaml_file`. "
             "Ask for missing paths or inputs explicitly."
            ),
            ("placeholder", "{messages}"),
        ])

        # --- YAML helper tools (stateful bindings) ---
        self._register_yaml_context_tools()

        # --- Assemble tools ---
        tool_list = [
            # CSV tools
            write_csv, read_csv, write_leveled_csv, read_leveled_csv,
            # Search / BPMN / Capella tools (stubs or real)
            search_model_object, bpmn_to_capella, capella_to_bpmn,
            apply_description, add_logical_components, show_context_diagram,
            # YAML tools (stateful)
            self.set_yaml_context, self.load_yaml_file, self.direct_yaml_query,
        ]

    

        # --- Build agent ---
        self.agent = create_react_agent(
            self.langchain_llm,
            self.tools,
            prompt=self.prompt,
        )

    # -----------------------------
    # YAML helper tools (bound)
    # -----------------------------
    def _register_yaml_context_tools(self):
        # set_yaml_context
        class _SetYamlArgs(BaseModel):
            yaml_text: str

        def _set_yaml_ctx(yaml_text: str):
            self.yaml_content = yaml_text
            return {"ok": True, "message": "YAML context set.", "bytes": len(yaml_text)}

        self.set_yaml_context = StructuredTool.from_function(
            func=_set_yaml_ctx,
            name="set_yaml_context",
            description="Load YAML text into the agent's in-memory context (fallback for other tools).",
            args_schema=_SetYamlArgs,
        )

        # load_yaml_file
        class _LoadYamlArgs(BaseModel):
            filename: str

        def _load_yaml_file(filename: str):
            if not os.path.exists(filename):
                return {"ok": False, "message": f"File not found: {filename}"}
            with open(filename, "r", encoding="utf-8") as f:
                text = f.read()
            self.yaml_content = text
            return {"ok": True, "message": f"Loaded YAML from {filename}", "bytes": len(text)}

        self.load_yaml_file = StructuredTool.from_function(
            func=_load_yaml_file,
            name="load_yaml_file",
            description="Read a YAML file from disk and set it as the agent's YAML context.",
            args_schema=_LoadYamlArgs,
        )

        # direct_yaml_query (bound with fallback to self.yaml_content)
        def _direct_yaml_query_bound(prompt: str, yaml_content: Optional[str] = None) -> str:
            yml = yaml_content if yaml_content is not None else (self.yaml_content or "")
            if not yml:
                return ("⚠️ No YAML is available. "
                        "Provide 'yaml_content' in the tool call, or load it via "
                        "load_yaml_file/set_yaml_context first.")
            return direct_yaml_query_function(prompt=prompt, yaml_content=yml)

        class _DirectArgs(DirectYamlQueryArgs):
            """Inherit schema so agent tool-calling stays consistent."""
            pass

        self.direct_yaml_query = StructuredTool.from_function(
            func=_direct_yaml_query_bound,
            name="direct_yaml_query",
            description=(
                "Run a direct RAG-style query over YAML. "
                "Args: {'prompt': str, 'yaml_content'?: str}. "
                "If 'yaml_content' is omitted, uses the agent's current YAML context."
            ),
            args_schema=_DirectArgs,
        )

    # -----------------------------
    # Simple list_tools if registry not used
    # -----------------------------
    def _build_simple_list_tools(self) -> StructuredTool:
        class _NoArgs(BaseModel):
            pass

        def _list_tools_noargs():
            items = []
            for t in getattr(self, "tools", []):
                # skip itself later (after creation we reinsert; safe to include)
                name = getattr(t, "name", None) or getattr(t, "__name__", str(t))
                desc = getattr(t, "description", "") or ""
                items.append({"name": name, "description": desc})
            # Remove this tool from the listing by name
            items = [x for x in items if x["name"] != "list_tools"]
            return {"message": "Available tools:", "tools": items}

        return StructuredTool.from_function(
            func=_list_tools_noargs,
            name="list_tools",
            description="List all available MBSE tools and their descriptions.",
            args_schema=_NoArgs,
        )

    # -----------------------------
    # Agent run
    # -----------------------------
    def run_agent(self, task: str):
        """Invoke the agent with a user task."""
        if self.debug:
            print("🔎 Debug mode ON — streaming steps...")
            for step in self.agent.stream({"messages": [("human", task)]}):
                print("Step:", step)
        result = self.agent.invoke({"messages": [("human", task)]})
        if isinstance(result, dict) and "messages" in result and result["messages"]:
            return result["messages"][-1].content
        return str(result)

    # -----------------------------
    # Interactive chat (Agent-only)
    # -----------------------------
    def interactive_chat(self):
        """Agent-only interactive chat with a file loader that wires content to messages."""
        ALLOWED_EXTENSIONS = [".txt", ".yaml", ".yml", ".csv", ".json", ".md"]
        print("Starting interactive chat (Agent mode)...")
        self.chat_active = True

        chat_history = widgets.Output()
        user_input = widgets.Textarea(
            placeholder="Type your prompt...",
            rows=6,
            layout=widgets.Layout(
                width="100%",
                border="2px solid #4A90E2",
                border_radius="8px",
                padding="12px",
                background_color="#F7F9FC",
                box_shadow="3px 3px 10px rgba(0, 0, 0, 0.1)",
            ),
        )
        send_button = widgets.Button(description="Execute", button_style="primary")
        exit_button = widgets.Button(description="Exit", button_style="danger")

        # File dropdown (wired to prompt context)
        file_list = [
            f for f in os.listdir(os.getcwd())
            if os.path.isfile(f) and os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS
        ]
        file_dropdown = widgets.Dropdown(
            options=[""] + file_list,
            description="Load file:",
            layout=widgets.Layout(width="auto"),
        )

        def load_file(_):
            filename = file_dropdown.value
            if not filename:
                return
            try:
                ext = os.path.splitext(filename)[1].lower()
                with open(filename, "r", encoding="utf-8") as f:
                    text = f.read()
                # If YAML, set as YAML context; otherwise attach as extra system context
                if ext in {".yaml", ".yml"}:
                    self.yaml_content = text
                    attach_msg = f"✅ **YAML loaded as agent context:** `{filename}`"
                else:
                    # Keep a short system attachment; truncate to avoid token bloat
                    snippet = text if len(text) <= 4000 else text[:4000] + "# [truncated]"
                    self.extra_context_msgs.append((
                        "system",
                        f"Attached file `{filename}` content for reference (truncated if large):{snippet}",
                    ))
                    attach_msg = f"✅ **File attached to context:** `{filename}`"
                with chat_history:
                    display(Markdown(attach_msg))
            except Exception as e:
                with chat_history:
                    display(Markdown(f"❌ Error reading `{filename}`: {e}"))

        file_dropdown.observe(load_file, names="value")

        def send_message(_):
            prompt = user_input.value.strip()
            if not prompt:
                return
            with chat_history:
                display(Markdown(f"**You:** {prompt}"))
                display(Markdown("**Agent reasoning...**"))
                try:
                    result = self.agent.invoke({"messages": [("human", prompt)]})
                    if isinstance(result, dict) and "messages" in result and result["messages"]:
                        chatbot_response = result["messages"][-1].content
                    else:
                        chatbot_response = str(result)
                except Exception as e:
                    chatbot_response = f"⚠️ Agent error: {e}"
                display(Markdown(f"**Assistant:** {chatbot_response}"))
            user_input.value = ""

        def exit_chat(_):
            self.chat_active = False

        send_button.on_click(send_message)
        exit_button.on_click(exit_chat)

        display(chat_history, user_input, widgets.HBox([send_button, exit_button]), file_dropdown)
        print("Waiting for chat interactions...")
        from jupyter_ui_poll import ui_events
        with ui_events() as poll:
            while self.chat_active:
                poll(10)
                time.sleep(1)
        return {"message": "👋 Interactive chat closed"}

