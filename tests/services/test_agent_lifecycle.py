"""Administrative lifecycle operations on AgentService (ADR-024 A.3/A.5/A.8, AP.5)."""

import pytest

from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.agent_administrative import (
    Actor,
    AdministrativeAction,
    AdministrativeLifecycleState,
)
from app.models.watermark import BaselineWatermark
from app.services.agent_service import (
    AgentService,
    IllegalAdministrativeTransitionError,
)
from tests.conftest import create_test_agent_service

OPERATOR = Actor(type="human", id="sec-ops-1")
AGENT_ID = "soc-agent"


def agent(agent_id: str = AGENT_ID) -> Agent:
    return Agent(
        agent_id=agent_id,
        name="SOC Agent",
        owner="security-team",
        risk_tier=RiskTier.HIGH,
        approved_tools=["file_read"],
        status=AgentStatus.ACTIVE,
    )


def registered_service() -> AgentService:
    service = create_test_agent_service()
    service.register_agent(agent())
    return service


class TestRegistration:
    def test_registration_yields_registered_and_grants_nothing(self) -> None:
        """A registered agent is known to the platform and not in service (A.3)."""
        service = registered_service()
        state = service.administrative_state(AGENT_ID)

        assert state is not None
        assert state.state is AdministrativeLifecycleState.REGISTERED
        assert state.administrative_version == 1

    def test_registration_is_recorded_in_the_ledger(self) -> None:
        service = registered_service()
        ledger = service.list_administrative_transitions(AGENT_ID)

        assert [t.action for t in ledger] == [AdministrativeAction.REGISTER]
        entry = ledger[0]
        assert entry.previous_state is None
        assert entry.new_state is AdministrativeLifecycleState.REGISTERED
        assert (entry.administrative_version_before, entry.administrative_version_after) == (0, 1)
        # Mandatory attribution: a system-initiated registration generates its own
        # correlation id rather than going unattributed (A.8).
        assert entry.correlation_id
        assert entry.actor.type.value == "system"

    def test_an_unknown_agent_has_no_administrative_state(self) -> None:
        """None is not REGISTERED -- it is ADMINISTRATIVE_STATE_UNAVAILABLE (L.3)."""
        service = create_test_agent_service()
        assert service.administrative_state("never-registered") is None


class TestActivation:
    def test_activation_puts_a_registered_agent_into_service(self) -> None:
        service = registered_service()
        state = service.activate_agent(AGENT_ID, actor=OPERATOR)

        assert state.state is AdministrativeLifecycleState.ACTIVE
        assert state.administrative_version == 2

    def test_activation_is_a_separate_lifecycle_event_from_registration(self) -> None:
        """A.3: distinct events even when consecutive, so two ledger entries.

        The combined helper exists for callers that legitimately do both at once; what
        makes them distinct is the evidence, not the number of calls.
        """
        service = create_test_agent_service()
        service.register_and_activate_agent(agent(), actor=OPERATOR)

        ledger = service.list_administrative_transitions(AGENT_ID)
        assert [t.action for t in ledger] == [
            AdministrativeAction.REGISTER,
            AdministrativeAction.ACTIVATE,
        ]
        assert [
            (t.administrative_version_before, t.administrative_version_after)
            for t in ledger
        ] == [(0, 1), (1, 2)]

    def test_activating_an_already_active_agent_is_refused(self) -> None:
        """Not idempotent: ACTIVE -> ACTIVE is not in the graph (AP.5).

        Refused rather than silently accepted, because a second activation would add a
        ledger entry asserting a transition that did not occur.
        """
        service = registered_service()
        service.activate_agent(AGENT_ID, actor=OPERATOR)

        with pytest.raises(IllegalAdministrativeTransitionError):
            service.activate_agent(AGENT_ID, actor=OPERATOR)


class TestDisablement:
    @pytest.mark.parametrize("activate_first", [False, True])
    def test_an_agent_can_be_disabled_from_either_source_state(
        self, activate_first: bool
    ) -> None:
        service = registered_service()
        if activate_first:
            service.activate_agent(AGENT_ID, actor=OPERATOR)

        state = service.disable_agent(AGENT_ID, actor=OPERATOR)
        assert state.state is AdministrativeLifecycleState.DISABLED

    @pytest.mark.security_invariant
    def test_disabled_is_terminal(self) -> None:
        """No administrative transition leaves DISABLED (A.3).

        Including back to REGISTERED, which is the shape a "reset this agent" feature
        would take. Re-enablement would be a separately defined, separately authorized
        transition -- and reinstatement is never that transition.
        """
        service = registered_service()
        service.disable_agent(AGENT_ID, actor=OPERATOR)

        with pytest.raises(IllegalAdministrativeTransitionError):
            service.activate_agent(AGENT_ID, actor=OPERATOR)

        assert (
            service.administrative_state(AGENT_ID).state
            is AdministrativeLifecycleState.DISABLED
        )


class TestPlaneIndependence:
    """The two planes are independently authoritative (A.5). Each must leave the other alone."""

    @pytest.mark.security_invariant
    def test_suspension_does_not_change_administrative_state(self) -> None:
        """Containment is an enforcement transition, not an administrative one."""
        service = create_test_agent_service()
        service.register_and_activate_agent(agent(), actor=OPERATOR)
        before = service.administrative_state(AGENT_ID)

        service.suspend_agent(AGENT_ID, reason="contained")

        assert service.administrative_state(AGENT_ID) == before
        assert len(service.list_administrative_transitions(AGENT_ID)) == 2

    @pytest.mark.security_invariant
    def test_reinstatement_does_not_change_administrative_state(self) -> None:
        """A.5, and the obligation this gate carries.

        Reinstatement clears the suspension and leaves the administrative state exactly
        as it was. The superseded implementation wrote ``AgentStatus.ACTIVE`` as part of
        reinstating, which conflated the planes: a reinstated agent that had never been
        activated would have been put into service by a containment-recovery operation.
        """
        service = create_test_agent_service()
        service.register_agent(agent())  # REGISTERED, deliberately never activated
        before = service.administrative_state(AGENT_ID)

        service.suspend_agent(AGENT_ID, reason="contained")
        service.reinstate_agent(
            AGENT_ID,
            actor="admin",
            reason="cleared",
            watermark=BaselineWatermark(
                agent_id=AGENT_ID,
                baseline_evidence_sequence=1,
                baseline_agent_sequence=1,
            ),
        )

        after = service.administrative_state(AGENT_ID)
        assert after == before
        assert after.state is AdministrativeLifecycleState.REGISTERED
        # The enforcement plane moved; the administrative ledger did not.
        assert len(service.list_administrative_transitions(AGENT_ID)) == 1
        assert service.get_enforcement_state(AGENT_ID).epoch == 2

    @pytest.mark.security_invariant
    def test_the_two_version_namespaces_advance_independently(self) -> None:
        """AP.2: administrative_version and epoch count different things.

        After one activation and one suspend/reinstate cycle they read 2 and 2 by
        coincidence, so the test drives them apart first -- otherwise it could not tell
        one namespace from the other.
        """
        service = create_test_agent_service()
        service.register_and_activate_agent(agent(), actor=OPERATOR)

        assert service.administrative_state(AGENT_ID).administrative_version == 2
        assert service.get_enforcement_state(AGENT_ID).epoch == 0

        service.suspend_agent(AGENT_ID, reason="contained")

        assert service.administrative_state(AGENT_ID).administrative_version == 2
        assert service.get_enforcement_state(AGENT_ID).epoch == 1


class TestAdministrativeConcurrency:
    @pytest.mark.security_invariant
    def test_a_lost_compare_and_set_is_raised_not_ignored(self) -> None:
        """A refused administrative transition must not be reported as success.

        Found by mutation: ignoring the repository's ``False`` left every test green,
        because an in-memory repository never loses a race in a single-threaded test. The
        defect it hides is the worst kind -- the caller is told the agent was activated,
        the ledger has no entry, and the authoritative state still says REGISTERED.

        Driven with a repository stubbed to lose the race, which is the only way to reach
        the branch without real concurrency.
        """
        from app.repositories.in_memory import (
            InMemoryAdministrativeStateRepository,
            InMemoryAgentRepository,
        )
        from app.services.agent_service import AdministrativeConcurrencyError

        class LosingRepository(InMemoryAdministrativeStateRepository):
            """Registers normally, then loses every compare-and-set after that.

            ``commit_registration`` is left alone deliberately: registration is a separate
            composition that does not go through ``record_transition``, so overriding it
            would test the wrong boundary.
            """

            def record_transition(self, transition, new_state, *, expected_version):
                return False

        agents = InMemoryAgentRepository()
        repo = LosingRepository(agent_repository=agents)
        service = create_test_agent_service(
            agent_repository=agents, administrative_repository=repo
        )
        service.register_agent(agent())

        with pytest.raises(AdministrativeConcurrencyError):
            service.activate_agent(AGENT_ID, actor=OPERATOR)

        # The refusal left the authoritative state exactly as it was.
        assert (
            service.administrative_state(AGENT_ID).state
            is AdministrativeLifecycleState.REGISTERED
        )
        assert len(service.list_administrative_transitions(AGENT_ID)) == 1
