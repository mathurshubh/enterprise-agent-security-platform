from enum import Enum

from pydantic import BaseModel


class ToolRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Tool(BaseModel):
    tool_id: str
    risk_level: ToolRiskLevel
    required_permission: str
    approval_required: bool = False
    description: str = ""