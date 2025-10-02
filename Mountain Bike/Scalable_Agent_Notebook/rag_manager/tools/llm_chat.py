from rag_manager.core.tool_registry import BaseTool
from rag_manager.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage, Artifact
from rag_manager.core.llm_config import load_llm_config
from openai import OpenAI


class LLMChatTool(BaseTool):
    name = "llm_chat"
    description = "Chat with an LLM. It is tool-aware and can suggest tool calls."
    def __init__(self, config_name=None):
        super().__init__()
        cfg = load_llm_config(config_name=config_name)
        self.client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        self.model = cfg["model"]
        self.tool_registry = None  # injected later in AgentCore


    def run(self, input_data, artifacts=None, package_name=None, **kwargs):
        prompt = input_data.get("prompt", "")
        context = input_data.get("context", "")
        messages = input_data.get("messages", [])
    
        # --- Inject tool-awareness context ---
        if self.tool_registry:
            tools = self.tool_registry.list_tools()
            tool_list_str = "\n".join([f"- {t['name']}: {t['description']}" for t in tools])
            context = (
                context
                + "\n\nYou have access to the following tools:\n"
                + tool_list_str
                + "\n⚠️ Respond with run:<tool_name> {json_input} when appropriate."
            )
    
        # --- Rehydrate from artifacts if no explicit messages provided ---
        if not messages and artifacts and package_name:
            pkg = artifacts.get_package(package_name)
            if pkg:
                convo_artifacts = [a for a in pkg.artifacts.values() if a.type == "conversation"]
                for a in convo_artifacts[-5:]:  # last 5 turns
                    messages.append({"role": "user", "content": a.content["prompt"]})
                    messages.append({"role": "assistant", "content": a.content["response"]})
                if pkg.artifacts:
                    context += (
                        "\n\n[State] Artifacts are available in memory. "
                        "To inspect them use:\n"
                        "- run:list_artifacts {}\n"
                        "- run:show_artifact {\"type\": \"hierarchy\"}  # or any stored type\n"
                        "- run:describe_state {}\n"
                    )
    
        # --- Always ensure context is pinned at the top ---
        if context:
            # If messages are provided, trust them; don't append the user prompt again
            if messages:
                # ensure system/tool context is pinned at messages[0]
                if context:
                    if messages[0]["role"] == "system":
                        messages[0] = {"role": "system", "content": context}
                    else:
                        messages.insert(0, {"role": "system", "content": context})
            else:
                # build fresh conversation from prompt + context
                if context:
                    messages = [{"role": "system", "content": context}]
                messages.append({"role": "user", "content": prompt})
    
        # --- Add the new user prompt if it's not a duplicate ---
        if not messages or messages[-1]["role"] != "user" or messages[-1]["content"] != prompt:
            messages.append({"role": "user", "content": prompt})
    
        # --- Call the LLM ---
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        reply = response.choices[0].message.content
    
        # --- Save this turn into artifacts for memory ---
        if artifacts and package_name:
            pkg = artifacts.get_package(package_name)
            if pkg:
                pkg.add_artifact(
                    Artifact(
                        type_="conversation",
                        content={"prompt": prompt, "response": reply},
                        metadata={"model": self.model}
                    )
                )
    
        return {"response": reply, "model": self.model}
