"""The two-plane authority, end to end (ADR-024 A.4/A.5/A.7, ADR-030 AP.1).

Integration-level counterpart to tests/policy/test_lifecycle_authorization.py, which
covers the evaluator in isolation. These drive real services, because the property that
matters is that the *authorities* decide -- not that a pure function computes correctly.
"""

import pytest

from app.auth.authorization_service import AuthorizationService
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.agent_administrative import Actor
from app.models.audit_event import Decision
from app.models.authorization_result import LifecycleRefusalCode
from app.models.watermark import BaselineWatermark
from app.policy.policy_engine import PolicyEngine
from app.runtime.execution_authority import ExecutionAuthority, IssuancePlane
from tests.conftest import create_test_agent_service, create_test_tool_service
from tests.services.test_agent_enforcement import low_risk_tool

OPERATOR = Actor(type="human", id="sec-ops-1")
AGENT_ID = "soc-agent"


def agent() -> Agent:
    return Agent(
        agent_id=AGENT_ID,
        name="SOC Agent",
        owner="security-team",
        risk_tier=RiskTier.HIGH,
        approved_tools=["file_read"],
        status=AgentStatus.ACTIVE,
    )


def authorization(agent_service):
    tool_service = create_test_tool_service()
    tool_service.register_tool(low_risk_tool())
    return AuthorizationService(agent_service, tool_service, PolicyEngine())


@pytest.mark.security_invariant
def test_a_registered_but_unactivated_agent_cannot_execute() -> None:
    """The defect F-09 exists to close, now closed at the authority rather than a field.

    A registered agent is known to the platform and not in service. Before F-09 it was
    executable by omission -- the gate denied an enumerated set and REGISTERED was not in
    it. The agent is now refused because the administrative authority says REGISTERED, not
    because a status field happens to hold that value.
    """
    service = create_test_agent_service()
    service.register_agent(agent())

    result = authorization(service).evaluate(AGENT_ID, "file_read")

    assert result.decision == Decision.DENY
    assert result.status_check.code == LifecycleRefusalCode.AGENT_NOT_ACTIVE.value


@pytest.mark.security_invariant
def test_an_activated_agent_can_execute() -> None:
    """The positive half: denying everything would satisfy every other test here."""
    service = create_test_agent_service()
    service.register_and_activate_agent(agent(), actor=OPERATOR)

    result = authorization(service).evaluate(AGENT_ID, "file_read")

    assert result.decision == Decision.ALLOW
    assert result.status_check.code is None


@pytest.mark.security_invariant
def test_an_unregistered_agent_is_administratively_unavailable_not_registered() -> None:
    """L.3: absence of a record is not a lifecycle state.

    The superseded model could not express this -- REGISTERED was the model default, so an
    agent with no administrative history and one that had been registered presented the
    same value.
    """
    service = create_test_agent_service()
    service.register_and_activate_agent(agent(), actor=OPERATOR)
    # Remove the administrative record while leaving the agent record in place.
    service.administrative_repository._states.clear()

    assert (
        service.lifecycle_refusal(AGENT_ID)
        is LifecycleRefusalCode.ADMINISTRATIVE_STATE_UNAVAILABLE
    )


@pytest.mark.security_invariant
def test_reinstating_a_disabled_agent_clears_containment_without_restoring_execution() -> None:
    """A.5 and A.7 together, which is where a single-plane model goes wrong.

    Reinstatement is permitted for a disabled agent and clears the suspension. It must not
    make the agent executable: that is the administrative plane's decision, and no
    enforcement transition may override it. With one issuance flag and one status field,
    the reinstatement would have reopened both.
    """
    service = create_test_agent_service()
    service.register_and_activate_agent(agent(), actor=OPERATOR)
    service.suspend_agent(AGENT_ID, reason="contained")
    service.disable_agent(AGENT_ID, actor=OPERATOR)

    service.reinstate_agent(
        AGENT_ID,
        actor="admin",
        reason="cleared",
        watermark=BaselineWatermark(
            agent_id=AGENT_ID, baseline_evidence_sequence=1, baseline_agent_sequence=1
        ),
    )

    # The containment is gone from the enforcement plane...
    assert service.get_enforcement_state(AGENT_ID).suspended_at is None
    # ...and the agent is still non-executable, on the administrative plane's authority.
    assert service.lifecycle_refusal(AGENT_ID) is LifecycleRefusalCode.AGENT_DISABLED
    assert authorization(service).evaluate(AGENT_ID, "file_read").decision == Decision.DENY


@pytest.mark.security_invariant
def test_the_enforcement_plane_cannot_reopen_issuance_closed_administratively() -> None:
    """The A.7 half, at the authority boundary rather than on the data structure."""
    authority = ExecutionAuthority()
    authority.suspend_issuance(AGENT_ID, plane=IssuancePlane.ADMINISTRATIVE)
    authority.suspend_issuance(AGENT_ID, plane=IssuancePlane.ENFORCEMENT)

    authority.resume_issuance(AGENT_ID, plane=IssuancePlane.ENFORCEMENT)

    assert authority.issuance_suspended(AGENT_ID) is True


@pytest.mark.security_invariant
def test_lifecycle_state_is_not_recoverable_from_the_agent_record() -> None:
    """AP.1: the projection cannot be the authorization source, by construction.

    Asserted on the stored record rather than on a service read, because the hazard is a
    caller that bypasses the service. What it gets back is non-executable, so bypassing
    fails closed rather than yielding a stale executable answer.
    """
    service = create_test_agent_service()
    service.register_and_activate_agent(agent(), actor=OPERATOR)

    stored = service.agent_repository.get(AGENT_ID)

    assert stored is not None
    assert stored.status is AgentStatus.REGISTERED
    assert service.get_agent(AGENT_ID).status is AgentStatus.ACTIVE


# --- the projection must not disagree with the decision ---------------------------------


@pytest.mark.security_invariant
@pytest.mark.parametrize("disable_first", [False, True])
def test_disabled_outranks_suspended_in_the_projection(disable_first: bool) -> None:
    """An agent that is both contained and disabled is shown as DISABLED.

    Found by mutation: swapping the two branches of the projection left every test green,
    because containment is refused for an already-disabled agent, so no test had ever
    produced an agent that was both. Disabling one that is *already* contained does.

    The order matters for the display, not the decision -- but showing SUSPENDED would
    imply reinstatement restores the agent, and it does not (A.5).
    """
    service = create_test_agent_service()
    service.register_and_activate_agent(agent(), actor=OPERATOR)

    if disable_first:
        service.disable_agent(AGENT_ID, actor=OPERATOR)
        service.suspend_agent(AGENT_ID, reason="contained")
    else:
        service.suspend_agent(AGENT_ID, reason="contained")
        service.disable_agent(AGENT_ID, actor=OPERATOR)

    assert service.get_agent(AGENT_ID).status is AgentStatus.DISABLED


@pytest.mark.security_invariant
def test_an_unestablishable_administrative_state_never_projects_as_active() -> None:
    """Found by mutation: projecting ACTIVE for an absent record survived every test.

    Nothing authorizes on the projection, so the mutation changed no decision -- which is
    exactly why it needs its own test. A console showing ACTIVE for an agent the platform
    is refusing is a false reassurance, and the projection's whole contract is that it
    cannot disagree with the decision.
    """
    service = create_test_agent_service()
    service.register_and_activate_agent(agent(), actor=OPERATOR)
    service.administrative_repository._states.clear()

    assert service.get_agent(AGENT_ID).status is not AgentStatus.ACTIVE
    assert service.lifecycle_refusal(AGENT_ID) is not None


@pytest.mark.security_invariant
def test_the_projection_says_active_exactly_when_execution_is_permitted() -> None:
    """The consistency property, over every reachable combination of the two planes.

    Stated as an equivalence rather than two implications, because either one alone is
    satisfiable by a projection that is merely more pessimistic than the decision -- and a
    projection that is more *optimistic* is the one that misleads an operator.
    """
    cases = []

    def build(activate: bool, suspend: bool, disable: bool):
        svc = create_test_agent_service()
        if activate:
            svc.register_and_activate_agent(agent(), actor=OPERATOR)
        else:
            svc.register_agent(agent())
        if suspend:
            svc.suspend_agent(AGENT_ID, reason="contained")
        if disable:
            svc.disable_agent(AGENT_ID, actor=OPERATOR)
        return svc

    for activate in (True, False):
        for suspend in (True, False):
            for disable in (True, False):
                cases.append(build(activate, suspend, disable))

    for svc in cases:
        projected_active = svc.get_agent(AGENT_ID).status is AgentStatus.ACTIVE
        permitted = svc.lifecycle_refusal(AGENT_ID) is None
        assert projected_active == permitted
