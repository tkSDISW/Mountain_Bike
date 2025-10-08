import json
from se_agent.core.tool_registry import BaseTool
from capella_tools import Open_AI_RAG_manager
import io
from contextlib import redirect_stdout


class FormatJsonReportTool(BaseTool):
    """
    Explicit tool to format JSON content (from an artifact or alias) into
    engineer-friendly HTML using the installed RAG Manager (ChatGPTAnalyzer).
    """
    name = "format_json_report"
    description = (
        "Generate an engineer-friendly HTML report for a JSON-based artifact. "
        "Typically used after loading or selecting an artifact (e.g., via alias). "
        "Input should include either an 'alias', 'id', or direct 'json' field. "
        "The tool converts the JSON content into a concise, readable HTML summary "
        "using the RAG Manager formatter."
    )

    def run(self, input_data, artifacts, package_name=None, **kwargs):
        alias = input_data.get("alias") or input_data.get("artifact")
        artifact_id = input_data.get("id")
        raw_json = input_data.get("json")  # optional direct JSON input
        title = input_data.get("title", "JSON View")

        # Resolve package
        pkg = artifacts.get_active_package() if package_name is None else artifacts.get_package(package_name)
        if not pkg:
            return {"message": f"❌ No package found (package_name={package_name})"}

        # Resolve artifact or raw JSON
        artifact = None
        if raw_json is not None:
            artifact = {"content": raw_json, "alias": "raw", "id": "raw", "type": "json"}
        else:
            if alias:
                artifact = pkg.get_by_alias(alias)
            elif artifact_id:
                artifact = pkg.get_by_id(artifact_id)

        if not artifact:
            return {"message": f"❌ Artifact not found (alias={alias}, id={artifact_id})"}

        # Ensure string payload
        try:
            payload_str = json.dumps(artifact["content"] if isinstance(artifact, dict) else artifact.content, indent=2)
        except Exception:
            payload_str = str(artifact["content"] if isinstance(artifact, dict) else artifact.content)

        # Use ChatGPTAnalyzer to format as HTML
        #fmt = Open_AI_RAG_manager.ChatGPTAnalyzer(yaml_content="")  # reusing analyzer
        
        try:
            fmt = Open_AI_RAG_manager.ChatGPTAnalyzer(yaml_content=payload_str)  # reusing analyzer
            baseline_prompt = (
                "You are a formatting assistant. Convert the following JSON into a concise, "
                "engineer-friendly HTML snippet. Use headings, short bullet lists, and compact tables. "
                #"Avoid dumping the entire JSON if very long.\n\n"
                #f"<h3>{title}</h3>\n"
                #"JSON:\n```json\n" + payload_str + "\n```"
            )

            fmt.initial_prompt(baseline_prompt)
            
            # Capture any printed or displayed output from the analyzer
            buf = io.StringIO()
            with redirect_stdout(buf):
                html = fmt.get_response()
            
            # Re-display the captured content inside the chat history when invoked
            try:
                captured = buf.getvalue()
                if captured.strip():
                    # Force the content to show inside interactive chat context
                    display(Markdown("### 🖨️ JSON Report Preview"))
                    display(HTML(html))
            except Exception:
                pass
            
            return {
                "message": f"🖨️ Formatted artifact '{alias or artifact_id or 'raw'}' into engineer-friendly HTML.",
                "ui": html,
                "html": html,
                "displayed": True     # 👈 new flag
            }

        except Exception as e:
            fallback = f"<div><h3>{title}</h3><pre>{payload_str[:4000]}</pre></div>"
            return {
                "message": f"⚠️ Formatter fallback (error: {e})",
                "ui": fallback,
                "html": fallback,
            }
        

