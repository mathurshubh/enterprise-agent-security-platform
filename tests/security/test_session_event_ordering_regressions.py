"""A session's event order is a property of its history, not of heap layout.

Two events in one session can share a timestamp. Ordering them by timestamp alone
left the result decided by where the heap array happened to hold them, which is
neither insertion order nor stable across differently shaped histories:

    inserted   a0 a1 a2 a3 a4 a5
    returned   a0 a5 a1 a2 a3 a4      (ties among many out-of-order events)

Anything that answers "the first N events" therefore had no deterministic answer.
That is why `sequence_number` is persisted on the event and assigned once by
`SessionService`, rather than recomputed by each reader from timestamps.

The security-relevant invariant is not that the field exists. It is that
**session event ordering used by detection is governed by the persisted
sequence**, so a reader cannot silently fall back to timestamp-only ordering and
reintroduce the ambiguity.

`(timestamp, sequence_number)` is the canonical deterministic ordering key;
`sequence_number` is the immutable per-session tie-breaker, not a replacement for
chronology. Chronological order is an existing contract (M4-EVENT-7) that
out-of-order arrival depends on. Sorting by sequence alone would place a
late-arriving earlier event last, overturning that contract to fix a different
problem.

Scope: ordering only. No occurrence identity, prior findings or enforcement
epoch — those build on this and are a separate change.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.audit_event import Decision
from app.models.detection_retention import DetectionRetentionPolicy
from app.models.session_event import SessionEvent
from app.services.detection_service import DetectionService
from tests.conftest import create_test_session_service

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def event(session_id: str = "s", offset: float = 0.0, tool: str = "file_read"):
    return SessionEvent(
        session_id=session_id,
        agent_id="a",
        tool_id=tool,
        decision=Decision.DENY,
        timestamp=T0 + timedelta(seconds=offset),
    )


@pytest.mark.security_invariant
def test_invariant_tied_timestamps_are_ordered_by_the_persisted_sequence() -> None:
    """The Case D regression: ties among many out-of-order events.

    The specific shape matters. Simpler tie arrangements happened to come back in
    insertion order under timestamp-only sorting, so a narrower test would have
    passed against the defect.
    """
    service = create_test_session_service()
    service.bind_or_validate("s", "a")

    for offset in range(30, 0, -3):
        service.record_event(event(offset=offset, tool=f"m{offset}"))
    tied = [service.record_event(event(offset=0, tool=f"a{i}")) for i in range(6)]

    returned = [e for e in service.list_events("s") if e.tool_id.startswith("a")]

    assert returned == tied
    assert [e.sequence_number for e in returned] == sorted(
        e.sequence_number for e in returned
    )


@pytest.mark.security_invariant
def test_invariant_ordering_is_governed_by_the_sequence_not_the_timestamp() -> None:
    """Ordering must not be derivable from timestamps alone.

    Every event here shares one timestamp, so timestamp ordering carries no
    information and only the persisted sequence can order them.
    """
    service = create_test_session_service()
    service.bind_or_validate("s", "a")

    recorded = [service.record_event(event(offset=0, tool=f"t{i}")) for i in range(12)]

    listed = service.list_events("s")

    assert listed == recorded
    assert [e.sequence_number for e in listed] == list(range(1, 13))


@pytest.mark.security_invariant
def test_invariant_the_sequence_is_scoped_to_the_session() -> None:
    """A service-wide counter would let one session's traffic shift another's
    positions, making a session's order depend on unrelated activity."""
    service = create_test_session_service()
    service.bind_or_validate("session-a", "a")
    service.bind_or_validate("session-b", "a")

    first_a = service.record_event(event("session-a"))
    first_b = service.record_event(event("session-b"))
    second_a = service.record_event(event("session-a"))

    assert first_a.sequence_number == 1
    assert first_b.sequence_number == 1
    assert second_a.sequence_number == 2


@pytest.mark.security_invariant
def test_invariant_the_sequence_is_monotonic_within_a_session() -> None:
    service = create_test_session_service()
    service.bind_or_validate("s", "a")

    recorded = [service.record_event(event(offset=i)) for i in range(10)]

    sequences = [e.sequence_number for e in recorded]
    assert sequences == list(range(1, 11))


@pytest.mark.security_invariant
def test_invariant_pruning_does_not_renumber_surviving_events() -> None:
    """Positions survive eviction.

    If the counter were rebuilt from retained events, pruning would renumber the
    survivors and reuse positions the evicted events already held — so a position
    would no longer identify one place in the history.
    """
    policy = DetectionRetentionPolicy.from_detection_service(DetectionService())
    service = create_test_session_service(retention_policy=policy)
    service.bind_or_validate("s", "a")
    service.bind_or_validate("other", "a")
    horizon = policy.total_retention_seconds

    for i in range(3):
        service.record_event(event(offset=i))

    # Age out every event of session "s", by recording elsewhere: pruning is global
    # over the heap and driven by the arriving event's timestamp. The session is
    # left with no retained events at all, which is the case that distinguishes a
    # remembered counter from one rebuilt by inspecting what survived.
    service.record_event(event(session_id="other", offset=horizon + 60))
    assert service.list_events("s") == [], "the session's events must have been pruned"

    resumed = service.record_event(event(offset=horizon + 61))

    assert resumed.sequence_number == 4, (
        "positions are never reused: rebuilding the counter from retained events "
        "would restart at 1 and hand this event a position an evicted event held"
    )


@pytest.mark.security_regression
def test_the_sequence_survives_retrieval_unchanged() -> None:
    """Assigned once and persisted, not recomputed per read."""
    service = create_test_session_service()
    service.bind_or_validate("s", "a")
    recorded = [service.record_event(event(offset=i)) for i in range(5)]

    first_read = [e.sequence_number for e in service.list_events("s")]
    second_read = [e.sequence_number for e in service.list_events("s")]

    assert first_read == second_read == [e.sequence_number for e in recorded]


@pytest.mark.security_regression
def test_an_unrecorded_event_carries_no_position() -> None:
    """Zero means unrecorded, so a position can never be mistaken for assigned."""
    assert event().sequence_number == 0


@pytest.mark.security_regression
def test_chronological_order_still_holds_for_out_of_order_arrival() -> None:
    """M4-EVENT-7, unchanged.

    The sequence breaks ties; it does not replace chronological ordering. A late
    arrival with an earlier timestamp still reads in its chronological place,
    which is what the detection window depends on.
    """
    service = create_test_session_service()
    service.bind_or_validate("s", "a")

    late_first = service.record_event(event(offset=30))
    earliest = service.record_event(event(offset=10))
    middle = service.record_event(event(offset=20))

    assert service.list_events("s") == [earliest, middle, late_first]
    assert late_first.sequence_number == 1, "arrival order still sets the position"
