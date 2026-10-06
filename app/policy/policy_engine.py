from typing import ClassVar, Protocol

from pydantic import BaseModel, ConfigDict

from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import Decision
from app.models.authorization_result import (
    AuthorizationCheck,
    AuthorizationCheckStatus,
    LifecycleRefusalCode,
    not_evaluated_check,
)
from app.models.tool_risk_level import ToolRiskLevel


class ToolGovernanceView(Protocol):
    """What policy needs to know about the tool being evaluated.

    Authorization is family-scoped, so what policy receives is the family's governance
    projection rather than one version. Declared as a Protocol because the attributes are
    all it uses, and because naming a concrete model here would invite this decision to
    start reading version-level state.
    """

    @property
    def tool_id(self) -> str: ...

    @property
    def risk_level(self) -> ToolRiskLevel: ...


class PolicyEvaluationResult(BaseModel):
    """The immutable outcome of policy evaluation across status, risk tier, and resource constraints."""

    model_config = ConfigDict(frozen=True)

    decision: Decision
    status_check: AuthorizationCheck
    risk_tier_check: AuthorizationCheck
    resource_check: AuthorizationCheck
    reason: str


# Codes for the lifecycle states that are known to be non-executable (ADR-024 A.4). A state
# absent from this mapping is still denied; it is the *code* that defaults, never the
# decision. ``AGENT_NOT_ACTIVE`` is the honest answer for an unclassified state: all that has
# been established is that it is not the executable one.
_LIFECYCLE_REFUSAL_CODES: dict[AgentStatus, LifecycleRefusalCode] = {
    AgentStatus.REGISTERED: LifecycleRefusalCode.AGENT_NOT_ACTIVE,
    AgentStatus.DISABLED: LifecycleRefusalCode.AGENT_DISABLED,
    AgentStatus.SUSPENDED: LifecycleRefusalCode.AGENT_SUSPENDED,
}


class PolicyEngine:
    PROTECTED_RESOURCES: ClassVar[set[str]] = {
        "secrets.txt",
    }

    def evaluate_policy(
        self,
        agent: Agent,
        tool: ToolGovernanceView,
        resource: str | None = None,
    ) -> PolicyEvaluationResult:
        # Execution is permitted by the presence of the executable state, never inferred
        # from the absence of a deny condition (ADR-024 amendment A.4). The previous form
        # denied only SUSPENDED and DISABLED, which made REGISTERED executable by omission
        # and would have made every state added later executable the same way. An allow-list
        # inverts that default: a state nobody classified is non-executable.
        #
        # Partial implementation of A.4. This reads ``agent.status``, which is a projection
        # over the administrative and enforcement planes, not the two authoritative sources.
        # A.4 requires each condition evaluated independently against its own authority, and
        # that needs the administrative plane. What holds here is the fail-closed default;
        # independent plane evaluation does not yet.
        if agent.status is not AgentStatus.ACTIVE:
            status_value = getattr(agent.status, "value", str(agent.status))
            code = _LIFECYCLE_REFUSAL_CODES.get(
                agent.status, LifecycleRefusalCode.AGENT_NOT_ACTIVE
            )
            reason = (
                f"Agent '{agent.agent_id}' is not in an executable lifecycle state: "
                f"{status_value}"
            )
            status_check = AuthorizationCheck(
                status=AuthorizationCheckStatus.FAILED,
                reason=reason,
                code=code.value,
                details={"agent_id": agent.agent_id, "status": status_value},
            )
            return PolicyEvaluationResult(
                decision=Decision.DENY,
                status_check=status_check,
                risk_tier_check=not_evaluated_check("status_check"),
                resource_check=not_evaluated_check("status_check"),
                reason=reason,
            )

        status_check = AuthorizationCheck(
            status=AuthorizationCheckStatus.PASSED,
            reason=f"Agent '{agent.agent_id}' is active",
            details={"agent_id": agent.agent_id, "status": AgentStatus.ACTIVE.value},
        )

        if (
            agent.risk_tier == RiskTier.LOW
            and tool.risk_level in {
                ToolRiskLevel.HIGH,
                ToolRiskLevel.CRITICAL,
            }
        ):
            risk_tier_check = AuthorizationCheck(
                status=AuthorizationCheckStatus.FAILED,
                reason=(
                    f"Agent risk tier '{agent.risk_tier.value}' cannot execute "
                    f"tool with risk level '{tool.risk_level.value}'"
                ),
                details={
                    "risk_tier": agent.risk_tier.value,
                    "tool_risk_level": tool.risk_level.value,
                },
            )
            return PolicyEvaluationResult(
                decision=Decision.DENY,
                status_check=status_check,
                risk_tier_check=risk_tier_check,
                resource_check=not_evaluated_check("risk_tier_check"),
                reason=(
                    f"Agent risk tier '{agent.risk_tier.value}' cannot execute "
                    f"tool with risk level '{tool.risk_level.value}'"
                ),
            )

        risk_tier_check = AuthorizationCheck(
            status=AuthorizationCheckStatus.PASSED,
            reason=(
                f"Agent risk tier '{agent.risk_tier.value}' permits "
                f"tool risk level '{tool.risk_level.value}'"
            ),
            details={
                "risk_tier": agent.risk_tier.value,
                "tool_risk_level": tool.risk_level.value,
            },
        )

        if (
            tool.tool_id == "file_read"
            and resource in self.PROTECTED_RESOURCES
        ):
            resource_check = AuthorizationCheck(
                status=AuthorizationCheckStatus.FAILED,
                reason=f"Access to protected resource '{resource}' is denied",
                details={
                    "resource": str(resource),
                    "tool_id": tool.tool_id,
                },
            )
            return PolicyEvaluationResult(
                decision=Decision.DENY,
                status_check=status_check,
                risk_tier_check=risk_tier_check,
                resource_check=resource_check,
                reason=f"Access to protected resource '{resource}' is denied",
            )

        resource_check = AuthorizationCheck(
            status=AuthorizationCheckStatus.PASSED,
            reason=(
                f"Access to resource '{resource}' is permitted"
                if resource is not None
                else "No resource restriction evaluated"
            ),
            details={"resource": resource} if resource is not None else {},
        )

        if tool.risk_level == ToolRiskLevel.CRITICAL:
            return PolicyEvaluationResult(
                decision=Decision.APPROVAL_REQUIRED,
                status_check=status_check,
                risk_tier_check=risk_tier_check,
                resource_check=resource_check,
                reason=(
                    f"Tool '{tool.tool_id}' has CRITICAL risk level; "
                    "human approval is required"
                ),
            )

        return PolicyEvaluationResult(
            decision=Decision.ALLOW,
            status_check=status_check,
            risk_tier_check=risk_tier_check,
            resource_check=resource_check,
            reason="All policy checks passed",
        )

    def evaluate(
        self,
        agent: Agent,
        tool: ToolGovernanceView,
        resource: str | None = None,
    ) -> Decision:
        return self.evaluate_policy(agent, tool, resource).decision