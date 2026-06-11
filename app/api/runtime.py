from fastapi import APIRouter
from pydantic import BaseModel

from app.auth.authorization_service import AuthorizationService
from app.policy.policy_engine import PolicyEngine
from app.services.agent_service import AgentService
from app.services.detection_service import DetectionService
from app.services.risk_service import RiskService
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
    DetectionService(),
    RiskService(),
)


class ExecuteRequest(BaseModel):
    session_id: str
    tool_id: str


@router.post("/agents/{agent_id}/execute")
def execute(
    agent_id: str,
    request: ExecuteRequest,
) -> dict:
    result = runtime_service.execute(
        session_id=request.session_id,
        agent_id=agent_id,
        tool_id=request.tool_id,
    )

    return {
        "session_id": result.event.session_id,
        "agent_id": result.event.agent_id,
        "tool_id": result.event.tool_id,
        "decision": result.event.decision.value,
        "findings": result.findings,
        "risk_score": result.risk_assessment.risk_score,
        "risk_level": result.risk_assessment.risk_level.value,
    }
