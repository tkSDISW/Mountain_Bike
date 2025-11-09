# se_agent/core/agent.py

import json
from pathlib import Path
from typing import Any, Optional

from se_agent.mcp.artifact_registry import ArtifactPackage, artifact_registry
from se_agent.core.tool_registry import tool_registry
import importlib, pkgutil, se_agent.tools as tools_pkg
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import os, time
import ipywidgets as widgets
from IPython.display import display, Markdown
from jupyter_ui_poll import ui_events
import traceback
from se_agent.core.workspace_resolver import resolve_workspace_names

class AgentCore:
    """
    Main agent core that orchestrates artifacts, tools, and pipelines.
    """
    def _tool_action_hint(self, name: str, meta: dict) -> str:
        io = meta.get("io_schema", {}) or {}
        ins = io.get("inputs", {}) or {}
        outs = io.get("outputs", {}) or {}
    
        # pull a nicer "when to use" if the class defines USAGE
        cls = meta.get("class")
        usage = (getattr(cls, "USAGE", "") or meta.get("description", "")).strip()
        cat = (meta.get("category") or "general").strip()
        when = (f"[{cat}] {usage}" if usage else f"[{cat}]").strip()
    
        # required / optional inputs
        req_lines, opt_lines = [], []
        for k, spec in ins.items():
            if not isinstance(spec, dict):
                continue
            line = f'"{k}": {spec.get("type","string")}'
            desc = spec.get("description")
            if desc:
                line += f"  # {desc}"
            (req_lines if spec.get("required") else opt_lines).append(line)
    
        # JSON action template: required first, then at most two optional
        required_keys = [k for k, s in ins.items() if isinstance(s, dict) and s.get("required")]
        optional_keys = [k for k, s in ins.items() if isinstance(s, dict) and not s.get("required")][:2]
        templ_parts = [f'"{k}": <{k}>' for k in required_keys + optional_keys]
        action_template = f'{{"tool":"{name}","input":{{{", ".join(templ_parts)}}}}}'
    
        # outputs summary (type + remember flag)
        out_lines = []
        for ok, spec in outs.items():
            if not isinstance(spec, dict):
                continue
            t = spec.get("type", "")
            r = " remember" if spec.get("remember") else ""
            out_lines.append(f'- "{ok}": {t}{r}')
    
        lines = []
        if when:
            lines.append(f"When to use: {when}")
        if req_lines:
            lines.append("Requires:")
            lines += [f"  - {x}" for x in req_lines]
        if opt_lines:
            lines.append("Optional:")
            lines += [f"  - {x}" for x in opt_lines]
        lines.append("Action template:")
        lines.append(f"  {action_template}")
        if out_lines:
            lines.append("Produces:")
            lines += [f"  {x}" for x in out_lines]
    
        return "\n".join(lines)

    def _format_tool_result_for_chat(self, result: dict) -> str:
        import json
        if not isinstance(result, dict):
            return str(result)
    
        ui = result.get("ui")
        if isinstance(ui, str) and ui.strip():
            return ui
    
        html = result.get("html")
        if isinstance(html, str) and html.strip():
            return html
    
        if "content" in result:
            try:
                if isinstance(result["content"], (dict, list)):
                    txt = json.dumps(result["content"], indent=2, ensure_ascii=False)
                else:
                    txt = str(result["content"])
            except Exception:
                txt = str(result["content"])
            if len(txt) > 4000:
                txt = txt[:4000] + "…"
            return txt
    
        # ✅ No UI/HTML/CONTENT → no preview; let _show_tool_result print message once
        return ""

    def _scan_tools_contracts(self):
        """Quick scan at startup: warn if tools declare remember=True."""
        for tool_name, meta in self.tools.tools.items():
            io_schema = meta.get("io_schema") or getattr(meta.get("obj", None), "IO_SCHEMA", None)
            if not isinstance(io_schema, dict):
                continue
            outputs = io_schema.get("outputs", {}) or {}
            remember_keys = [k for k, v in outputs.items() if isinstance(v, dict) and v.get("remember")]
            if remember_keys:
                print(f"[contract] Tool '{tool_name}' has remember-outputs {remember_keys}. "
                      "Ensure it returns result['artifact_ids'][name] on success.")


    def __init__(self,memory_saver: MemorySaver | None = None):
        self.artifacts = artifact_registry
        self.tools = tool_registry
        self.history = []  # in-memory execution history
         # 🔹 Autoload all tool modules so @register_tool executes
        self._autoload_tools()
        self._last_announced: dict[str, str] = {}  # package_name -> artifact_id
        self.memory_saver = memory_saver or MemorySaver()
        self._scan_tools_contracts()  # ← add this one-liner
        self.last_tool = None
        self._bottom_windows = None
        
    # --- Package management ---

    
    def create_package(self, name: str) -> ArtifactPackage:
        return self.artifacts.create_package(name)

    def use_package(self, name: str):
        self.artifacts.use_package(name)

    def list_packages(self):
        """Return a list of available package names."""
        return list(self.artifacts.packages.keys())
    # add inside AgentCore:
    def _autoload_tools(self):
        """Import every module in se_agent.tools so tool decorators run."""
        for m in pkgutil.iter_modules(tools_pkg.__path__):
            importlib.import_module(f"{tools_pkg.__name__}.{m.name}")
    
    def add_artifact(self, package: str, type_: str, content: Any, metadata: Optional[dict] = None):
        return self.artifacts.add_artifact(package, type_, content, metadata)

    # --- Tool management ---
    def list_tools(self):
        """Return available tools and their descriptions as a list of dicts."""
        out = []
        for name, info in self.tools.tools.items():
            out.append({
                "name": name,
                "description": info.get("description", ""),
                "category": info.get("category", "general"),
                "consumes": [v.get("type") for v in info.get("io_schema", {}).get("inputs", {}).values()],
                "produces": [v.get("type") for v in info.get("io_schema", {}).get("outputs", {}).values()],
            })
        return out

    def active_package_name(self) -> Optional[str]:
        return self.artifacts.active_package


    def _execute_tool_safely(self, tool_name: str, payload: dict, package_name: Optional[str] = None):
        """Run a tool with robust error handling; never crash the chat loop."""
        import io, contextlib, traceback
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                return self.run(tool_name, package_name or self.active_package_name(), input_data=payload)
        except Exception as e:
            tb = traceback.format_exc(limit=6)
            return {
                "error": f"{type(e).__name__}: {e}",
                "logs": buf.getvalue(),
                "traceback": tb,
                "message": f"❌ `{tool_name}` failed: {e}",
                "displayed": False,
            }


    
    def run(
        self,
        tool_name: str,
        package_name: Optional[str] = None,
        input_data: Any = None,
        capture_as_artifact: bool = False,
        **kwargs
    ) -> Any:
        """
        Run a tool by name, optionally scoped to a package.
        Tools should be responsible for persisting domain-specific artifacts.
        Optionally capture the tool's output as a separate 'run' artifact snapshot.
        """
    
        # 1) Resolve tool (from normalized registry metadata)
        meta = self.tools.get(tool_name)
        if not meta:
            raise ValueError(
                f"Tool '{tool_name}' not found. Available: {list(self.tools.tools.keys())}"
            )
        tool_cls = meta.get("class")
        if tool_cls is None:
            raise ValueError(f"Tool '{tool_name}' is missing its class in the registry.")
        tool = tool_cls()  # ✅ instantiate
        #Save the last tool in the agenet so can be used  
        self.last_tool = tool
    
        # 2) Resolve package (requested or active)
        pkg_name = package_name or self.active_package_name()
        package = None
        if pkg_name:
            if pkg_name not in self.artifacts.packages:
                raise ValueError(f"Package '{pkg_name}' not found.")
            package = self.artifacts.packages[pkg_name]
    
        # 3) Execute tool
        # resolve any workspace names in the incoming payload
        resolved_input = resolve_workspace_names(input_data or {}, self.artifacts, pkg_name)
        result = tool.run(
            input_data or {},
            artifacts=self.artifacts,   # always the registry
            package_name=pkg_name,      # explicit package scope
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
    
        # 5) (Optional) capture a 'run snapshot' artifact
        if capture_as_artifact and package:
            if isinstance(result, (str, dict, list)):
                self.artifacts.add_artifact(
                    pkg_name,
                    type_=f"run:{tool_name}",
                    content=result,
                    metadata={"from_tool": True, "snapshot": True}
                )
    
        # 6) (Optional) enforce tool-declared memory policy (remember=True on outputs)
        try:
            if hasattr(self, "_enforce_memory_policy") and isinstance(result, dict):
                self._enforce_memory_policy(tool_name, result, pkg_name)
        except Exception:
            # memory should never break the run; ignore failures
            pass
    
        # 7) Append latest artifact announce to the tool message (your existing UX)
        if isinstance(result, dict):
            ann = self._latest_non_conversation_announce(pkg_name)
            if ann:
                result.setdefault("artifact_message", ann)
    
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
        tools_map = self.tools.list_tools()  # name -> meta dict
        tool_lines = []
        for name in sorted(tools_map.keys()):
            meta = tools_map[name]
            hint = self._tool_action_hint(name, meta)
            tool_lines.append(f"- {name}\n{hint}")
    


    
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
        
          # How to think (silently) before acting
          "Before proposing actions, silently check the ToolRegistry IO_SCHEMA for each tool you intend to use.",
        
          # What to output when actions are possible
          "When actions can be taken, reply ONLY with a JSON object containing an 'actions' list. Do NOT include any other text.",
          "Each action must be of the form: {\"tool\": <tool_name>, \"input\": {<fields>}}",
        
          # Hard rules for inputs (teach, don't fix)
          "INPUT RULES:",
          " - Include ONLY input fields that are defined in the tool's IO_SCHEMA.inputs.",
          " - NEVER invent fields (e.g., 'version' unless IO_SCHEMA includes it).",
          " - Omit keys with empty values (\"\", null) entirely.",
          " - Satisfy all required inputs. If a required input is missing, first add an action to create or fetch it.",
          " - Use artifact identifiers that exist: prefer 'name' OR 'id' as specified by the tool; do not include both unless required.",
          " - Match value types suggested by IO_SCHEMA (string, integer, boolean, dict, list, path).",
          " - If a tool expects a single-asset artifact (e.g., 'capella_model'), reference it by name or id as the tool specifies.",
          " - Do not include package in inputs unless the tool explicitly defines a 'package' input; the runtime provides package scope.",
        
          # Planning & chaining
          "PLANNING:",
          " - Plan from available artifacts to desired outputs. If prerequisites are missing, create them first.",
          " - Use the tool’s declared outputs (IO_SCHEMA.outputs) to chain to the next action.",
          " - Prefer minimal, correct sequences over long plans. Keep actions ≤ 3 unless the task truly requires more.",
          " - If no tool applies or required data cannot be created without user input, reply naturally and ask only for the missing essentials.",
        
          # Output format and cleanliness
          "FORMAT:",
          " - Return ONLY the JSON with 'actions'. No markdown fences, no json prefix, no commentary, no 'run:' lines.",
          " - Do not propose {\"tool\":\"interactive_chat\"} recursively.",
          " - Do not echo previous conversations or artifacts in the JSON.",
        
          # Examples (schema-compliant)
          "EXAMPLES:",
          ' {"actions":[{"tool":"read_leveled_csv","input":{"filename":"drone.csv"}}]}',
          ' {"actions":[{"tool":"name_artifact","input":{"type":"hierarchy","name":"BOM"}}]}',
          ' {"actions":[{"tool":"show_artifact","input":{"name":"SEA_Capella_Model"}}]}',
          ' {"actions":[{"tool":"query_capella_model","input":{"capella_model_name":"BikeModel","query":"brake lever","top_n":25}}]}',
        
          # Final reminder
          "If no tool applies, respond naturally."
        ]

    
        # 4) Compose
        parts = [
            "\n".join(contract),
            "You have access to the following tools:",
            "\n".join(tool_lines) or "- (no tools registered)",
            "Be helpful in educating and listing the tools you have access to.",
            "If user asks about prompt for using a tool assume they desire it in a natural language format.",
        ]
        if state_lines:
            parts.append("\n".join(state_lines))
    
        return "\n\n".join(parts)

    #    
    def _show_tool_result(self, tool, result):
        from IPython.display import display, Markdown, HTML
        import json
    
        # Respect tools that already rendered
        if isinstance(result, dict) and result.get("displayed"):
            return
    
        # --- helpers ---
        def _render_tables(r):
            arts, mems = r.get("artifacts"), r.get("memory")
            if not arts and not mems:
                return False
    
            def _mk(rows, cols):
                if not rows:
                    return "| *(none)* |\n|---|\n"
                head = "| " + " | ".join(cols) + " |\n"
                sep  = "| " + " | ".join(["---"] * len(cols)) + " |\n"
                body = "".join("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |\n" for row in rows)
                return head + sep + body
    
            did = False
            if arts:
                display(Markdown("**Workspace Artifacts**"))
                display(Markdown(_mk(arts, ["name","type","artifact_id","updated_at"])))
                did = True
            if mems:
                display(Markdown("**Workspace Memory**"))
                display(Markdown(_mk(mems, ["name","type","updated_at"])))
                did = True
            return did
    
        def _maybe_injection(r):
            if isinstance(r, dict) and r.get("inject_once"):
                display(Markdown("> _One-shot workspace injection appended to the next LLM turn._"))
    
        # -------- single-pass, prioritized rendering (UI first) --------
        rendered = False
        if isinstance(result, dict):
            ui   = result.get("ui")
            html = result.get("html")
            msg  = result.get("message")
    
            # 1) Prefer UI markdown (keeps your headings + tables)
            if isinstance(ui, str) and ui.strip():
                display(Markdown(ui))
                rendered = True
            # 2) Else HTML
            elif isinstance(html, str) and html.strip():
                display(HTML(html))
                rendered = True
            # 3) Else smart tables (only if no ui/html)
            elif _render_tables(result):
                rendered = True
            # 4) Else short message
            elif isinstance(msg, str) and msg.strip():
                display(Markdown(msg))
                rendered = True
            # 5) Else basic fallbacks
            else:
                if "text" in result:
                    display(Markdown(f"```\n{result['text']}\n```")); rendered = True
                elif "csv_text" in result:
                    display(Markdown(f"```\n{result['csv_text']}\n```")); rendered = True
        else:
            display(Markdown(f"```\n{result}\n```"))
            rendered = True
    
        _maybe_injection(result)
    
        # Debug payload (only if something was rendered and there are extras)
        if isinstance(result, dict):
            known = {
                "html","ui","message","text","csv_text",
                "artifacts","memory","displayed","inject_once",
                "artifact_id","artifact_name","artifact_type","type","name"
            }
            extras = {k:v for k,v in result.items() if k not in known}
            if rendered and extras:
                try:
                    display(Markdown("**Debug payload**"))
                    display(Markdown(f"```json\n{json.dumps(extras, ensure_ascii=False, indent=2)}\n```"))
                except Exception:
                    pass


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
        self._last_preview = None
            
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
                # Register the file as a file_reference artifact
                res = self._execute_tool_safely("import_file_artifact", {
                    "file_path": filename,
                    # Optional: let users type an alias somewhere, else filename stem is used by the tool
                    # "name": "Bike_BOM_v2"
                })
                # Show the tool's own UI/message
                with chat_history:
                    self._show_tool_result("import_file_artifact", res)
        
                # Refresh side-by-side panes (Workspace | Artifacts | Tools)
                try:
                    if getattr(self, "_bottom_windows", None):
                        self._bottom_windows.refresh()
                except Exception:
                    pass

            except Exception as e:
                with chat_history:
                    display(Markdown(f"❌ Error attaching `{filename}`: {e}"))

    
        file_dropdown.observe(load_file, names="value")
        enriched_context = self._build_enriched_context()  # call this each turn
        self.chat_history_msgs = [{"role": "system", "content": enriched_context}]
        
        def send_message(_):


        
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
                    tool_result = self._execute_tool_safely(cmd, payload)
                    self._show_tool_result(self.last_tool, tool_result)
                    # 🔹 If the tool returned a one-shot injection, append to messages for the next LLM turn
                    if isinstance(tool_result, dict) and tool_result.get("inject_once"):
                        self.chat_history_msgs.append({"role": "system", "content": tool_result["inject_once"]})

                    return  # Prevent fallthrough to LLM branch
        
            # --- Normal LLM chat flow ---
            self.chat_history_msgs.append({"role": "user", "content": prompt})
            enriched_context = self._build_enriched_context()
        
            with chat_history:
            # 🔹 Optional governance: keep total prompt under control
                try:
                    from se_agent.core.prompt_guard import enforce_prompt_budget
                    guard = enforce_prompt_budget(self.chat_history_msgs)
                    if not guard["ok"]:
                        display(Markdown(guard["message"]))
                        return
                except Exception:
                    pass

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
     
                        #display(Markdown(f"**Executing:** `{tool_name}` {input_data}"))
                        tool_result = self._execute_tool_safely(tool_name, input_data)
                        self._show_tool_result(self.last_tool, tool_result)
                        # refresh bottom panes
                        try:
                            if getattr(self, "_bottom_windows", None):
                                self._bottom_windows.refresh()
                        except Exception:
                            pass
                        #  honor one-shot injection returned by tools
                        if isinstance(tool_result, dict) and tool_result.get("inject_once"):
                            self.chat_history_msgs.append({"role": "system", "content": tool_result["inject_once"]})

                        time.sleep(0.3)

        
        def exit_chat(_):
            self.chat_active = False
    
        send_button.on_click(send_message)
        exit_button.on_click(exit_chat)
    
        display(chat_history, user_input, widgets.HBox([send_button, exit_button]), file_dropdown)
        print("💬 Interactive chat started. Use `run:tool {json}` to call tools. Exit button to close.")
         # --- Persistent bottom panes (Workspace / Artifacts / Tools) ---
        try:
            from se_agent.ui.panels_widgets import BottomWindows
            self._bottom_windows = BottomWindows(
                artifacts=self.artifacts,
                tool_registry_like=self.tools,     # works with your tool_registry structure
                package_name=package_name
            )
            display(self._bottom_windows.view())
        except Exception as e:
            # Don't block the chat if panes fail
            with chat_history:
                display(Markdown(f"⚠️ Bottom panes not available: {e}"))
   
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

    def _latest_non_conversation_announce(self, pkg_name: str | None) -> str:
        if not pkg_name:
            return ""
        pkg = self.artifacts.get_package(pkg_name)
        if not pkg or not getattr(pkg, "artifacts", None):
            return ""
    
        # find most-recent non-conversation artifact
        arts = [a for a in pkg.artifacts.values() if getattr(a, "type", None) != "conversation"]
        if not arts:
            return ""
    
        latest = max(arts, key=lambda a: getattr(a, "_created_at", ""))
        last_seen = self._last_announced.get(pkg_name)
    
        # Nothing new since last time
        if last_seen == latest.id:
            return ""
    
        # Prefer the tool-supplied announce, or synthesize a minimal one
        announce = getattr(latest, "_announce", None)
        if not announce:
            short_id = latest.id[:8] if getattr(latest, "id", "") else ""
            announce = f"✅ Artifact created: id='{short_id}' type='{latest.type}' in package '{pkg_name}'"
    
        # Mark consumed for this package
        self._last_announced[pkg_name] = latest.id
        try:
            setattr(latest, "_announce", None)  # optional: clear per-artifact flag
        except Exception:
            pass
        return announce


    def _remember_with_langgraph(self, package_name: str, artifact_id: str, note: str | None = None):
        """
        Minimal, safe write into MemorySaver. If saver not present, no-op.
        Stores only small refs (ids + notes), not full artifacts.
        """
        if not (self.memory_saver and package_name and artifact_id):
            return
        # Read existing state; MemorySaver API is flexible, we’ll keep to a single 'data' dict.
        state = self.memory_saver.get(thread_id=package_name, checkpoint_ns="conversation") or {}
        ids = state.get("artifact_ids", [])
        if artifact_id not in ids:
            ids.append(artifact_id)
        notes = state.get("notes", [])
        if note:
            notes.append(note)
        state["artifact_ids"] = ids
        state["notes"] = notes
        self.memory_saver.put(thread_id=package_name, checkpoint_ns="conversation", data=state)

    def _enforce_memory_policy(self, tool_name: str, result: dict, package_name: str | None):
        if not package_name:
            return
    
        meta = self.tools.get(tool_name) or {}
        io_schema = meta.get("io_schema", {})
        outputs = io_schema.get("outputs", {}) or {}
        artifact_ids = (result or {}).get("artifact_ids", {}) or {}
        if not isinstance(artifact_ids, dict):
            print(f"[remember] {tool_name}: result missing 'artifact_ids' dict; skipping remember.")
            return
    
        pkg = self.artifacts.get_package(package_name)
        missing = []  # ← track missing remember outputs
    
        for out_name, out_spec in outputs.items():
            if not isinstance(out_spec, dict) or not out_spec.get("remember"):
                continue
            art_id = artifact_ids.get(out_name)
            if not art_id or not pkg:
                missing.append(out_name)
                continue
    
            art = pkg.get_by_id(art_id)
            if art and isinstance(art.metadata, dict):
                art.metadata["remembered"] = True
    
            note = f"{tool_name}.{out_name} → {art.type} ({art_id[:8]})" if art else None
            self._remember_with_langgraph(package_name, art_id, note)
    
        if missing:
            print(f"[remember] {tool_name}: declared remember for {missing} but no artifact_ids returned.")

    def list_remembered(self, package_name: str):
        if not self.memory_saver:
            return []
        st = self.memory_saver.get(thread_id=package_name, checkpoint_ns="conversation") or {}
        return list(st.get("artifact_ids", []))

    def memory_notes(self, package_name: str):
        if not self.memory_saver:
            return ""
        st = self.memory_saver.get(thread_id=package_name, checkpoint_ns="conversation") or {}
        return "\n".join(st.get("notes", []))