from pydantic import BaseModel

from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_operational import ToolOperational


class ToolMetadata(BaseModel):
    """Complete metadata describing a registered tool."""

    identity: ToolIdentity

    governance: ToolGovernance

    capability: ToolCapability

    operational: ToolOperational