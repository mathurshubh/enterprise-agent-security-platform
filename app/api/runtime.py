from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth import require_execution_identity
from app.api.dependencies import runtime_service

router = APIRouter()


class ExecuteRequest(BaseModel):
    """Runtime decision request.

    ``resource`` and ``parameters`` describe the operation being evaluated, so that
    resource-aware policy applies to what would actually be executed (finding M-2).
    When both identify a resource they must agree; a contradictory request is denied
    rather than evaluated against an ambiguous target (ADR-023).
    """

    session_id: str
    tool_id: str
    resource: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)
    user_prompt: str = ""
    model_output: str = ""
    tool_output: str = ""


@router.post(
    "/agents/{agent_id}/execute",
    dependencies=[Depends(require_execution_identity)],
)
def execute(
    agent_id: str,
    request: ExecuteRequest,
) -> dict:
    """Evaluate an operation through the runtime security pipeline.

    Decision-only by design (ADR-023): this endpoint never executes a tool and never
    returns an execution grant. Grants are in-process authority and do not leave
    the platform.

    Authorization is entirely in dependencies (M3): the mount admits only AGENT
    principals, and ``require_execution_identity`` binds the execution to the
    authenticated agent's own identity. Nothing reaches this body that has not
    already been authorized, so the handler makes no security decision.
    """
    result = runtime_service.execute(
        session_id=request.session_id,
        agent_id=agent_id,
        tool_id=request.tool_id,
        resource=request.resource,
        parameters=request.parameters or None,
        user_prompt=request.user_prompt,
        model_output=request.model_output,
        tool_output=request.tool_output,
    )

    assessment = result.risk_assessment
    posture = result.enforcement_posture
    response = result.response_action

    # A request refused at a trust boundary (for example a session owned by another
    # agent) never reaches assessment. Those fields are null rather than zero, so a
    # consumer cannot read a refusal as a benign evaluation, and refusal_reason names
    # the boundary that refused it.
    return {
        "session_id": result.event.session_id,
        "agent_id": result.event.agent_id,
        "tool_id": result.event.tool_id,
        # The final decision when the pipeline established one, otherwise what
        # authorization concluded. The response shape is unchanged: an incomplete
        # request is not an externally observable state, and making it one would be
        # a separate contract decision.
        "decision": (
            result.event.final_decision
            if result.event.final_decision is not None
            else result.event.decision
        ).value,
        "findings": result.findings,
        # Session-scoped assessment: unchanged meaning for existing consumers.
        "risk_score": assessment.risk_score if assessment is not None else None,
        "risk_level": assessment.risk_level.value if assessment is not None else None,
        # Agent-scoped posture the decision was derived from (M2b).
        "enforcement_risk_score": (
            posture.risk_score
            if posture is not None
            else (assessment.risk_score if assessment is not None else None)
        ),
        "enforcement_risk_level": (
            posture.risk_level.value
            if posture is not None
            else (assessment.risk_level.value if assessment is not None else None)
        ),
        "response_type": response.response_type.value if response is not None else None,
        "response_reason": response.reason if response is not None else None,
        "refusal_reason": result.refusal_reason,
    }
