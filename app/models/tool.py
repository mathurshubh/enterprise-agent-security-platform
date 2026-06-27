from pydantic import BaseModel

from app.models.tool_metadata import ToolMetadata


class Tool(BaseModel):
    metadata: ToolMetadata

    @property
    def tool_id(self) -> str:
        return self.metadata.identity.tool_id

    @property
    def risk_level(self) -> str:
        return self.metadata.governance.risk_level

    @property
    def required_permission(self) -> str:
        permissions = (
            self.metadata.governance.required_permissions
        )
        return permissions[0] if permissions else ""

    @property
    def approval_required(self) -> bool:
        return (
            self.metadata.governance.approval_required
        )

    @property
    def description(self) -> str:
        return self.metadata.identity.description