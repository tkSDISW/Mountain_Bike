# rag_manager/tools/interactive_chat.py

from rag_manager.core.tool_registry import BaseTool

class InteractiveChatTool(BaseTool):
    name = "interactive_chat"
    description = "Launch an interactive chat session with file attach, using llm_chat internally."

    def run(self, input_data, artifacts=None, **kwargs):
        """
        Start an interactive chat UI.
        input_data can include:
          - context: system context for the assistant
          - package: optional package to capture conversation artifacts
        """
        from rag_manager.core.agent import AgentCore  # safe import to avoid circulars

        context = input_data.get("context", "You are a helpful assistant.")
        package_name = input_data.get("package")

        # The current agent instance must be passed via kwargs
        agent: AgentCore = kwargs.get("agent")
        if not agent:
            raise ValueError("InteractiveChatTool requires 'agent' passed via kwargs")

        return agent.interactive_chat(package_name=package_name, context=context)
