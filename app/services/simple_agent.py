from app.models.tool_invocation import (
    ToolInvocation,
)


class SimpleAgent:
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