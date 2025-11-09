# se_agent/ui/panels_widgets.py
from ipywidgets import VBox, HBox, Output, Button, Layout
from .panels import _collect_workspace, _collect_artifacts, _relevant_tools, _mk_table

class BottomWindows:
    """
    Three persistent panes (side-by-side):
      Left:  Workspace (Newest → Oldest): name, type
      Middle: Artifacts (Newest → Oldest): name, type
      Right: Runnable Tools (A → Z): name
    """
    def __init__(self, artifacts, tool_registry_like, package_name=None, border=True, height_px=320):
        self.artifacts = artifacts
        self.tool_registry_like = tool_registry_like
        self.package_name = package_name

        border_css = "1px solid #ddd" if border else "none"
        padd = "6px"
        hp = f"{int(height_px)}px"

        self.btn = Button(description="Refresh", layout=Layout(width="120px"))

        # Scrollable, flexed columns
        common = dict(border=border_css, padding=padd, height=hp, overflow_y="auto", flex="1 1 0", width="33%")
        self.out_ws    = Output(layout=Layout(**common))
        self.out_af    = Output(layout=Layout(**common))
        self.out_tools = Output(layout=Layout(**common))

        self.row = HBox(
            [self.out_ws, self.out_af, self.out_tools],
            layout=Layout(width="100%", gap="12px", align_items="stretch")
        )

        self.btn.on_click(lambda _: self.refresh())

    def refresh(self):
        ws = _collect_workspace(self.artifacts, self.package_name)
        af = _collect_artifacts(self.artifacts, self.package_name)
        tools = _relevant_tools(self.tool_registry_like, ws, af)
        with self.out_ws:
            self.out_ws.clear_output()
            _mk_table(ws, ["name", "type"], "⚙️ Workspace (Newest → Oldest)")
        with self.out_af:
            self.out_af.clear_output()
            _mk_table(af, ["name", "type"], "📋 Artifacts (Newest → Oldest)")
        with self.out_tools:
            self.out_tools.clear_output()
            _mk_table([{"name": n} for n in tools], ["name"], "🛠️ Runnable Tools (A → Z)")

    def view(self):
        box = VBox(
            [HBox([self.btn], layout=Layout(justify_content="flex-start")), self.row],
            layout=Layout(width="100%")
        )
        self.refresh()
        return box

