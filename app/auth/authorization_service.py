from app.models.audit_event import Decision
from app.models.authorization_result import (
    AuthorizationCheck,
    AuthorizationCheckStatus,
    AuthorizationResult,
    not_evaluated_check,
)
from app.policy.policy_engine import PolicyEngine
from app.services.agent_service import (
    AgentNotFoundError,
    AgentService,
    EnforcementStateUnavailableError,
)
from app.services.tool_service import (
    ToolService,
)


class AuthorizationService:
    def __init__(
        self,
        agent_service: AgentService,
        tool_service: ToolService,
        policy_engine: PolicyEngine,
    ) -> None:
        self._agent_service = agent_service
        self._tool_service = tool_service
        self._policy_engine = policy_engine

    def evaluate(
        self,
        agent_id: str,
        tool_id: str,
        resource: str | None = None,
    ) -> AuthorizationResult:
        try:
            agent = self._agent_service.get_agent(agent_id)
        except AgentNotFoundError:
            agent_check = AuthorizationCheck(
                status=AuthorizationCheckStatus.FAILED,
                reason=f"Agent '{agent_id}' is not registered",
                details={"agent_id": agent_id},
            )
            return AuthorizationResult(
                decision=Decision.DENY,
                agent_id=agent_id,
                tool_id=tool_id,
                resource=resource,
                agent_check=agent_check,
                tool_check=not_evaluated_check("agent_check"),
                approved_tool_check=not_evaluated_check("agent_check"),
                status_check=not_evaluated_check("agent_check"),
                risk_tier_check=not_evaluated_check("agent_check"),
                resource_check=not_evaluated_check("agent_check"),
                reason=f"Agent '{agent_id}' is not registered",
            )
        except EnforcementStateUnavailableError:
            agent_check = AuthorizationCheck(
                status=AuthorizationCheckStatus.FAILED,
                reason="Security posture authority unavailable (fail-closed)",
                details={"agent_id": agent_id},
            )
            return AuthorizationResult(
                decision=Decision.DENY,
                agent_id=agent_id,
                tool_id=tool_id,
                resource=resource,
                agent_check=agent_check,
                tool_check=not_evaluated_check("agent_check"),
                approved_tool_check=not_evaluated_check("agent_check"),
                status_check=not_evaluated_check("agent_check"),
                risk_tier_check=not_evaluated_check("agent_check"),
                resource_check=not_evaluated_check("agent_check"),
                reason="Security posture authority unavailable (fail-closed)",
            )

        agent_check = AuthorizationCheck(
            status=AuthorizationCheckStatus.PASSED,
            reason=f"Agent '{agent_id}' is registered",
            details={"agent_id": agent_id},
        )

        # Authorization is family-scoped (D-1): an agent is approved for a tool, not for
        # one of its versions. So this establishes that the family exists and that the
        # agent may ask for it, and reads no version-level state.
        #
        # Enablement in particular is deliberately not read here. Whether a concrete
        # implementation may run is an enforceability question, settled at containment
        # where the version is known; answering it here would report an operational
        # disablement as though the agent's authorization had been revoked, and would
        # require this decision to pick a version, which nothing may do implicitly.
        if not self._tool_service.family_exists(tool_id):
            tool_check = AuthorizationCheck(
                status=AuthorizationCheckStatus.FAILED,
                reason=f"Tool '{tool_id}' is not registered",
                details={"tool_id": tool_id},
            )
            return AuthorizationResult(
                decision=Decision.DENY,
                agent_id=agent_id,
                tool_id=tool_id,
                resource=resource,
                agent_check=agent_check,
                tool_check=tool_check,
                approved_tool_check=not_evaluated_check("tool_check"),
                status_check=not_evaluated_check("tool_check"),
                risk_tier_check=not_evaluated_check("tool_check"),
                resource_check=not_evaluated_check("tool_check"),
                reason=f"Tool '{tool_id}' is not registered",
            )

        tool_check = AuthorizationCheck(
            status=AuthorizationCheckStatus.PASSED,
            reason=f"Tool '{tool_id}' is registered",
            details={"tool_id": tool_id},
        )

        if tool_id not in agent.approved_tools:
            approved_tool_check = AuthorizationCheck(
                status=AuthorizationCheckStatus.FAILED,
                reason=f"Tool '{tool_id}' is not approved for agent '{agent_id}'",
                details={"tool_id": tool_id, "agent_id": agent_id},
            )
            return AuthorizationResult(
                decision=Decision.DENY,
                agent_id=agent_id,
                tool_id=tool_id,
                resource=resource,
                agent_check=agent_check,
                tool_check=tool_check,
                approved_tool_check=approved_tool_check,
                status_check=not_evaluated_check("approved_tool_check"),
                risk_tier_check=not_evaluated_check("approved_tool_check"),
                resource_check=not_evaluated_check("approved_tool_check"),
                reason=f"Tool '{tool_id}' is not approved for agent '{agent_id}'",
            )

        approved_tool_check = AuthorizationCheck(
            status=AuthorizationCheckStatus.PASSED,
            reason=f"Tool '{tool_id}' is approved for agent '{agent_id}'",
            details={"tool_id": tool_id, "agent_id": agent_id},
        )

        # Policy evaluates the family's governance projection, not a version. The
        # projection is deterministic and most-restrictive, so it neither selects an
        # implementation nor lets one version's classification be the family's.
        # Both lifecycle planes are evaluated against their own authorities here, where
        # those authorities are held, and the outcome is handed to policy. The engine does
        # not read ``agent.status``: that is a computed projection, and A.4 requires two
        # independent readings rather than one collapsed value.
        policy_result = self._policy_engine.evaluate_policy(
            agent=agent,
            tool=self._tool_service.get_family_governance(tool_id),
            resource=resource,
            lifecycle_refusal=self._agent_service.lifecycle_refusal(agent_id),
        )

        return AuthorizationResult(
            decision=policy_result.decision,
            agent_id=agent_id,
            tool_id=tool_id,
            resource=resource,
            agent_check=agent_check,
            tool_check=tool_check,
            approved_tool_check=approved_tool_check,
            status_check=policy_result.status_check,
            risk_tier_check=policy_result.risk_tier_check,
            resource_check=policy_result.resource_check,
            reason=policy_result.reason,
        )

    def authorize(
        self,
        agent_id: str,
        tool_id: str,
        resource: str | None = None,
    ) -> Decision:
        return self.evaluate(agent_id, tool_id, resource).decision