# se_agent/core/agent.py

import json
from pathlib import Path
from typing import Any, Optional
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage
from se_agent.core.tool_registry import ToolRegistry
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import os, time
import ipywidgets as widgets
from IPython.display import display, Markdown
from jupyter_ui_poll import ui_events
import traceback

class AgentCore:
    """
    Main agent core that orchestrates artifacts, tools, and pipelines.
    """

    def __init__(self):
        self.artifacts = ArtifactRegistry()
        self.tools = ToolRegistry()
        self.history = []  # in-memory execution history
        # 🔹 Inject tool registry into llm_chat if it exists
        if "llm_chat" in self.tools.tools:
            self.tools.tools["llm_chat"].tool_registry = self.tools
        # --- Package management ---
    def create_package(self, name: str) -> ArtifactPackage:
        return self.artifacts.create_package(name)

    def use_package(self, name: str):
        self.artifacts.use_package(name)

    def list_packages(self):
        """Return a list of available package names."""
        return list(self.artifacts.packages.keys())

    def add_artifact(self, package: str, type_: str, content: Any, metadata: Optional[dict] = None):
        return self.artifacts.add_artifact(package, type_, content, metadata)

    # --- Tool management ---
    def list_tools(self):
        """Return available tools and their descriptions."""
        return self.tools.list_tools()

    def active_package_name(self) -> Optional[str]:
        return self.artifacts.active_package
    
    def run(
        self,
        tool_name: str,
        package_name: Optional[str] = None,
        input_data: Any = None,
        capture_as_artifact: bool = False,  # default False to avoid duplicates
        **kwargs
    ) -> Any:
        """
        Run a tool by name, optionally scoped to a package.
        Tools should be responsible for persisting domain-specific artifacts.
        Optionally capture the tool's output as a separate 'run' artifact snapshot.
        """
    
        # 1) Resolve tool
        if tool_name not in self.tools.tools:
            raise ValueError(
                f"Tool '{tool_name}' not found. Available: {list(self.tools.tools.keys())}"
            )
        tool = self.tools.get_tool(tool_name)
    
        # 2) Resolve package (requested or active)
        pkg_name = package_name or self.active_package_name()
        package = None
        if pkg_name:
            if pkg_name not in self.artifacts.packages:
                raise ValueError(f"Package '{pkg_name}' not found.")
            package = self.artifacts.packages[pkg_name]
    
        # 3) Execute tool
        #    IMPORTANT: pass the registry + the resolved package name
        result = tool.run(
            input_data or {},
            artifacts=self.artifacts,   # <-- always the registry
            package_name=pkg_name,      # <-- explicit package scope
            **kwargs
        )
    
        # 4) Track in history
        record = {
            "tool": tool_name,
            "package": pkg_name,
            "input": input_data,
            "kwargs": kwargs,
            "output": result,
            "state": result if isinstance(result, dict) else {"value": result},
        }
        self.history.append(record)
    
        # 5) (Optional) capture a 'run snapshot' artifact (avoid domain duplication)
        #    Only do this if explicitly requested.
        if capture_as_artifact and package:
            if isinstance(result, (str, dict, list)):
                # Use 'run:<tool>' to keep these separate from domain artifacts
                self.artifacts.add_artifact(
                    pkg_name,
                    type_=f"run:{tool_name}",
                    content=result,
                    metadata={"from_tool": True, "snapshot": True}
                )

        if isinstance(result, dict):
            msg = self._latest_non_conversation_announce(pkg_name)
            if msg:
                # Keep structured field for UIs
                result.setdefault("artifact_message", msg)
                # Also append a newline so plain-text consumers see it immediately
                # If the tool already returned a 'message' string, append to it; else create one
                if "message" in result and isinstance(result["message"], str) and result["message"].strip():
                    result["message"] = result["message"].rstrip() + f"\n{msg}"
                else:
                    result["message"] = msg
        return result
    
    
        # --- Pipeline / History ---
        def get_history(self):
            return self.history
    
        def export_pipeline(self, out_path: Path, package_name: Optional[str] = None):
            """
            Export execution history as a JSON pipeline.
            If a package_name is provided, store pipeline inside the package.
            """
            out_path = Path(out_path)
            if out_path.suffix != ".json":
                out_path = out_path.with_suffix(".json")
    
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2)
    
            if package_name and package_name in self.artifacts.packages:
                self.artifacts.add_pipeline(package_name, self.history)
    
            return out_path

    def import_pipeline(self, pipeline_path: Path, package_name: Optional[str] = None):
        """
        Load a pipeline JSON file and replay it.
        If package_name is provided, attach to package.
        """
        pipeline_path = Path(pipeline_path)
        with open(pipeline_path, "r", encoding="utf-8") as f:
            pipeline = json.load(f)

        if package_name and package_name in self.artifacts.packages:
            self.artifacts.add_pipeline(package_name, pipeline)

        results = []
        for step in pipeline:
            result = self.run(
                step["tool"],
                package_name=step.get("package"),
                input_data=step.get("input"),
                **step.get("kwargs", {})
            )
            results.append(result)
        return results
    def run_pipeline_as_graph(self, steps, package: str, input_data: str):
        """
        Run a sequence of tools as a LangGraph pipeline.
        Each step is a tool name from ToolRegistry.
        """

        # Define state structure
        class AgentState(dict):
            package: str
            input: str
            output: dict
            history: list

        # Initialize LangGraph
        memory = MemorySaver()
        graph = StateGraph(AgentState)

        # --- Add nodes dynamically based on steps ---
        for tool_name in steps:
            def make_node(name):
                def node_fn(state: AgentState):
                    output = self.run(name, state["package"], state["input"])
                    state["output"] = output
                    state["history"].append((name, output))
                    return state
                return node_fn

            graph.add_node(tool_name, make_node(tool_name))

        # --- Link nodes in sequence ---
        graph.set_entry_point(steps[0])
        for i in range(len(steps) - 1):
            graph.add_edge(steps[i], steps[i+1])
        graph.add_edge(steps[-1], END)

        # Compile with memory
        compiled = graph.compile(checkpointer=memory)
        
        # Run with required config
        initial_state = {"package": package, "input": input_data, "output": None, "history": []}
        final_state = compiled.invoke(
            initial_state,
            config={"configurable": {"thread_id": f"{package}-pipeline"}}
)
        return final_state
    def record_decision(self, rule: str, choice: str, metadata: Optional[dict] = None):
        """
        Record a decision step in the history (for later pipeline branching).
        """
        record = {
            "tool": "decision",
            "rule": rule,
            "choice": choice,
            "metadata": metadata or {}
        }
        self.history.append(record)
        return record

    def _build_enriched_context(self):
        # 1) Tool awareness (names + one-liners)
        tools = self.tools.list_tools() if hasattr(self.tools, "list_tools") else []
        tool_lines = [f"- {t['name']}: {t['description']}" for t in tools]
    
        # 2) Artifact state (very compact)
        pkg = self.artifacts.get_active_package() if hasattr(self.artifacts, "get_active_package") else None
        state_lines = []
        if pkg and getattr(pkg, "artifacts", None):
            # counts by type, newest-first types first
            from collections import Counter
            counts = Counter(getattr(a, "type", "") for a in pkg.artifacts.values())
            state_lines.append(
                "[State] Artifacts in memory: " +
                ", ".join(f"{typ or 'unknown'}×{cnt}" for typ, cnt in counts.most_common())
            )
            # helpful nudges (only if relevant)
            if counts.get("hierarchy"):
                state_lines.append(
                    'Hint: use run:show_artifact {"type":"hierarchy","limit":20} '
                    'or run:write_leveled_csv {"filename":"out.csv","new_column":{"name":"type","value":"LogicalComponent"}}'
                )
    
        # 3) Interaction contract
        contract = [
            "You are a systems engineering assistant with access to tools.",
            "When a user makes a request:",
            "1. Briefly reason in natural language what needs to happen.",
            "2. Reply with a JSON object containing an 'actions' list describing the tools to call in order.",
            "   Example:",
            '   {"actions": [',
            '       {"tool": "read_leveled_csv", "input": {"filename": "drone.csv"}},',
            '       {"tool": "name_artifact", "input": {"type": "hierarchy", "name": "BOM"}}',
            '   ]}',
            "3. Do not include 'run: lines or extra commentary after the JSON.",
            '4. Do not propose "action" :[ "tool":"interactive_chat"] to limit recursive conversation.',
            'If no tool applies, respond naturally."'
    ]
    
        # 4) Compose
        parts = [
            "\n".join(contract),
            "You have access to the following tools:",
            "\n".join(tool_lines) or "- (no tools registered)",
        ]
        if state_lines:
            parts.append("\n".join(state_lines))
    
        return "\n\n".join(parts)
    
        
    def interactive_chat(self, package_name=None, context="You are a helpful assistant."):
        """
        Interactive chat with tool awareness + direct tool invocation.
        - User can type plain prompts (go to llm_chat).
        - Or type: run:<toolname> {json_input} (executes a tool directly).
        - Provide a preview of content returned from a tool. 
        """
        from IPython.display import display, Markdown, HTML
        import io, contextlib, json, os, time
        import ipywidgets as widgets
        from jupyter_ui_poll import ui_events
        ALLOWED_EXTENSIONS = [".txt", ".yaml", ".yml", ".csv", ".json", ".md"]
        self.chat_active = True
        self.yaml_content = None
        self.extra_context_msgs = []
        # Track last displayed outputs to prevent duplicates
        self._last_html = None
        self._last_message = None
            
        # 🔹 Include tool list in assistant context
        tools = self.list_tools()
        tool_list_str = "\n".join([f"- {t['name']}: {t['description']}" for t in tools])

    
        chat_history = widgets.Output()
        user_input = widgets.Textarea(
            placeholder="Type your prompt...",
            rows=6,
            layout=widgets.Layout(width="100%", border="2px solid #4A90E2", border_radius="8px",
                                  padding="12px", background_color="#F7F9FC", 
                                  box_shadow="3px 3px 10px rgba(0, 0, 0, 0.1)"),
        )
        send_button = widgets.Button(description="Execute", button_style="primary")
        exit_button = widgets.Button(description="Exit", button_style="danger")
    
        # File dropdown
        file_list = [
            f for f in os.listdir(os.getcwd())
            if os.path.isfile(f) and os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS
        ]
        file_dropdown = widgets.Dropdown(
            options=[""] + file_list, description="Load file:",
            layout=widgets.Layout(width="auto"),
        )
    
        def load_file(change):
            filename = change["new"]
            if not filename:
                return
            try:
                ext = os.path.splitext(filename)[1].lower()
                with open(filename, "r", encoding="utf-8") as f:
                    text = f.read()
                if ext in {".yaml", ".yml"}:
                    self.yaml_content = text
                    attach_msg = f"✅ YAML loaded: `{filename}`"
                else:
                    snippet = text if len(text) <= 4000 else text[:4000] + "\n# [truncated]"
                    self.extra_context_msgs.append((
                        "system",
                        f"Attached file `{filename}` content (truncated if large):\n{snippet}"
                    ))
                    attach_msg = f"✅ File attached: `{filename}`"
                with chat_history:
                    display(Markdown(attach_msg))
            except Exception as e:
                with chat_history:
                    display(Markdown(f"❌ Error reading `{filename}`: {e}"))
    
        file_dropdown.observe(load_file, names="value")
        enriched_context = self._build_enriched_context()  # call this each turn
        self.chat_history_msgs = [{"role": "system", "content": enriched_context}]
        
        def send_message(_):
            from IPython.display import HTML  # ensure in-scope for nested calls
            import io, contextlib, json, time, traceback
        
            def _show_tool_result(tool_result):
                """Central display logic with dedup + displayed flag + friendly errors."""
                if not isinstance(tool_result, dict):
                    display(Markdown("✅ Tool executed successfully."))
                    return
            
                # 1) Error path: render clearly and do not crash loop
                if tool_result.get("error"):
                    msg = tool_result.get("message") or f"❌ {tool_result['error']}"
                    if msg != getattr(self, "_last_message", None):
                        display(Markdown(f"<span style='color:#b00020'>{msg}</span>"))
                        self._last_message = msg
            
                    if getattr(self, "verbose", False):
                        tb = tool_result.get("traceback", "")
                        logs = tool_result.get("logs", "")
                        blocks = []
                        if tb:
                            blocks.append(f"```text\n{tb}\n```")
                        if logs:
                            blocks.append(f"```text\n{logs}\n```")
                        if blocks:
                            display(Markdown(
                                "<details><summary>Debug details</summary>\n\n" +
                                "\n\n".join(blocks) + "\n</details>"
                            ))
                    return
            
                html_out    = tool_result.get("html") or tool_result.get("ui")
                artifact_msg = tool_result.get("artifact_message")
                user_msg     = tool_result.get("message")
            
                # 2) Respect self-displayed tools
                if tool_result.get("displayed"):
                    # record last seen outputs to avoid future duplicates
                    if html_out:
                        self._last_html = html_out
                    if artifact_msg:
                        self._last_message = artifact_msg
                    elif user_msg:
                        self._last_message = user_msg
                    return
            
                # 3) Normal display path (with dedup)
                if html_out and html_out != getattr(self, "_last_html", None):
                    display(HTML(html_out))
                    self._last_html = html_out
            
                # Show artifact banner first (if new)
                if artifact_msg and artifact_msg != getattr(self, "_last_message", None):
                    display(Markdown(artifact_msg))
                    self._last_message = artifact_msg
            
                # Then show concise summary (if provided and different)
                if user_msg and user_msg != getattr(self, "_last_message", None):
                    display(Markdown(user_msg))
                    self._last_message = user_msg 
        
            def _execute_tool_safely(tool_name, payload):
                """Run a tool with robust error handling; never crash the chat loop."""
                buf = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                        return self.run(tool_name, package_name, input_data=payload)
                except Exception as e:
                    tb = traceback.format_exc(limit=6)
                    return {
                        "error": f"{type(e).__name__}: {e}",
                        "logs": buf.getvalue(),
                        "traceback": tb,
                        "message": f"❌ `{tool_name}` failed: {e}",
                        "displayed": False,
                    }
        
            prompt = user_input.value.strip()
            user_input.value = ""  # clear immediately
            if not prompt:
                return
        
            with chat_history:
                display(Markdown(f"**You:** {prompt}"))
        
                # --- Direct tool invocation (run:<tool> {...}) ---
                if prompt.startswith("run:"):
                    try:
                        cmd, payload_str = prompt[4:].split(" ", 1)
                        payload = json.loads(payload_str)
                    except Exception as e:
                        display(Markdown(f"❌ Invalid `run:` payload: {e}"))
                        return
        
                    display(Markdown(f"**Executing:** `{cmd}` {payload}"))
                    tool_result = _execute_tool_safely(cmd, payload)
                    _show_tool_result(tool_result)
                    return  # Prevent fallthrough to LLM branch
        
            # --- Normal LLM chat flow ---
            self.chat_history_msgs.append({"role": "user", "content": prompt})
            enriched_context = self._build_enriched_context()
        
            with chat_history:
                result = self.run("llm_chat", package_name, input_data={
                    "prompt": prompt,
                    "context": enriched_context,
                    "messages": self.chat_history_msgs
                })
        
                response = result.get("response", "")
                self.chat_history_msgs.append({"role": "assistant", "content": response})
                display(Markdown(f"**Assistant:** {response}"))
        
                # --- Parse sequential actions (planning mode) ---
                import re
                json_match = re.search(r'\{[\s\S]*\}', response)
                if not json_match:
                    return
        
                json_text = json_match.group(0)
                try:
                    parsed = json.loads(json_text)
                except Exception as e:
                    display(Markdown(f"⚠️ Could not parse actions JSON: {e}"))
                    return
        
                if isinstance(parsed, dict) and "actions" in parsed:
                    for step in parsed["actions"]:
                        tool_name = step.get("tool")
                        input_data = step.get("input", {})
                        if not tool_name:
                            continue
        
                        display(Markdown(f"**Executing:** `{tool_name}` {input_data}"))
                        tool_result = _execute_tool_safely(tool_name, input_data)
                        _show_tool_result(tool_result)
                        time.sleep(0.3)

        
        def exit_chat(_):
            self.chat_active = False
    
        send_button.on_click(send_message)
        exit_button.on_click(exit_chat)
    
        display(chat_history, user_input, widgets.HBox([send_button, exit_button]), file_dropdown)
        print("💬 Interactive chat started. Use `run:tool {json}` to call tools. Exit button to close.")
    
        with ui_events() as poll:
            while self.chat_active:
                poll(10)
                time.sleep(1)
    
        return {"message": "👋 Interactive chat closed"}


    def last_artifact_message(self, package_name: str | None = None) -> str | None:
        """
        Return the most recent artifact announcement for a package (or active package).
        """
        pkg_name = package_name or self.active_package_name()
        if not pkg_name:
            return None
        pkg = self.artifacts.get_package(pkg_name)
        if not pkg or not pkg.artifacts:
            return None

        # Pick the most recent by _created_at if present; fallback to insertion order
        try:
            artifacts_sorted = sorted(
                pkg.artifacts.values(),
                key=lambda a: getattr(a, "_created_at", ""),
                reverse=True,
            )
            latest = artifacts_sorted[0]
        except Exception:
            latest = list(pkg.artifacts.values())[-1]

        return getattr(latest, "_announce", None)
        
    def get_history(self):
        """Return the recorded tool run history."""
        return getattr(self, "history", [])

    def _latest_non_conversation_announce(self, package_name: str | None = None) -> str | None:
        pkg_name = package_name or self.active_package_name()
        if not pkg_name:
            return None
        pkg = self.artifacts.get_package(pkg_name)
        if not pkg or not pkg.artifacts:
            return None
    
        # Prefer non-conversation artifacts; fall back to any if none exist
        non_conv = [a for a in pkg.artifacts.values() if getattr(a, "type", "") != "conversation"]
        target = (sorted(non_conv, key=lambda a: getattr(a, "_created_at", ""), reverse=True)[0]
                  if non_conv else
                  sorted(pkg.artifacts.values(), key=lambda a: getattr(a, "_created_at", ""), reverse=True)[0])
    
        return getattr(target, "_announce", None)
# --- Example usage ---
if __name__ == "__main__":
    agent = AgentCore()

    # Setup
    agent.create_package("LandingGear")
    agent.add_artifact("LandingGear", "doc", "This is a long technical document about the landing gear system.")
    agent.use_package("LandingGear")

    # Run tools
    print("Available tools:", agent.list_tools())
    result = agent.run("summarizer", "LandingGear", input_data="Summarize the doc")
    print("Result:", result)

    # Export pipeline
    pipeline_file = agent.export_pipeline("landinggear_pipeline.json", package_name="LandingGear")
    print(f"Pipeline exported to {pipeline_file}")

