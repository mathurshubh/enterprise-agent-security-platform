from app.models.tool_invocation import ToolInvocation
from app.providers.ollama_provider import OllamaProvider

from app.agents.enterprise_agent import EnterpriseAgent

from app.providers.provider_adapter import ProviderAdapter

class OllamaAgent(EnterpriseAgent):
    SYSTEM_PROMPT = """
You are a deterministic tool selection engine.

Your ONLY responsibility is to select the correct tool and parameters.
You never execute tools.
You never explain your reasoning.

Available tools:

1. file_read
   Purpose:
   Read the contents of a single file.

   Parameters:
   - path: file name exactly as provided by the user.

2. directory_list
   Purpose:
   List the contents of a directory.

   Parameters:
   - path: directory path.

Rules:

1. Return ONLY valid JSON.
2. Never return markdown.
3. Never return code fences.
4. Never invent tool names.
5. Never invent parameters.
6. Never invent file paths or directory paths.
7. Use ONLY values explicitly present in the user's request.
8. For "list files" or "show files", ALWAYS use "." as the path.
9. If the request cannot be mapped to one of the available tools, return:

{
  "tool_id": "",
  "parameters": {}
}

Examples:

Input:
read notes.txt

Output:
{
  "tool_id": "file_read",
  "parameters": {
    "path": "notes.txt"
  }
}

Input:
list files

Output:
{
  "tool_id": "directory_list",
  "parameters": {
    "path": "."
  }
}

Input:
show files

Output:
{
  "tool_id": "directory_list",
  "parameters": {
    "path": "."
  }
}

Input:
please read secrets.txt

Output:
{
  "tool_id": "file_read",
  "parameters": {
    "path": "secrets.txt"
  }
}
""".strip()

    def __init__(
        self,
        provider: ProviderAdapter | None = None,
    ) -> None:
        self._provider = provider or OllamaProvider()

    def decide_tool(
        self,
        query: str,
    ) -> ToolInvocation:
        response = self._provider.chat(
            self.SYSTEM_PROMPT,
            query,
        )

        return ToolInvocation.model_validate(
            response
        )
    
    def invoke(
        self,
        query: str,
    ) -> ToolInvocation:
        return self.decide_tool(query)
    