from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.models.audit_event import Decision
from app.models.finding import Severity
from app.models.session_event import SessionEvent
from app.services.detection_service import (
    DEFAULT_EXCESSIVE_DENIALS_WINDOW_SECONDS,
    EXCESSIVE_DENIAL_THRESHOLD,
    DetectionService,
    session_finding_id,
)


def evaluated_now() -> datetime:
    """Evaluation moment for tests that build their events relative to now.

    Passed explicitly because the detector no longer reads a clock: a windowed
    rule answers a question about a moment, and the caller owns that moment.
    """
    return datetime.now(timezone.utc)


def create_event(
    decision: Decision,
    session_id: str = "session-1",
    agent_id: str = "agent-1",
    timestamp: datetime | None = None,
) -> SessionEvent:
    kwargs = {
        "session_id": session_id,
        "agent_id": agent_id,
        "tool_id": "file_read",
        "decision": decision,
    }
    if timestamp is not None:
        kwargs["timestamp"] = timestamp
    return SessionEvent(**kwargs)


def test_detect_excessive_denials():
    service = DetectionService()
    events = [
        create_event(Decision.DENY),
        create_event(Decision.DENY),
        create_event(Decision.DENY),
    ]

    findings = service.detect_excessive_denials(events, evaluation_time=evaluated_now())

    assert len(findings) == 1
    assert findings[0].session_id == "session-1"
    assert findings[0].agent_id == "agent-1"
    assert findings[0].rule_name == "EXCESSIVE_DENIALS"
    assert findings[0].severity == Severity.MEDIUM
    assert findings[0].description == (
        "Session contains 3 denied actions"
    )
    # Identity is derived from the threshold crossing, not random, so re-deriving the
    # same crossing yields the same finding (M2a).
    assert UUID(findings[0].finding_id).version == 5
    assert findings[0].finding_id == session_finding_id(
        "EXCESSIVE_DENIALS", "session-1", "agent-1", EXCESSIVE_DENIAL_THRESHOLD
    )


def test_threshold_crossing_identity_is_stable_and_scoped():
    service = DetectionService()
    denials = [create_event(Decision.DENY) for _ in range(EXCESSIVE_DENIAL_THRESHOLD)]

    first = service.detect_excessive_denials(denials, evaluation_time=evaluated_now())[0]
    # Re-deriving from a longer history of the same session is the same evidence.
    repeated = service.detect_excessive_denials(
        denials + [create_event(Decision.DENY)], evaluation_time=evaluated_now()
    )[0]

    assert first.finding_id == repeated.finding_id

    other_session = service.detect_excessive_denials(
        [create_event(Decision.DENY, "session-2") for _ in range(EXCESSIVE_DENIAL_THRESHOLD)],
        evaluation_time=evaluated_now(),
    )[0]
    other_agent = service.detect_excessive_denials(
        [
            create_event(Decision.DENY, "session-1", "agent-2")
            for _ in range(EXCESSIVE_DENIAL_THRESHOLD)
        ],
        evaluation_time=evaluated_now(),
    )[0]

    assert len({first.finding_id, other_session.finding_id, other_agent.finding_id}) == 3


def test_no_findings_below_threshold():
    service = DetectionService()
    events = [
        create_event(Decision.DENY),
        create_event(Decision.DENY),
    ]

    findings = service.detect_excessive_denials(events, evaluation_time=evaluated_now())

    assert not findings


def test_ignore_non_deny_events():
    service = DetectionService()
    events = [
        create_event(Decision.DENY),
        create_event(Decision.ALLOW),
        create_event(Decision.APPROVAL_REQUIRED),
        create_event(Decision.DENY),
    ]

    findings = service.detect_excessive_denials(events, evaluation_time=evaluated_now())

    assert not findings


def test_denials_are_attributed_per_agent_not_per_session():
    """Ownership is authoritative state, never inferred from whichever event is first.

    Grouping by session alone would credit the aggregate to the agent of the earliest
    denial, letting interleaved activity be attributed to another agent (NEW-002).
    """
    service = DetectionService()
    events = [
        create_event(Decision.DENY, "session-1", "agent-a"),
        create_event(Decision.DENY, "session-1", "agent-b"),
        create_event(Decision.DENY, "session-1", "agent-a"),
        create_event(Decision.DENY, "session-1", "agent-b"),
    ]

    findings = service.detect_excessive_denials(events, evaluation_time=evaluated_now())

    # Two denials each: neither agent reaches the threshold on its own.
    assert findings == []


def test_only_the_agent_that_crossed_the_threshold_is_reported():
    service = DetectionService()
    events = [
        create_event(Decision.DENY, "session-1", "agent-a"),
        create_event(Decision.DENY, "session-1", "agent-b"),
        create_event(Decision.DENY, "session-1", "agent-a"),
        create_event(Decision.DENY, "session-1", "agent-b"),
        create_event(Decision.DENY, "session-1", "agent-b"),
    ]

    findings = service.detect_excessive_denials(events, evaluation_time=evaluated_now())

    assert len(findings) == 1
    assert findings[0].agent_id == "agent-b"
    assert findings[0].session_id == "session-1"


def test_multiple_sessions_generate_findings():
    service = DetectionService()
    events = [
        create_event(Decision.DENY, "session-1", "agent-1"),
        create_event(Decision.DENY, "session-2", "agent-2"),
        create_event(Decision.DENY, "session-1", "agent-1"),
        create_event(Decision.DENY, "session-2", "agent-2"),
        create_event(Decision.DENY, "session-1", "agent-1"),
        create_event(Decision.DENY, "session-2", "agent-2"),
    ]

    findings = service.detect_excessive_denials(events, evaluation_time=evaluated_now())

    assert len(findings) == 2
    assert {finding.session_id for finding in findings} == {
        "session-1",
        "session-2",
    }


class TestExcessiveDenialsTemporalSemantics:
    """M4 Step 2C-A: Excessive denials temporal sliding window and cumulative semantics."""

    def test_cumulative_semantics_with_intervening_decisions(self) -> None:
        """Intervening ALLOW and APPROVAL_REQUIRED do not reset the cumulative denial counter."""
        service = DetectionService()
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        events = [
            create_event(Decision.DENY, timestamp=now - timedelta(seconds=100)),
            create_event(Decision.ALLOW, timestamp=now - timedelta(seconds=80)),
            create_event(Decision.DENY, timestamp=now - timedelta(seconds=60)),
            create_event(Decision.APPROVAL_REQUIRED, timestamp=now - timedelta(seconds=40)),
            create_event(Decision.DENY, timestamp=now - timedelta(seconds=20)),
        ]

        findings = service.detect_excessive_denials(events, evaluation_time=now)

        assert len(findings) == 1
        assert findings[0].rule_name == "EXCESSIVE_DENIALS"
        assert findings[0].description == "Session contains 3 denied actions"

    def test_cross_agent_isolation_with_interleaved_denials(self) -> None:
        """Interleaved denials for different agents are partitioned by agent_id."""
        service = DetectionService()
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        events = [
            create_event(
                Decision.DENY,
                "session-1",
                "agent-A",
                timestamp=now - timedelta(seconds=40),
            ),
            create_event(
                Decision.DENY,
                "session-1",
                "agent-A",
                timestamp=now - timedelta(seconds=30),
            ),
            create_event(
                Decision.DENY,
                "session-1",
                "agent-B",
                timestamp=now - timedelta(seconds=20),
            ),
            create_event(
                Decision.DENY,
                "session-1",
                "agent-A",
                timestamp=now - timedelta(seconds=10),
            ),
        ]

        findings = service.detect_excessive_denials(events, evaluation_time=now)

        assert len(findings) == 1
        assert findings[0].agent_id == "agent-A"
        assert findings[0].session_id == "session-1"

    def test_boundary_timestamp_inclusion_and_exclusion(self) -> None:
        """Boundary test: event exactly at now - T is included; strictly older (< now - T) is excluded."""
        t_window = 1800.0
        service = DetectionService(excessive_denials_window_seconds=t_window)
        now = datetime(2026, 1, 1, 12, 30, 0, tzinfo=timezone.utc)
        exact_boundary = now - timedelta(seconds=t_window)
        older_than_boundary = now - timedelta(seconds=t_window + 1)

        # Case 1: First denial is exactly on the boundary (included) -> 3 denials in window -> triggers
        events_on_boundary = [
            create_event(Decision.DENY, timestamp=exact_boundary),
            create_event(Decision.DENY, timestamp=now - timedelta(seconds=60)),
            create_event(Decision.DENY, timestamp=now - timedelta(seconds=10)),
        ]
        findings_included = service.detect_excessive_denials(
            events_on_boundary, evaluation_time=now
        )
        assert len(findings_included) == 1

        # Case 2: First denial is strictly older than boundary (excluded) -> only 2 denials in window -> no finding
        events_older = [
            create_event(Decision.DENY, timestamp=older_than_boundary),
            create_event(Decision.DENY, timestamp=now - timedelta(seconds=60)),
            create_event(Decision.DENY, timestamp=now - timedelta(seconds=10)),
        ]
        findings_excluded = service.detect_excessive_denials(
            events_older, evaluation_time=now
        )
        assert len(findings_excluded) == 0

    def test_all_denials_expired_produces_no_findings(self) -> None:
        """Denials occurring entirely outside the sliding window are disregarded."""
        service = DetectionService(excessive_denials_window_seconds=1800.0)
        now = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)

        # 3 denials that occurred 2 hours ago
        events = [
            create_event(Decision.DENY, timestamp=now - timedelta(hours=2)),
            create_event(
                Decision.DENY, timestamp=now - timedelta(hours=2, seconds=-10)
            ),
            create_event(
                Decision.DENY, timestamp=now - timedelta(hours=2, seconds=-20)
            ),
        ]

        findings = service.detect_excessive_denials(events, evaluation_time=now)
        assert len(findings) == 0

    def test_configurable_window_and_validation(self) -> None:
        """Window is configurable, defaults to 1800s, and rejects non-positive durations."""
        default_service = DetectionService()
        assert (
            default_service.excessive_denials_window_seconds
            == DEFAULT_EXCESSIVE_DENIALS_WINDOW_SECONDS
        )
        assert (
            default_service.get_rule_horizon("EXCESSIVE_DENIALS")
            == DEFAULT_EXCESSIVE_DENIALS_WINDOW_SECONDS
        )

        with pytest.raises(ValueError, match="positive"):
            DetectionService(excessive_denials_window_seconds=0)

        with pytest.raises(ValueError, match="positive"):
            DetectionService(excessive_denials_window_seconds=-60.0)

        custom_service = DetectionService(excessive_denials_window_seconds=60.0)
        assert custom_service.excessive_denials_window_seconds == 60.0
        assert custom_service.get_rule_horizon("EXCESSIVE_DENIALS") == 60.0

        with pytest.raises(KeyError, match="Unknown detection rule"):
            custom_service.get_rule_horizon("UNKNOWN_RULE")
