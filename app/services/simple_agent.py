from app.models.tool_invocation import (
    ToolInvocation,
)

from app.agents.enterprise_agent import EnterpriseAgent

class SimpleAgent(EnterpriseAgent):

    def invoke(
            self,
            query: str,
    ) -> ToolInvocation:
            return self.decide_tool(query)
     

    def decide_tool(
        self,
        query: str,
    ) -> ToolInvocation:
        normalized_query = query.strip().lower()

        if normalized_query.startswith("read "):
            path = query.strip()[5:]

            return ToolInvocation(
                tool_id="file_read",
                parameters={
                    "path": path,
                },
            )

        if normalized_query in {
            "list files",
            "show files",
        }:
            return ToolInvocation(
                tool_id="directory_list",
                parameters={
                    "path": ".",
                },
            )

        raise ValueError(
            f"Unsupported query: {query}"
        )


   