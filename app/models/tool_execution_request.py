from pydantic import BaseModel, Field


class ToolExecutionRequest(BaseModel):
    tool_id: str
    arguments: dict = Field(default_factory=dict)