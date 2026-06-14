from pydantic import BaseModel

from app.models.response_action import ResponseType


class AgentRuntimeResult(BaseModel):
    decision: str
    response_type: ResponseType
    output: str | list[str] | None