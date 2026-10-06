from typing import ClassVar, Protocol

from pydantic import BaseModel, ConfigDict

from app.models.agent import Agent, RiskTier
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




class PolicyEngine:
    PROTECTED_RESOURCES: ClassVar[set[str]] = {
        "secrets.txt",
    }

    def evaluate_policy(
        self,
        agent: Agent,
        tool: ToolGovernanceView,
        resource: str | None = None,
        *,
        lifecycle_refusal: LifecycleRefusalCode | None,
    ) -> PolicyEvaluationResult:
        """Evaluate policy for one request.

        ``lifecycle_refusal`` is the outcome of evaluating the administrative and
        enforcement planes against their own authorities (ADR-024 A.4), computed by the
        caller that holds those authorities. ``None`` means both planes permit execution.

        It is a **required** keyword rather than an optional one with a permissive default.
        A caller that forgot to supply it would otherwise obtain an unconditional
        lifecycle pass, which is the defect class this gate exists to remove -- and the
        same shape F-02 corrected on capability digests and F-09.A corrected on the
        execution gate.

        This engine no longer reads ``agent.status``. Under AP.1 that field is a computed
        projection over both planes and must not be consumed by a security decision: a
        projection can be stale, can be constructed by a caller, and asserts a single
        value where A.4 requires two independent readings.
        """
        if lifecycle_refusal is not None:
            reason = (
                f"Agent '{agent.agent_id}' may not execute: "
                f"{lifecycle_refusal.value}"
            )
            status_check = AuthorizationCheck(
                status=AuthorizationCheckStatus.FAILED,
                reason=reason,
                code=lifecycle_refusal.value,
                details={
                    "agent_id": agent.agent_id,
                    "lifecycle_refusal": lifecycle_refusal.value,
                },
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
            details={"agent_id": agent.agent_id},
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
        *,
        lifecycle_refusal: LifecycleRefusalCode | None,
    ) -> Decision:
        return self.evaluate_policy(
            agent, tool, resource, lifecycle_refusal=lifecycle_refusal
        ).decision