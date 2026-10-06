"""Administrative refusal evidence: append-only, isolated, deterministic (ADR-028 §6)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.administrative_audit_event import (
    AdministrativeAuditEvent,
    AdministrativeRefusalCode,
)
from app.models.agent_administrative import Actor, AdministrativeAction
from app.repositories.in_memory import InMemoryAdministrativeAuditRepository

ADMIN = Actor(type="human", id="sec-ops-1")
T0 = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)


def event(
    event_id: str,
    agent_id: str = "agent-1",
    code: AdministrativeRefusalCode = AdministrativeRefusalCode.NOT_AUTHORIZED,
    occurred_at: datetime | None = None,
) -> AdministrativeAuditEvent:
    return AdministrativeAuditEvent(
        event_id=event_id,
        agent_id=agent_id,
        attempted_action=AdministrativeAction.ACTIVATE,
        actor=ADMIN,
        refusal_code=code,
        reason="refused in test",
        correlation_id=f"corr-{event_id}",
        occurred_at=occurred_at or T0,
    )


def test_a_refusal_round_trips() -> None:
    repo = InMemoryAdministrativeAuditRepository()
    recorded = repo.record_event(event("e-1"))
    assert repo.list_events("agent-1") == [recorded]


@pytest.mark.security_invariant
def test_a_refusal_for_an_unknown_agent_is_still_recorded() -> None:
    """The record holds no foreign key, so it survives an agent that never existed.

    This is the case that forced a separate record rather than a widened ``AuditEvent``:
    UNKNOWN_AGENT is one of the refusals the store exists for, and a foreign key would
    make the evidence unrecordable precisely when it matters (ADR-034 §8.1).
    """
    repo = InMemoryAdministrativeAuditRepository()
    repo.record_event(
        event("e-ghost", agent_id="never-existed",
              code=AdministrativeRefusalCode.UNKNOWN_AGENT)
    )
    assert len(repo.list_events("never-existed")) == 1


@pytest.mark.security_invariant
def test_stored_records_are_isolated_from_the_caller() -> None:
    """A caller holding a returned record cannot reach the stored one.

    Immutability is enforced by construction on the model; this guards the other half --
    that the store hands out copies rather than its own objects.
    """
    repo = InMemoryAdministrativeAuditRepository()
    returned = repo.record_event(event("e-iso"))
    listed = repo.list_events()[0]
    assert returned is not listed
    assert listed == returned


def test_events_are_isolated_between_agents() -> None:
    repo = InMemoryAdministrativeAuditRepository()
    repo.record_event(event("e-a", agent_id="agent-a"))
    repo.record_event(event("e-b", agent_id="agent-b"))
    assert len(repo.list_events("agent-a")) == 1
    assert len(repo.list_events("agent-b")) == 1
    assert len(repo.list_events()) == 2


def test_ordering_is_deterministic_under_timestamp_ties() -> None:
    """Equal timestamps must not leave the order to insertion luck."""
    repo = InMemoryAdministrativeAuditRepository()
    repo.record_event(event("e-z", occurred_at=T0))
    repo.record_event(event("e-a", occurred_at=T0))
    repo.record_event(event("e-m", occurred_at=T0 + timedelta(seconds=1)))
    assert [e.event_id for e in repo.list_events()] == ["e-a", "e-z", "e-m"]


@pytest.mark.security_invariant
def test_the_repository_exposes_no_way_to_rewrite_or_remove_a_record() -> None:
    """Append-only, enforced by the absence of a mutator.

    A repository that cannot express a rewrite cannot be asked to perform one. Asserted
    on the surface rather than by attempting a rewrite, because the defect this guards
    against is a method being *added* later.
    """
    surface = {
        name for name in dir(InMemoryAdministrativeAuditRepository)
        if not name.startswith("_")
    }
    assert surface == {"record_event", "list_events"}
