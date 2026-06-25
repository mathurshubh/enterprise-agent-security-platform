from pydantic import BaseModel, Field


class ToolMetadata(BaseModel):
    """Describes a tool for governance and security."""

    tool_id: str = Field(
        description="Unique tool identifier."
    )

    name: str = Field(
        description="Human-readable tool name."
    )

    description: str = Field(
        description="Purpose of the tool."
    )

    category: str = Field(
        description="Capability category."
    )

    risk_level: str = Field(
        description="Risk classification."
    )

    required_permissions: list[str] = Field(
        default_factory=list,
        description="Permissions required to execute the tool."
    )
    