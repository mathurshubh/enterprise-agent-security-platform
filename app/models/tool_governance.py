from pydantic import BaseModel, Field

from app.models.tool_risk_level import ToolRiskLevel


class ToolGovernance(BaseModel):
    """Governance metadata for a tool."""

    risk_level: ToolRiskLevel

    required_permissions: list[str] = Field(
        default_factory=list,
        description="Permissions required to execute the tool."
    )

    owner: str | None = Field(
        default=None,
        description="Owning team or individual."
    )

    approval_required: bool = Field(
        default=False,
        description="Whether execution requires manual approval."
    )