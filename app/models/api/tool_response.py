from pydantic import BaseModel


class ToolResponse(BaseModel):
    """Management API representation of a registered tool.

    Projected from ToolMetadata.identity only.  Executable tool objects
    are never exposed through the management plane (ADR-005).
    """

    tool_id: str
    name: str
    description: str
    version: str
