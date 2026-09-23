"""ADR-028 property 3 — an audit record is not modified after it is written.

The property was previously described as *"true by the absence of any mutator"*. It
was not. `AuditService` exposes no method named like a mutator, but two aliasing paths
reached the stored object anyway:

    list_events()   returns self._events.copy()   a SHALLOW copy -- the same records
    record_event()  returns the object it was given -- the producer keeps it live

Neither is a mutator and both could rewrite recorded evidence, so the property held
only because no caller chose to violate it. That is a property of the callers, not of
the evidence boundary.

A record that can be edited after the fact does not establish that a decision was
made; it establishes what someone last said about it. The record is therefore frozen,
which closes both paths at once — a caller cannot mutate what it received, and the
producer cannot mutate what it kept.

Scope: `AuditEvent` only. `Finding` carries the same requirement (ADR-017, ADR-029 §6)
and the same gap, but its construction assigns `rule_id` in `model_post_init`, so
freezing it needs that converted first and is deliberately not part of this change.
`SessionEvent` is mutated on the production path by design and is a separate
architectural question.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.audit_event import AuditEvent, Decision
from app.services.audit_service import AuditService


def audit_event(decision: Decision = Decision.DENY) -> AuditEvent:
    return AuditEvent(
        event_id="evt-immutability",
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
        decision=decision,
    )


@pytest.mark.security_invariant
def test_invariant_a_recorded_decision_cannot_be_rewritten_through_the_read_path() -> None:
    """The path that made the property violable: `list_events` returns the records.

    Asserted on the store's state as well as on the raised error, because a record
    that refused mutation but had already been altered would satisfy a narrower test.
    """
    service = AuditService()
    service.record_event(audit_event())

    fetched = service.list_events()[0]
    with pytest.raises(ValidationError):
        fetched.decision = Decision.ALLOW

    assert service.list_events()[0].decision == Decision.DENY


@pytest.mark.security_invariant
def test_invariant_the_producer_cannot_rewrite_what_it_recorded() -> None:
    """The second path, which deep-copying on read would have left open.

    `record_event` returns the object it was given, so the producer holds a live
    reference to the stored record for as long as it keeps one.
    """
    service = AuditService()
    event = audit_event()
    returned = service.record_event(event)

    assert returned is event, "the producer's reference is the stored record"
    with pytest.raises(ValidationError):
        event.agent_id = "agent-2"

    assert service.list_events()[0].agent_id == "agent-1"


@pytest.mark.security_invariant
def test_invariant_no_field_of_a_recorded_decision_is_writable() -> None:
    """Every field, not only the ones an attacker would obviously target.

    Attribution (`session_id`, `agent_id`) and the decision itself matter most, but a
    record whose timestamp or tool could be rewritten is equally unable to say what
    happened.
    """
    service = AuditService()
    service.record_event(audit_event())
    stored = service.list_events()[0]

    for field, value in (
        ("event_id", "evt-forged"),
        ("session_id", "session-2"),
        ("agent_id", "agent-2"),
        ("tool_id", "directory_list"),
        ("decision", Decision.ALLOW),
        ("timestamp", datetime.now(timezone.utc)),
    ):
        with pytest.raises(ValidationError):
            setattr(stored, field, value)


@pytest.mark.security_invariant
def test_invariant_immutability_is_a_property_of_the_record_not_the_store() -> None:
    """A record recovered from anywhere is immutable.

    Enforced on the model rather than by a defensive copy in `AuditService`, so a
    second store, an export path or a future persistence layer inherits the property
    instead of having to reimplement it.
    """
    detached = audit_event()

    with pytest.raises(ValidationError):
        detached.decision = Decision.ALLOW


@pytest.mark.security_regression
def test_deriving_a_changed_record_produces_a_new_one() -> None:
    """Immutability forbids editing a record, not producing a different one.

    Without this, the invariants above would be satisfied by a model that could not
    express change at all, which would block any later evidence-schema evolution.
    """
    original = audit_event()

    derived = original.model_copy(update={"decision": Decision.ALLOW})

    assert derived.decision == Decision.ALLOW
    assert original.decision == Decision.DENY
    assert derived is not original


@pytest.mark.security_regression
def test_recording_and_reading_still_work() -> None:
    """The positive control: a frozen record is still ordinary evidence."""
    service = AuditService()
    service.record_event(audit_event())
    service.record_event(
        AuditEvent(
            event_id="evt-second",
            session_id="session-1",
            agent_id="agent-1",
            tool_id="directory_list",
            decision=Decision.ALLOW,
        )
    )

    recorded = service.list_events()

    assert len(recorded) == 2
    assert [e.decision for e in recorded] == [Decision.DENY, Decision.ALLOW]
