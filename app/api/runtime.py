from fastapi import APIRouter
from pydantic import BaseModel

from app.auth.authorization_service import AuthorizationService
from app.policy.policy_engine import PolicyEngine
from app.services.agent_service import AgentService
from app.services.runtime_service import RuntimeService
from app.services.session_service import SessionService
from app.services.tool_service import ToolService


router = APIRouter()

runtime_service = RuntimeService(
    AuthorizationService(
        AgentService(),
        ToolService(),
        PolicyEngine(),
    ),
    SessionService(),
)


class ExecuteRequest(BaseModel):
    session_id: str
    tool_id: str


@router.post("/agents/{agent_id}/execute")
def execute(
    agent_id: str,
    request: ExecuteRequest,
) -> dict[str, str]:
    event = runtime_service.execute(
        session_id=request.session_id,
        agent_id=agent_id,
        tool_id=request.tool_id,
    )

    return {
        "session_id": event.session_id,
        "agent_id": event.agent_id,
        "tool_id": event.tool_id,
        "decision": event.decision.value,
    }
