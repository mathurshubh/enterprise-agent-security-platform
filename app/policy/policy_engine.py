from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import Decision
from app.models.authorization_result import (
    AuthorizationCheck,
    AuthorizationCheckStatus,
    not_evaluated_check,
)
from app.models.tool import Tool
from app.models.tool_risk_level import ToolRiskLevel


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
        tool: Tool,
        resource: str | None = None,
    ) -> PolicyEvaluationResult:
        if agent.status in {
            AgentStatus.SUSPENDED,
            AgentStatus.DISABLED,
        }:
            status_check = AuthorizationCheck(
                status=AuthorizationCheckStatus.FAILED,
                reason=f"Agent '{agent.agent_id}' is in inactive status: {agent.status.value}",
                details={"agent_id": agent.agent_id, "status": agent.status.value},
            )
            return PolicyEvaluationResult(
                decision=Decision.DENY,
                status_check=status_check,
                risk_tier_check=not_evaluated_check("status_check"),
                resource_check=not_evaluated_check("status_check"),
                reason=f"Agent '{agent.agent_id}' is in inactive status: {agent.status.value}",
            )

        status_check = AuthorizationCheck(
            status=AuthorizationCheckStatus.PASSED,
            reason=f"Agent '{agent.agent_id}' is active",
            details={"agent_id": agent.agent_id, "status": agent.status.value},
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
        tool: Tool,
        resource: str | None = None,
    ) -> Decision:
        return self.evaluate_policy(agent, tool, resource).decision