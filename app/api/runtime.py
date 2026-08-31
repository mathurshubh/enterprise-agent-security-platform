from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.auth import get_current_principal
from app.api.dependencies import runtime_service
from app.models.jwt_claims import JWTClaims, Role

router = APIRouter()



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
    principal: JWTClaims = Depends(get_current_principal),
) -> dict:
    if principal.role == Role.AGENT and principal.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent identity mismatch: token agent_id '{principal.agent_id}' does not match path agent_id '{agent_id}'",
        )

    if principal.role == Role.ANALYST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role 'ANALYST' is not authorized to execute agent runtime actions",
        )

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
