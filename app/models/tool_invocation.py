from pydantic import BaseModel


class ToolInvocation(BaseModel):
    tool_id: str
    parameters: dict[str, str]