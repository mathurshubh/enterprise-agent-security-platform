from pydantic import BaseModel

from app.models.tool_metadata import ToolMetadata


class Tool(BaseModel):
    metadata: ToolMetadata

    @property
    def tool_id(self) -> str:
        """The tool family this version belongs to.

        An agent is approved for a family, never for a version (ADR-023 A'; D-1), so this
        is the authorization identity. It does not identify an executable implementation.
        """
        return self.metadata.identity.tool_id

    @property
    def version(self) -> str:
        return self.metadata.identity.version

    @property
    def identity(self) -> tuple[str, str]:
        """``(tool_id, version)`` — the identity of one concrete implementation."""
        return (self.tool_id, self.version)

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

    @property
    def enabled(self) -> bool:
        return self.metadata.operational.enabled