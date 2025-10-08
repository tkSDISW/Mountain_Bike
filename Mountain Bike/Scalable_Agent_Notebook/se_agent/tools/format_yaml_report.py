

from contextlib import redirect_stdout
from se_agent.tools.tool_patterns import  DisplayTool
import io
from contextlib import redirect_stdout


class FormatYAMLReportTool(DisplayTool):
    """
    Display: Convert YAML (from a yaml_content artifact) into an engineer-friendly HTML report,
    optionally guided by a prompt artifact (type='prompt').

    Inputs:
      • yaml_content_alias / yaml_content_id           : identifies a 'yaml_content' artifact (REQUIRED)
      • prompt_alias / prompt_id : identifies a 'prompt' artifact with text (OPTIONAL)

    Behavior:
      • Fetch YAML string from the yaml_content artifact
      • Fetch a custom prompt (if provided), else use a default system prompt
      • Use Open_AI_RAG_manager.ChatGPTAnalyzer to produce compact HTML
      • Return {'html': ..., 'displayed': True} so the agent shows it once
    """

    name = "format_yaml_report"
    description = (
        "Format a YAML artifact into a concise engineer-friendly HTML report via RAG Manager. "
        "Required: yaml_content_alias or yaml_content_id of a 'yaml_content' artifact. "
        "Required: prompt_alias or prompt_id of a 'prompt' artifact (string) to steer formatting. "
        "Planner rules: (1) Always pass the YAML by alias/id; (1) Always pass the prompt by alias/id;"
        "(3) No raw YAML in inputs. Example: "
        "{\"actions\":[{\"tool\":\"format_yaml_report\",\"input\":{"
        "\"yaml_content_alias\":\"Bike_CS_yaml\",\"prompt_alias\":\"context_view_prompt\"}}]}"
        "The tool converts the yaml content via a promt into a concise readable HTML "
        "using the RAG Manager formatter."
    )
    category = "display"  # Display tool; no artifact created

    # --- Minimal registry helpers consistent with your current API ---
    def _pkg_name(self, artifacts, package_name):
        return package_name or getattr(artifacts, "active_package", None)

    def _get_by_alias(self, artifacts, pkg_name, alias):
        try:
            pkg = artifacts.get_package(pkg_name)
            if not pkg or not hasattr(pkg, "artifacts"):
                return None
            arts = list(pkg.artifacts.values())
            matches = [a for a in arts if getattr(a, "alias", None) == alias]
            if not matches:
                return None
            matches.sort(key=lambda a: getattr(a, "_created_at", 0), reverse=True)
            return matches[0]
        except Exception:
            return None

    def _get_by_id(self, artifacts, pkg_name, art_id):
        try:
            return artifacts.get_artifact(pkg_name, art_id)  # your current signature
        except Exception:
            return None

    def render(self, input_data, artifacts, package_name=None):
        # --- Resolve YAML artifact
        pkg_name = self._pkg_name(artifacts, package_name)
        yaml_art = None

        yaml_alias = input_data.get("yaml_content_alias")
        yaml_id    = input_data.get("yaml_content_id")

        if not artifacts or not pkg_name:
            return "<p style='color:red'>❌ No artifact registry or active package.</p>"

        if yaml_alias:
            yaml_art = self._get_by_alias(artifacts, pkg_name, yaml_alias)
        elif yaml_id:
            yaml_art = self._get_by_id(artifacts, pkg_name, yaml_id)

        if not yaml_art or not isinstance(yaml_art.content, str):
            return "<p style='color:red'>❌ Provide alias/id of a 'yaml_content' artifact with string content.</p>"

        yaml_text = yaml_art.content

        # --- Resolve optional prompt artifact
        prompt_text = None
        p_alias = input_data.get("prompt_alias")
        p_id    = input_data.get("prompt_id")

        if p_alias:
            p_art = self._get_by_alias(artifacts, pkg_name, p_alias)
            if p_art and isinstance(p_art.content, str):
                prompt_text = p_art.content
        elif p_id:
            p_art = self._get_by_id(artifacts, pkg_name, p_id)
            if p_art and isinstance(p_art.content, str):
                prompt_text = p_art.content

        # --- Call RAG Manager to format
        try:
            from capella_tools import Open_AI_RAG_manager
        except Exception as e:
            return f"<p style='color:red'>❌ Failed to import Open_AI_RAG_manager: {e}</p>"
        
        payload_str = yaml_text  # pass the actual YAML string to the analyzer
        
        try:
            # Initialize analyzer with YAML content
            fmt = Open_AI_RAG_manager.ChatGPTAnalyzer(yaml_content=payload_str)
    
        
            # Seed the analyzer
            fmt.initial_prompt(prompt_text)
        
            # Capture any console output the analyzer may emit
            buf = io.StringIO()
            with redirect_stdout(buf):
                html = fmt.get_response()
        
            # Optionally echo a small preview header + the HTML immediately in interactive UI
            # (We also set displayed=True below so the agent won't render it a second time.)
            try:
                captured = buf.getvalue()
                if captured.strip():
                    display(MD("### 🖨️ YAML Report Preview"))
                    display(HTML(html))
            except Exception:
                pass
        
            # Return in the shape your agent expects for self-displayed RAG outputs
            return {
                "message": "🖨️ Formatted YAML artifact into engineer-friendly HTML.",
                "ui": html,
                "html": html,
                "displayed": True  # prevent agent from re-rendering
            }
        

        except Exception as e:
            return {
                "error": f"YAML formatting failed: {e}",
                "message": f"❌ YAML formatting failed: {e}",
                "displayed": False  # let the agent render the error message
            }