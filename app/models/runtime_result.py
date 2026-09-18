from pydantic import BaseModel

from app.models.agent_risk_posture import AgentRiskPosture
from app.models.execution_binding import ExecutionBinding
from app.models.execution_grant import ExecutionGrant
from app.models.finding import Finding
from app.models.response_action import ResponseAction
from app.models.risk_assessment import RiskAssessment
from app.models.session_event import SessionEvent


class RuntimeResult(BaseModel):
    event: SessionEvent
    findings: list[Finding]
    # Session-scoped, for reporting and attribution (unchanged meaning).
    risk_assessment: RiskAssessment
    # Agent-scoped posture the response decision was derived from (M2b). Absent only
    # for partially constructed runtimes; see RuntimeService.execute.
    enforcement_posture: AgentRiskPosture | None = None
    response_action: ResponseAction
    # ADR-023: present only when the final decision is ALLOW. It is the only
    # authority a DefaultToolExecutor accepts for executing this operation.
    authorization: ExecutionGrant | None = None

    @property
    def authorized_binding(self) -> ExecutionBinding | None:
        if self.authorization is None:
            return None
        return self.authorization.binding

    @property
    def authorized_parameters(self) -> dict[str, str] | None:
        binding = self.authorized_binding
        if binding is None:
            return None
        return binding.parameters_dict
