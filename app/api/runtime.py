from fastapi import APIRouter
from pydantic import BaseModel

from app.auth.authorization_service import AuthorizationService
from app.detection.engine import DetectionEngine
from app.detection.prompt_injection_rule import PromptInjectionRule
from app.detection.sensitive_file_access_rule import SensitiveFileAccessRule
from app.policy.policy_engine import PolicyEngine
from app.services.agent_service import AgentService
from app.services.detection_service import DetectionService
from app.services.response_service import ResponseService
from app.services.risk_service import RiskService
from app.services.runtime_service import RuntimeService
from app.services.session_service import SessionService
from app.services.tool_service import ToolService


router = APIRouter()

policy_engine = PolicyEngine()

agent_service = AgentService()
tool_service = ToolService()
session_service = SessionService()

authorization_service = AuthorizationService(
    agent_service,
    tool_service,
    policy_engine,
)

detection_service = DetectionService()
risk_service = RiskService()

response_service = ResponseService()

detection_engine = DetectionEngine(
    [
        PromptInjectionRule(),
        SensitiveFileAccessRule(),
    ]
)

runtime_service = RuntimeService(
    authorization_service,
    session_service,
    detection_engine,
    detection_service,
    risk_service,
    response_service,
)


class ExecuteRequest(BaseModel):
    session_id: str
    tool_id: str
    user_prompt: str = ""
    model_output: str = ""
    tool_output: str = ""


@router.post("/agents/{agent_id}/execute")
def execute(
    agent_id: str,
    request: ExecuteRequest,
) -> dict:
    result = runtime_service.execute(
        session_id=request.session_id,
        agent_id=agent_id,
        tool_id=request.tool_id,
        user_prompt=request.user_prompt,
        model_output=request.model_output,
        tool_output=request.tool_output,
    )

    return {
        "session_id": result.event.session_id,
        "agent_id": result.event.agent_id,
        "tool_id": result.event.tool_id,
        "decision": result.event.decision.value,
        "findings": result.findings,
        "risk_score": result.risk_assessment.risk_score,
        "risk_level": result.risk_assessment.risk_level.value,
        "response_type": (
            result.response_action.response_type.value
        ),
        "response_reason": (
            result.response_action.reason
        ),
    }
