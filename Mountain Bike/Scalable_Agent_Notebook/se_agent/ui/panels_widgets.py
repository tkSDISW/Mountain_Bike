# widgets (safe inside VBox/HBox.children)
from ipywidgets import (
    VBox, HBox, Output, Button, Layout, ToggleButtons,
    Textarea, Select, Text, HTML as WHTML, Accordion
)
from IPython.display import display
from .panels import (
    _collect_workspace, _collect_artifacts, _relevant_tools, _mk_table,
    _collect_prompt_artifacts, _filter_prompts
)
import os
from se_agent.core.prompt_utils import get_prompt_path_from_artifacts
# display (for rendering inside Output)
from IPython.display import display as rdisplay, HTML as RHTML

from se_agent.core.prompt_render import extract_vars, render_template

class BottomWindows:
    """
    Mode 'state' (default): 3 panes as before.
    Mode 'prompts':
      Left  = Search box
      Middle= Filtered results (newest → oldest)
      Right = Preview + actions (Insert template, Render with tool)
    """
    def __init__(self, agent, artifacts, tool_registry_like, package_name=None,
                 border=True, height_px=320,
                 user_input_widget=None,
                 system_hint_setter=None,
                 tool_runner=None):
        """
        user_input_widget: a Textarea (or obj with `.value` str) to insert text into the chat input.
        system_hint_setter: callable(str)->None (optional, if you also want “insert as system” later).
        tool_runner: callable(tool_name:str, payload:dict)->dict result
                     If None, the 'Render with tool' button will show a warning.
        """
        self.agent = agent
        self.artifacts = artifacts
        self.tool_registry_like = tool_registry_like
        self.package_name = package_name
        self.user_input_widget = user_input_widget
        self.system_hint_setter = system_hint_setter
        self.tool_runner = tool_runner
        # Variables editor (expandable)
        self.values_editor_box = VBox()                     # <— was local before
        self.values_editor = Accordion(children=[self.values_editor_box])
        self.values_editor.set_title(0, "Edit values (optional)")
        self.values_editor.selected_index = None  # collapsed by default
        
        border_css = "1px solid #ddd" if border else "none"
        padd = "6px"
        hp = f"{int(height_px)}px"

        # Header controls
        self.mode = ToggleButtons(
            options=[("State", "state"), ("Prompts", "prompts")],
            value="state",
            layout=Layout(width="260px")
        )
        self.btn_refresh = Button(description="Refresh", layout=Layout(width="120px"))
        self.btn_refresh.on_click(self._on_refresh_click)


        # Columns (scrollable)
        common = dict(border=border_css, padding=padd, height=hp, overflow_y="auto", flex="1 1 0", width="33%")
        self.col_left  = Output(layout=Layout(**common))
        self.col_mid   = Output(layout=Layout(**common))
        self.col_right = Output(layout=Layout(**common))

        self.header = HBox([self.mode, self.btn_refresh], layout=Layout(justify_content="flex-start", width="100%", gap="12px"))
        self.row    = HBox([self.col_left, self.col_mid, self.col_right], layout=Layout(width="100%", gap="12px", align_items="stretch"))

        self.mode.observe(self._on_mode_change, names="value")

    def _on_refresh_click(self, _btn=None):
        self.refresh()
    # Public
    def view(self):
        box = VBox([self.header, self.row], layout=Layout(width="100%"))
        self.refresh()
        return box

    def refresh(self):
        try:
            if self.mode.value == "state":
                self._render_state_mode()
            else:
                self._render_prompts_mode()
        except Exception as e:
            # show the error in-left to keep UI alive
            with self.col_left:
                self.col_left.clear_output()
                rdisplay(RHTML(f"<pre>⚠️ Bottom pane error:\n{e}</pre>"))

    # Mode change
    def _on_mode_change(self, change):
        self.refresh()

    # ---- STATE MODE (unchanged) ----
    def _render_state_mode(self):
        ws = _collect_workspace(self.artifacts, self.package_name)
        af = _collect_artifacts(self.artifacts, self.package_name)
        tools = _relevant_tools(self.tool_registry_like, ws, af)

        with self.col_left:
            self.col_left.clear_output()
            _mk_table(ws, ["name", "type"], "⚙️ Workspace (Newest → Oldest)")
        with self.col_mid:
            self.col_mid.clear_output()
            _mk_table(af, ["name", "type"], "📦 Artifacts (Newest → Oldest)")
        with self.col_right:
            self.col_right.clear_output()
            _mk_table([{"name": n} for n in tools], ["name"], "🧰 Runnable Tools (A → Z)")

    # ---- PROMPTS MODE ----

    # in se_agent/ui/panels_widgets.py
    from se_agent.core.prompt_utils import get_prompt_path_from_artifacts
    from se_agent.core.prompt_render import extract_vars, render_template
    from IPython.display import display, HTML
    
    def _render_prompts_mode(self):
        prompt_dir = get_prompt_path_from_artifacts(self.artifacts, self.package_name)
        prompts_all = _collect_prompt_artifacts(self.artifacts, self.package_name, prompt_dir=prompt_dir)
    
        # Left: search
        with self.col_left:
            self.col_left.clear_output()
            if prompt_dir:
                rdisplay(RHTML(f"<b>🔎 Search Prompts</b><br><small>Path: <code>{prompt_dir}</code></small>"))
            else:
                rdisplay(RHTML("<b>🔎 Search Prompts</b><br><small>⚠️ No prompt path artifact found.</small>"))
            search = Text(placeholder="Filter by name, text, tags...", layout=Layout(width="100%"))
            display(search)
    
        # Middle: results
        with self.col_mid:
            self.col_mid.clear_output()
            rdisplay(RHTML("<b>🧠 Results</b>"))
            names = [p["name"] for p in prompts_all]
            sel = Select(options=names, layout=Layout(width="100%", height="100%"))
            display(sel)
        # Right: preview + variable form + actions
        with self.col_right:
            self.col_right.clear_output()
            rdisplay(RHTML("<b>📄 Template · Variables · Actions</b>"))
            preview = Textarea(value="", layout=Layout(width="100%", height="8.2em"), disabled=True)
        
            vars_list_box = Textarea(value="", layout=Layout(width="100%", height="8.2em"), disabled=True)
        
            btn_save = Button(description="Save as Artifact", layout=Layout(width="100%"))
            status   = Output(layout=Layout(border="none", padding="0", height="auto"))
        
            rdisplay(preview)
            rdisplay(RHTML("<b>Variables</b>"))
            rdisplay(vars_list_box)
            rdisplay(btn_save)
            rdisplay(status)
        
        def _current_prompt():
            src = _filter_prompts(prompts_all, search.value) if (search.value or "").strip() else prompts_all
            name = sel.value
            return next((p for p in src if p["name"] == name), None)
            
     
        def _update_preview_and_vars():
            p = _current_prompt()
            preview.value = (p or {}).get("text","")
            _rebuild_vars_ui()


        
        def _collect_values():
            vals = {}
            for group in getattr(self.values_editor_box, "children", []):
                if len(group.children) >= 2 and hasattr(group.children[1], "value"):
                    key = (group.children[0].value or "").replace("<b>","").replace("</b>","")
                    vals[key] = group.children[1].value
            return vals
            
        def _rebuild_vars_ui():
            p = _current_prompt() or {}
            keys = p.get("vars") or []
            defaults = p.get("defaults") or {}
        
            if not keys:
                vars_list_box.value = "(no variables)"
            else:
                lines = []
                for k in keys:
                    lines.append(f"{k} = {defaults[k]}" if k in defaults and str(defaults[k]) != "" else k)
                vars_list_box.value = "\n".join(lines)
        
            rows = []
            for k in keys:
                rows.append(VBox([
                    WHTML(f"<b>{k}</b>"),
                    Textarea(value=str(defaults.get(k, "")),
                             placeholder=f"Enter value for {k}",
                             layout=Layout(width="100%", height="2.6em"))
                ], layout=Layout(border="1px solid #eee", padding="4px")))
            self.values_editor_box.children = tuple(rows)


        def _on_save_artifact(_btn=None):  # ← local handler (no 'self' param)
            p     = _current_prompt() or {}
            tmpl  = p.get("text", "")
            vals  = _collect_values()
            title = p.get("name") or (p.get("meta") or {}).get("title") or "Prompt"
            pkg   = None
        
            rendered = None
            try:
                out = (self.agent.run(
                    tool_name="render_prompt_with_values",
                    package_name=pkg,
                    input_data={
                        "template_text": tmpl,
                        "values": vals,
                        "template_name": p.get("name"),
                        "source_path": p.get("source_path"),
                    },
                ) or {})
                rendered = out.get("text") or out.get("rendered_text")
            except Exception:
                rendered = None
        
            if not rendered:
                try:
                    from jinja2 import Environment, StrictUndefined
                    _J = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
                    rendered = _J.from_string(tmpl or "").render(**(vals or {}))
                except Exception as e:
                    with status:
                        status.clear_output()
                        rdisplay(RHTML(f"<pre>❌ Render failed: {e}</pre>"))
                    return
        
            res = (self.agent.run(
                tool_name="save_prompt_artifact",
                package_name=pkg,
                input_data={
                    "name": title,
                    "text": rendered,
                    "source_path": p.get("source_path"),
                    "template_name": p.get("name") or (p.get("meta") or {}).get("title"),
                    "tags": p.get("tags") or (p.get("meta") or {}).get("tags") or [],
                },
            ) or {})
        
            #self._show_tool_result("save_prompt_artifact", res)
            self.refresh()
        

        btn_save.on_click(_on_save_artifact)
        
 
        
            
        
        def _update_results():
            filtered = _filter_prompts(prompts_all, search.value)
            names2 = [p["name"] for p in filtered]
            sel.options = names2
            if names2:
                sel.value = names2[0]
            _update_preview_and_vars()

        # events
        search.observe(lambda ch: (_update_list := _update_results()) if ch["name"]=="value" else None, names="value")
        sel.observe(lambda ch: _update_preview_and_vars() if ch["name"]=="value" else None, names="value")

        btn_save.on_click(_on_save_artifact)
    
        _update_results()


 

