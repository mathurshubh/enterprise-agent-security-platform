"""Administrative recovery from containment (M2b Step 5).

Runtime enforcement is one-way. ``RuntimeService`` may contain an agent — suspending it
and withdrawing its execution authority — but no runtime path returns an agent to
service. Recovery runs only through this coordinator, driven by an authorized
administrative request.

    RuntimeService ──▶ contain                (automated security response)
    EnforcementCoordinator ──▶ recover        (authorized administrative action)

Reinstatement touches two independent in-memory stores, which cannot roll back
together, so the contract is **convergence, not atomicity**: a successful reinstatement
leaves the agent ACTIVE with issuance open, and every intermediate failure leaves a
state that is still fail-closed for execution and repairable by retrying.
"""

from app.models.agent import Agent, AgentStatus
from app.runtime.execution_authority import ExecutionAuthority
from app.services.agent_service import AgentService


class ReinstatementIncompleteError(Exception):
    """Raised when an agent was returned to service but issuance is still closed.

    The agent is ACTIVE while its execution authority remains withdrawn: policy admits
    its requests, but no execution grant can be issued, so nothing executes. The state
    is deliberately left in place rather than rolled back, because retrying the
    reinstatement repairs it.
    """

    def __init__(self, agent_id: str) -> None:
        super().__init__(
            f"Agent '{agent_id}' was returned to service, but execution grant issuance "
            "is still closed. Execution remains blocked; retry the reinstatement."
        )
        self.agent_id = agent_id


class EnforcementCoordinator:
    """Coordinates the two stores that together describe an agent's containment."""

    def __init__(
        self,
        agent_service: AgentService,
        execution_authority: ExecutionAuthority,
    ) -> None:
        self._agent_service = agent_service
        self._execution_authority = execution_authority

    def reinstate(self, agent_id: str, *, actor: str, reason: str) -> Agent:
        """Return a suspended agent to service and reopen its grant issuance.

        The status transition happens first. Reopening the gate before it would briefly
        grant issuance capability to an agent the registry still calls suspended, which
        is the weaker intermediate state.

        ``resume_issuance`` is called unconditionally, so retrying after a partial
        failure repairs an agent that is ACTIVE with its gate still closed.

        Raises:
            AgentNotFoundError: the agent is not registered.
            AgentNotSuspendedError: the agent is not currently suspended.
            ValueError: the reinstatement is not attributed to an actor and a reason.
            ReinstatementIncompleteError: issuance could not be reopened. The agent
                stays ACTIVE and execution stays blocked until a retry succeeds.
        """
        agent = self._agent_service.reinstate_agent(
            agent_id,
            actor=actor,
            reason=reason,
        )

        self._execution_authority.resume_issuance(agent_id)

        # Success is reported only when both halves hold. Anything else is incomplete,
        # never a successful reinstatement with a quietly blocked agent.
        if (
            agent.status != AgentStatus.ACTIVE
            or self._execution_authority.issuance_suspended(agent_id)
        ):
            raise ReinstatementIncompleteError(agent_id)

        return agent

    def repair(self, agent_id: str) -> Agent:
        """Reopen issuance for an agent that is already ACTIVE.

        The repair path for a reinstatement whose second half failed. It performs no
        status transition, so it cannot recover an agent that is still suspended.
        """
        agent = self._agent_service.get_agent(agent_id)

        if agent.status != AgentStatus.ACTIVE:
            raise ReinstatementIncompleteError(agent_id)

        self._execution_authority.resume_issuance(agent_id)

        if self._execution_authority.issuance_suspended(agent_id):
            raise ReinstatementIncompleteError(agent_id)

        return agent
