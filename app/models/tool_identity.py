from pydantic import BaseModel, Field


class ToolIdentity(BaseModel):
    """Identity information for a registered tool."""

    tool_id: str = Field(
        description="Unique identifier for the tool."
    )

    name: str = Field(
        description="Human-readable tool name."
    )

    version: str = Field(
        default="1.0.0",
        description="Semantic version of the tool."
    )

    description: str = Field(
        description="Purpose of the tool."
    )