from pydantic import BaseModel


class ToolMetadata(BaseModel):
    tool_id: str
    name: str
    description: str
    category: str
    risk_level: str
    required_permissions: list[str]