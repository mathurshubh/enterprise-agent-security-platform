from app.models.tool_invocation import ToolInvocation
from app.services.ollama_service import OllamaService


class OllamaAgent:
    SYSTEM_PROMPT = """
You are a tool selection engine.

Available tools:

1. file_read
   Parameters:
   - path

2. directory_list
   Parameters:
   - path

Return ONLY valid JSON in this format:

{
  \"tool_id\": \"file_read\",
  \"parameters\": {
    \"path\": \"notes.txt\"
  }
}

Do not include markdown, explanations, or code fences.
""".strip()

    def __init__(self) -> None:
        self._ollama_service = OllamaService()

    def decide_tool(
        self,
        query: str,
    ) -> ToolInvocation:
        response = self._ollama_service.chat(
            self.SYSTEM_PROMPT,
            query,
        )

        return ToolInvocation.model_validate(
            response
        )
