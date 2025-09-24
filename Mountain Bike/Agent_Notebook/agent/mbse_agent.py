import os
import json
import time
import pandas as pd
import ipywidgets as widgets
from IPython.core.display import Javascript
from jupyter_ui_poll import ui_events
from IPython.display import display, Markdown
from pathlib import Path
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from agent.tool_registry import ToolRegistry, ToolInfo, build_list_tools_tool

# Import your existing RAG Manager (Direct mode)
from capella_tools import Open_AI_RAG_manager




# -----------------------------
# MBSE Agent (Dual Mode)
# -----------------------------
class MBSEAgent(Open_AI_RAG_manager.ChatGPTAnalyzer):
    """
    MBSEAgent extends the RAG Manager with an Agent mode (LangGraph).
    It provides two pathways:
      • Direct (RAG Manager): uses inherited submit/get methods.
      • Agent (LangGraph): tool-using ReAct agent with @tool-decorated skills.
    """

    def __init__(self, yaml_content=None, model=None, base_url=None, api_key=None, config_name=None, debug=False):
        # Initialize Direct (RAG) via superclass
        super().__init__(yaml_content=yaml_content, model=model, base_url=base_url, api_key=api_key, config_name=config_name)
        self.debug = debug

        config = {}
        if config_name:
            config_path = Path.home() / ".secrets" / "model_configs.json"
            if config_path.exists():
                with config_path.open() as f:
                    configs = json.load(f)
                config = configs.get(config_name, {})
                if not config:
                    raise ValueError(f"No config named '{config_name}' found in model_configs.json.")
        elif model is None and base_url is None and api_key is None:
            # Use default config if no overrides and no name given
            config_path = Path.home() / ".secrets" / "model_configs.json"
            if config_path.exists():
                with config_path.open() as f:
                    configs = json.load(f)
                default_name = configs.get("_default")
                if default_name:
                    config = configs.get(default_name, {})
        
        # Choose from: passed args > config file > .secrets fallback
        self.api_key = api_key or config.get("api_key") or Open_AI_RAG_manager.get_api_key()
        self.llm_url = base_url or config.get("base_url") or Open_AI_RAG_manager.get_base_url()
        self.llm_model = model or config.get("model") or Open_AI_RAG_manager.get_model()
        print(f"✅ Agent initialized")
        print(f"🔐 API Key: {'Provided' if api_key else 'Loaded from secrets'}")
        print(f"🌐 Base URL: {self.llm_url or 'Default'}")
        print(f"🤖 Model: {self.llm_model}")


        # ✅ If no explicit model provided, fall back to what RAG Manager already set
        active_model = model or self.llm_model
        # --- LLM setup ---
        self.langchain_llm = ChatOpenAI(
            model=active_model,
            api_key=self.api_key,
            base_url=self.llm_url,
            temperature=0,
        )

        # ---- Prompt (LangGraph expects `messages`) ----
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are an MBSE assistant. Use tools when helpful."
                "If the user asks to list tools, call the list_tools tool."
                "Prefer structured tool calls with correct parameter names."
            )),
            MessagesPlaceholder("messages"),
        ])
        from agent.tools import (
            write_csv, read_csv, write_leveled_csv, read_leveled_csv,
            search_model_object, bpmn_to_capella, capella_to_bpmn,
            apply_description, add_logical_components, show_context_diagram,
        )
        from agent.tool_registry import ToolRegistry, ToolInfo, build_list_tools_tool
        
        
        # --- Tool registry + list_tools (zero-arg) ---
        self.registry = ToolRegistry()
        
        # Register always-available tools
        for name, tool, cat, tags in [
            ("write_csv", write_csv, "csv", ["io","export"]),
            ("read_csv", read_csv, "csv", ["io","import"]),
            ("write_leveled_csv", write_leveled_csv, "csv", ["io","hierarchy","export"]),
            ("read_leveled_csv", read_leveled_csv, "csv", ["io","hierarchy","import"]),
            ("search_model_object", search_model_object, "search", ["uuid","lookup"]),
            ("bpmn_to_capella", bpmn_to_capella, "bpmn", ["convert"]),
            ("capella_to_bpmn", capella_to_bpmn, "bpmn", ["convert"]),
        ]:
            self.registry.add(ToolInfo(name, tool, cat, tags))
        
        # Optional Capella tools (may be None if capellambse not installed)
        for name, tool, cat, tags in [
            ("apply_description", apply_description, "capella", ["update","description"]),
            ("add_logical_components", add_logical_components, "capella", ["create","structure"]),
            ("show_context_diagram", show_context_diagram, "capella", ["visualize","context"]),
        ]:
            if tool is not None:
                self.registry.add(ToolInfo(name, tool, cat, tags))
        
        # Build zero-arg list_tools bound to the registry (no `self` in schema)
        self.list_tools = build_list_tools_tool(self.registry)
        
        # Final toolset for the agent
        self.tools = self.registry.all() + [self.list_tools]

        # Convenience bindings for direct calls from notebooks
        self.write_csv = write_csv
        self.read_csv = read_csv
        self.write_leveled_csv = write_leveled_csv
        self.read_leveled_csv = read_leveled_csv
        self.search_model_object = search_model_object
        self.bpmn_to_capella = bpmn_to_capella
        self.capella_to_bpmn = capella_to_bpmn
        if apply_description is not None:
            self.apply_description = apply_description
        if add_logical_components is not None:
            self.add_logical_components = add_logical_components
        if show_context_diagram is not None:
            self.show_context_diagram = show_context_diagram
        self.list_tools_tool = self.list_tools  # zero-arg StructuredTool        


        # ---- Build Agent ----
        self.agent = create_react_agent(self.langchain_llm, self.tools, prompt=self.prompt)



    # ------------------------------------------------------------------
    # Core run method (Agent mode)
    # ------------------------------------------------------------------
    def run_agent(self, task: str):
        if self.debug:
            print("🔎 Debug mode ON — streaming steps...")
            for step in self.agent.stream({"messages": [("human", task)]}):
                print("Step:", step)
        result = self.agent.invoke({"messages": [("human", task)]})
        if isinstance(result, dict) and "messages" in result and result["messages"]:
            last = result["messages"][-1]
            return last.content if hasattr(last, "content") else str(last)
        return str(result)

    # ------------------------------------------------------------------
    # Interactive Chat (Dual Mode)
    # ------------------------------------------------------------------
    def interactive_chat(self):
        self.ALLOWED_EXTENSIONS = [".txt", ".yaml", ".yml", ".csv", ".json"]   
        print("Starting interactive chat...")
        self.chat_active = True

    
        chat_history = widgets.Output()
    
        # Chat mode selector
        mode_toggle = widgets.ToggleButtons(
            options=["Direct (RAG Manager)", "Agent"],
            description="Mode:",
            button_style="info"
        )
    
        user_input = widgets.Textarea(
            placeholder="Type your prompt...",
            rows=3,
            layout=widgets.Layout(
                width="100%", 
                border="2px solid #4A90E2", 
                border_radius="8px",
                padding="12px", 
                background_color="#F7F9FC", 
                box_shadow="3px 3px 10px rgba(0, 0, 0, 0.1)"
            )
        )
    
        send_button = widgets.Button(description="Execute", button_style="primary")
        exit_button = widgets.Button(description="Exit", button_style="danger")
    
        # File dropdown for appending context
        file_list = [
            f for f in os.listdir(os.getcwd())
            if os.path.isfile(f) and os.path.splitext(f)[1].lower() in self.ALLOWED_EXTENSIONS
        ]
        file_dropdown = widgets.Dropdown(
            options=[""] + file_list,
            description="Load file:",
            layout=widgets.Layout(width="auto")
        )
    
        def load_file(_):
            filename = file_dropdown.value
            if not filename:
                return
            try:
                self.add_text_file_to_messages(filename)
                with chat_history:
                    display(Markdown(f"✅ **File `{filename}` was added for analysis.**"))
            except Exception as e:
                with chat_history:
                    display(Markdown(f"❌ Error reading `{filename}`: {str(e)}"))
    
        file_dropdown.observe(load_file, names="value")
    
        def send_message(_):
            prompt = user_input.value.strip()
            if not prompt:
                return
            with chat_history:
                display(Markdown(f"**You:** {prompt}"))
                if mode_toggle.value == "Direct (RAG Manager)":
                    self.submit_prompt(prompt, is_initial=False)
                    display(Markdown("**RAG Manager generating...**"))
                    chatbot_response = self.get_response()
                else:
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
    
        display(chat_history, mode_toggle, user_input, widgets.HBox([send_button, exit_button]), file_dropdown)
    
        print("Waiting for chat interactions...")
        with ui_events() as poll:
            while self.chat_active:
                poll(10)
                time.sleep(1)
    
        return {"message": "👋 Interactive chat closed"}