from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter()


class ExecuteRequest(BaseModel):
    session_id: str
    tool_id: str


@router.post("/agents/{agent_id}/execute")
def execute(
    agent_id: str,
    request: ExecuteRequest,
) -> dict[str, str]:
    return {
        "status": "received",
        "agent_id": agent_id,
    }
