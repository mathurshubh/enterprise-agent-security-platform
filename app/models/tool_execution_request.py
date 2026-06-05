from pydantic import BaseModel


class ToolExecutionRequest(BaseModel):
    tool: str
    arguments: dict = {}