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
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver

# --- Agent MCP ---
from agent.mcp import MCPStore
# --- Agent tool registry (unchanged from your pattern) ---
from agent.tool_registry import ToolRegistry, ToolInfo, build_list_tools_tool

# Optional registry (nice-to-have). If you prefer pure list, you can remove this import and related use.
try:
    from agent.tool_registry import ToolRegistry, build_list_tools_tool, ToolInfo
    _HAS_REGISTRY = True
except Exception:
    _HAS_REGISTRY = False

from agent.tools.csv_tools import (
    write_csv,
    read_csv,
    write_leveled_csv,
    read_leveled_csv,
)
from agent.tools.capella_tools import (
    apply_description,
    add_logical_components,
    show_context_diagram,
)
from agent.tools.bpmn_tools import (
    bpmn_to_capella,
    capella_to_bpmn,
)
from agent.tools.search_tools import (
    search_model_object,
)
# direct YAML (stateless core function + args)
from agent.tools.yaml_tools import direct_yaml_query_function  # the stateless function we wrap with fallback



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
    # inside class MBSEAgent:
    class _MCPCreateArgs(BaseModel):
        id: str = Field(..., description="Unique identifier for the MCP, e.g., 'bike@main'")
        notes: Optional[str] = None
    
    class _MCPUseArgs(BaseModel):
        id: str = Field(..., description="MCP id to select as current")
    
    class _MCPSetArtifactsArgs(BaseModel):
        id: Optional[str] = Field(None, description="MCP id (defaults to current)")
        capella_project: Optional[str] = None
        resources_dir: Optional[str] = None
        embeddings_index: Optional[str] = None
        yaml_snapshot: Optional[str] = None
    
    class _MCPGetInfoArgs(BaseModel):
        id: Optional[str] = None    
  
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
        # inside MBSEAgent.__init__ (very top of the method)
        #self.extra_context_msgs: list[tuple[str, str]] = []
        self.extra_context_msgs = []
        self.yaml_content: Optional[str] = yaml_content
        self.debug = debug

        

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


        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are an MBSE assistant. Prefer calling tools to read or transform data.\n"
             "IMPORTANT:\n"
             "• When you use a tool, ALWAYS pass arguments as valid JSON matching the tool's args schema.\n"
             "• If the user gives informal text (e.g., Read file name \"drone.csv\"), convert it to JSON\n"
             "  (e.g., {{\"filename\":\"drone.csv\"}}) before calling the tool.\n"
             "• If YAML is loaded in memory, use `direct_yaml_query` rather than asking to reload it.\n"
             "\n"
             "Examples of valid tool JSON:\n"
             "• Read CSV  {{\"filename\":\"test_simple.csv\"}}\n"
             "• Write CSV {{\"filename\":\"test_simple.csv\",\"data\":[{{\"ReqID\":\"R1\",\"Text\":\"Brake\"}}]}}\n"
             "• Load YAML {{\"filename\":\"capella_model.yaml\"}}\n"
             "• direct_yaml_query {{\"prompt\":\"List all Logical Components\"}}\n"
            ),
            MessagesPlaceholder("messages"),
        ])


        # --- Conversation memory ---
        self.checkpointer = MemorySaver()
        # Use a stable thread id for a session; callers may overwrite if desired
        self.thread_id = f"mbse-{int(time.time())}"

        # --- MCP store ---
        self.mcp_store = MCPStore()
        self.mcp_store.ensure_default()  # auto-create 'default'

        # MCP state (Model Context Packages)
        self.mcp_store: Dict[str, Dict[str, Any]] = {}
        self.current_mcp_id: Optional[str] = None
        
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

        # Built-in list_tools (zero-arg)
        self.list_tools = build_list_tools_tool(self.registry)




        
        # Register MCP management tools
        self._register_mcp_tools()

        
        # YAML context helper tools (agent-callable)
        self._register_yaml_context_tools()

        # Final toolset
        self.tools = self.registry.all() + [
            self.list_tools, 
            self.set_yaml_context, 
            self.load_yaml_file, 
            self.direct_yaml_query,
            self.mcp_create,
            self.mcp_use,
            self.mcp_list,
            self.mcp_set_artifacts,
            self.mcp_get_info]  


        # --- Build agent ---
        self.agent = create_react_agent(
            self.langchain_llm,
            self.tools,
            prompt=self.prompt,
            checkpointer=self.checkpointer,
        )

    
    #-------------
    # Yaml tools
    #-------------
    def _register_yaml_context_tools(self):
        # --- set_yaml_context ---
        class _SetYamlArgs(BaseModel):
            yaml_text: str
    
        def _set_yaml_ctx(yaml_text: str):
            self.yaml_content = yaml_text
            return {"ok": True, "message": "YAML context set.", "bytes": len(yaml_text)}
    
        self.set_yaml_context = StructuredTool.from_function(
            func=_set_yaml_ctx,
            name="set_yaml_context",
            description=(
                "Load YAML text into the agent's in-memory context. "
                "Other YAML tools will use this as fallback if no yaml_content is provided."
            ),
            args_schema=_SetYamlArgs,
        )
    
        # --- load_yaml_file ---
        class _LoadYamlArgs(BaseModel):
            filename: str
    
        def _load_yaml_file(filename: str):
            if not os.path.exists(filename):
                yamls = [f for f in os.listdir(os.getcwd()) if f.lower().endswith((".yaml", ".yml"))]
                return {"ok": False, "message": f"File not found: {filename}", "cwd_yamls": yamls}
            with open(filename, "r", encoding="utf-8") as f:
                text = f.read()
            self.yaml_content = text
            # short status line for next turn (avoid bloat)
            self.extra_context_msgs.append((
                "system",
                f"[status] Loaded YAML from {filename} (~{len(text)} bytes)."
            ))
            return {"ok": True, "message": f"Loaded YAML from {filename}", "bytes": len(text)}
    
        self.load_yaml_file = StructuredTool.from_function(
            func=_load_yaml_file,
            name="load_yaml_file",
            description="Read a YAML file from disk and set it as the agent's YAML context.",
            args_schema=_LoadYamlArgs,
        )
    
        # --- direct_yaml_query (bound) ---
        class _DirectYamlArgs(BaseModel):
            prompt: str
            yaml_content: Optional[str] = None
    
        def _direct_yaml_query_bound(prompt: str, yaml_content: Optional[str] = None) -> str:
            # fallback to in-memory YAML if not provided
            yml = yaml_content if yaml_content is not None else (self.yaml_content or "")
            # IMPORTANT: call the function directly, don’t call a BaseTool
            return direct_yaml_query_function(prompt=prompt, yaml_content=yml)
    
        self.direct_yaml_query = StructuredTool.from_function(
            func=_direct_yaml_query_bound,
            name="direct_yaml_query",
            description=(
                "Run a direct RAG-style query over YAML. Args: {\"prompt\": str, \"yaml_content\"?: str}. "
                "If 'yaml_content' is omitted, uses the agent's current YAML context."
            ),
            args_schema=_DirectYamlArgs,
        )

    
    #-------------
    # MCP tools
    #-------------        

    def _mcp_create(self, id: str, notes: Optional[str] = None) -> dict:
        if id in self.mcp_store:
            return {"ok": False, "error": f"MCP '{id}' already exists."}
        self.mcp_store[id] = {
            "id": id,
            "notes": notes or "",
            # slots we may fill later
            "model_path": None,          # path to .aird / Capella project
            "resources": None,           # capellambse resources map if used
            "json_index_path": None,     # embeddings / index path
            "yaml": None,                # last YAML snapshot
            "artifacts": {},             # any derived outputs
        }
        self.current_mcp_id = id
        # reflect in chat context
        self.extra_context_msgs.append(("system", f"[status] MCP created and selected: {id}"))
        return {"ok": True, "message": f"Created MCP '{id}' and set as current."}
    
    def _mcp_use(self, id: str) -> dict:
        if id not in self.mcp_store:
            return {"ok": False, "error": f"MCP '{id}' not found."}
        self.current_mcp_id = id
        self.extra_context_msgs.append(("system", f"[status] MCP selected: {id}"))
        return {"ok": True, "message": f"Using MCP '{id}'."}
    
    def _mcp_list(self) -> dict:
        items = []
        for k, v in self.mcp_store.items():
            items.append({
                "id": k,
                "current": (k == self.current_mcp_id),
                "notes": v.get("notes") or "",
                "model_path": v.get("model_path"),
                "json_index_path": v.get("json_index_path"),
                "has_yaml": bool(v.get("yaml")),
                "artifacts": list((v.get("artifacts") or {}).keys()),
            })
        return {"ok": True, "mcps": items}
            

    
    def _mcp_set_artifacts(
        self,
        id: Optional[str] = None,
        capella_project: Optional[str] = None,
        resources_dir: Optional[str] = None,
        embeddings_index: Optional[str] = None,
        yaml_snapshot: Optional[str] = None,
    ):
        self.mcp_store.set_artifacts(
            id,
            capella_project=capella_project,
            resources_dir=resources_dir,
            embeddings_index=embeddings_index,
            yaml_snapshot=yaml_snapshot,
        )
        m = self.mcp_store.current() if id is None else self.mcp_store.get(id)
        return {"ok": True, "message": f"Updated artifacts for MCP '{m.id}'.", "mcp": m.__dict__}
    
    def _mcp_get_info(self, id: Optional[str] = None):
        m = self.mcp_store.current() if id is None else self.mcp_store.get(id)
        return {"ok": True, "mcp": m.__dict__}
    
    def _register_mcp_tools(self):
        self.mcp_create = StructuredTool.from_function(
            func=lambda id, notes=None: self._mcp_create(id=id, notes=notes),
            name="mcp_create",
            description="Create a new Model Context Package (MCP) and set it current.",
            args_schema= MBSEAgent._MCPCreateArgs,
        )
        self.mcp_use = StructuredTool.from_function(
            func=lambda id: self._mcp_use(id=id),
            name="mcp_use",
            description="Switch current MCP.",
            args_schema=  MBSEAgent._MCPUseArgs,
        )
        self.mcp_list = StructuredTool.from_function(
            func=lambda : self._mcp_list(),
            name="mcp_list",
            description="List all MCPs with current flag and key artifacts."
        )
        self.mcp_set_artifacts = StructuredTool.from_function(
            func=lambda **kw: self._mcp_set_artifacts(**kw),
            name="mcp_set_artifacts",
            description=("Set artifact paths on an MCP: capella_project, resources_dir, "
                         "embeddings_index, yaml_snapshot. Omit 'id' to update current."),
            args_schema=  MBSEAgent._MCPSetArtifactsArgs,
        )
        self.mcp_get_info = StructuredTool.from_function(
            func=lambda id=None: self._mcp_get_info(id=id),
            name="mcp_get_info",
            description="Show full details of an MCP (defaults to current).",
            args_schema=  MBSEAgent._MCPGetInfoArgs,
        )
    # -----------------------------
    # Low-level invoke/stream wrappers
    # -----------------------------
    def _invoke(self, messages):
        """Always invoke with the persistent thread_id."""
        # messages must be a list of (role, content) tuples or BaseMessage objects
        return self.agent.invoke(
            {"messages": messages},
            config={
                "configurable": {"thread_id": self.thread_id},
                # optional: keep your recursion cap if you set it in __init__
                # "recursion_limit": self.recursion_limit,
            },
        )
    
    def _stream(self, messages):
        """Always stream with the persistent thread_id."""
        return self.agent.stream(
            {"messages": messages},
            config={
                "configurable": {"thread_id": self.thread_id},
                # "recursion_limit": self.recursion_limit,
            },
        )
    
    
    # -----------------------------
    # Agent run
    # -----------------------------
    def run_agent(self, task: str) -> str:
        # Defensive init
        if not hasattr(self, "extra_context_msgs"):
            self.extra_context_msgs = []
    
        status_msgs: list[tuple[str, str]] = []
        if getattr(self, "yaml_content", None):
            status_msgs.append((
                "system",
                f"[status] YAML is loaded in memory (~{len(self.yaml_content)} bytes). "
                "Use `direct_yaml_query` for details."
            ))
    
        if self.extra_context_msgs:
            status_msgs.extend(self.extra_context_msgs)
            # keep only the last couple to avoid bloat
            self.extra_context_msgs = self.extra_context_msgs[-2:]
    
        msgs = status_msgs + [("human", task)]
    
        if getattr(self, "debug", False):
            print("🔎 Debug mode ON — streaming steps...")
            for step in self._stream(msgs):
                print("Step:", step)
    
        result = self._invoke(msgs)
        if isinstance(result, dict) and "messages" in result and result["messages"]:
            last = result["messages"][-1]
            return last.content if hasattr(last, "content") else str(last)
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
                if ext in {".yaml", ".yml"}:
                    self.yaml_content = text
                    attach_msg = f"✅ **YAML loaded as agent context:** `{filename}`"
                else:
                    if not hasattr(self, "extra_context_msgs"):
                        self.extra_context_msgs = []
                    snippet = text if len(text) <= 4000 else text[:4000] + "\n# [truncated]"
                    self.extra_context_msgs.append((
                        "system",
                        f"Attached file `{filename}` content for reference (truncated if large):\n{snippet}",
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
                    # Build status context (same as run_agent)
                    status_msgs: list[tuple[str, str]] = []
                    if getattr(self, "yaml_content", None):
                        status_msgs.append((
                            "system",
                            f"[status] YAML is loaded in memory (~{len(self.yaml_content)} bytes). "
                            "Use `direct_yaml_query` for details."
                        ))
                    if hasattr(self, "extra_context_msgs") and self.extra_context_msgs:
                        status_msgs.extend(self.extra_context_msgs[-2:])
    
                    msgs = status_msgs + [("human", prompt)]
    
                    # IMPORTANT: pass a list, do NOT double-wrap
                    result = self._invoke(msgs)
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

