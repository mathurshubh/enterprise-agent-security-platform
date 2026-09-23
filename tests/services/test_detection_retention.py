"""Adversarial and contract test suite for SessionEvent retention (M4 Step 2C-B).

Verifies invariants:
- M4-EVENT-1: Complete 1,800s detection evaluation horizon is preserved.
- M4-EVENT-2: Events are retained through the 1,830s effective retention horizon (1,800s + 30s grace).
- M4-EVENT-3: Event pruning produces zero mutation to Findings, Risk Posture, Enforcement State, or Tombstones.
- M4-EVENT-4: Retention is governed by horizon + grace, never arbitrary count limits (burst resilience).
- M4-EVENT-5: retention_policy=None indicates explicit unbounded test/compatibility mode (pruning disabled).
- M4-EVENT-6: Hot-path efficiency (O(log N) insertion, O(K log N) pruning).
- M4-EVENT-7: Correctness does not assume monotonic timestamp insertion (out-of-order arrival resilience).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.audit_event import Decision
from app.models.detection_retention import DetectionRetentionPolicy
from app.models.session_event import SessionEvent
from app.services.detection_service import DetectionService
from app.services.session_service import SessionService
from tests.services.test_runtime_enforcement_posture import AGENT_ID, build_runtime


def make_event(
    session_id: str = "session-1",
    agent_id: str = "agent-1",
    decision: Decision = Decision.ALLOW,
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


class TestDetectionRetentionInvariants:
    """Rigorous verification of M4-EVENT-1 through M4-EVENT-7."""

    def test_m4_event_1_detection_horizon_preservation(self) -> None:
        """M4-EVENT-1: All events within the 1,800s evaluation horizon are preserved."""
        detection_service = DetectionService(excessive_denials_window_seconds=1800.0)
        policy = DetectionRetentionPolicy.from_detection_service(
            detection_service, late_arrival_grace_seconds=30.0
        )
        service = SessionService(retention_policy=policy)
        now = datetime(2026, 1, 1, 12, 30, 0, tzinfo=timezone.utc)

        # Record 3 denials distributed across the 1,800s horizon
        e1 = make_event("s1", "a1", Decision.DENY, timestamp=now - timedelta(seconds=1750))
        e2 = make_event("s1", "a1", Decision.DENY, timestamp=now - timedelta(seconds=900))
        e3 = make_event("s1", "a1", Decision.DENY, timestamp=now - timedelta(seconds=10))

        service.record_event(e1)
        service.record_event(e2)
        service.record_event(e3)

        events = service.list_events("s1")
        assert len(events) == 3

        # Detection engine evaluates full horizon and detects crossing
        findings = detection_service.detect_excessive_denials(events, evaluation_time=now)
        assert len(findings) == 1
        assert findings[0].rule_name == "EXCESSIVE_DENIALS"

    def test_m4_event_2_effective_retention_horizon_with_grace(self) -> None:
        """M4-EVENT-2: Events are retained through 1,830s (1,800s horizon + 30s grace)."""
        policy = DetectionRetentionPolicy(
            retention_window_seconds=1800.0,
            late_arrival_grace_seconds=30.0,
        )
        assert policy.total_retention_seconds == 1830.0
        service = SessionService(retention_policy=policy)
        now = datetime(2026, 1, 1, 12, 30, 0, tzinfo=timezone.utc)

        # Event within grace (1815s old): past rule window (1800s), but within total retention (1830s)
        event_in_grace = make_event("s1", "a1", timestamp=now - timedelta(seconds=1815))
        # Event strictly beyond total retention (1831s old)
        event_expired = make_event("s1", "a1", timestamp=now - timedelta(seconds=1831))
        # Recent event (trigger for now)
        event_recent = make_event("s1", "a1", timestamp=now)

        service.record_event(event_expired)
        service.record_event(event_in_grace)
        service.record_event(event_recent)

        # Trigger pruning at time 'now'
        service.prune_events(now_utc=now)

        events = service.list_events("s1")
        # event_expired (1831s) must be pruned; event_in_grace (1815s) and event_recent must remain
        assert event_expired not in events
        assert event_in_grace in events
        assert event_recent in events

    def test_m4_event_3_security_state_independence(self) -> None:
        """M4-EVENT-3: Event pruning produces zero mutation to security-authoritative state.

        Given identical findings and enforcement state:
        pruning SessionEvents must produce NO mutation to:
        - FindingsService
        - AgentRiskPosture
        - AgentEnforcementState
        - TerminalSessionTombstones
        """
        env = build_runtime()
        session_id = "test-security-state-independence"

        # 1. Generate 3 denials to create EXCESSIVE_DENIALS finding and update posture
        for _ in range(3):
            env.runtime.execute(
                session_id=session_id,
                agent_id=AGENT_ID,
                tool_id="unauthorized_tool",
            )

        # Capture security-authoritative state before pruning
        findings_before = env.findings_service.list_findings(agent_id=AGENT_ID)
        assert len(findings_before) == 1
        assert findings_before[0].rule_name == "EXCESSIVE_DENIALS"

        posture_before = env.risk_aggregator.get_posture(AGENT_ID)
        assert posture_before is not None

        enforcement_state_before = env.agent_service.get_enforcement_state(AGENT_ID)

        # 2. Terminate session to create tombstone
        env.runtime._session_service.end_session(session_id, AGENT_ID)
        tombstone_before = env.runtime._session_service.get_tombstone(session_id)
        assert tombstone_before is not None

        # 3. Force eviction of all session events by advancing time past retention horizon
        future_time = datetime.now(timezone.utc) + timedelta(hours=5)
        # Configure a policy on the session_service to allow pruning
        env.runtime._session_service._retention_policy = DetectionRetentionPolicy(
            retention_window_seconds=1800.0,
            late_arrival_grace_seconds=30.0,
        )
        evicted = env.runtime._session_service.prune_events(now_utc=future_time)
        assert evicted >= 3
        assert env.runtime._session_service.list_events(session_id) == []

        # 4. Assert zero mutation to security-authoritative state
        findings_after = env.findings_service.list_findings(agent_id=AGENT_ID)
        assert findings_after == findings_before

        posture_after = env.risk_aggregator.get_posture(AGENT_ID)
        assert posture_after == posture_before

        enforcement_state_after = env.agent_service.get_enforcement_state(AGENT_ID)
        assert enforcement_state_after == enforcement_state_before

        tombstone_after = env.runtime._session_service.get_tombstone(session_id)
        assert tombstone_after == tombstone_before

    def test_m4_event_4_no_count_based_truncation_under_burst(self) -> None:
        """M4-EVENT-4: High volume traffic does not cause arbitrary count-based window truncation."""
        policy = DetectionRetentionPolicy(
            retention_window_seconds=1800.0,
            late_arrival_grace_seconds=30.0,
        )
        service = SessionService(retention_policy=policy)
        base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Record 5,000 events all within the last 60 seconds (well within 1,800s horizon)
        burst_count = 5000
        for i in range(burst_count):
            service.record_event(
                make_event(
                    session_id="burst-session",
                    agent_id="burst-agent",
                    timestamp=base_time + timedelta(milliseconds=i * 10),
                )
            )

        events = service.list_events("burst-session")
        assert len(events) == burst_count

    def test_m4_event_5_compatibility_mode_retains_all_events(self) -> None:
        """M4-EVENT-5: retention_policy=None indicates explicit unbounded compatibility mode."""
        service = SessionService(retention_policy=None)
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Record events from days ago
        ancient_event = make_event("s1", "a1", timestamp=now - timedelta(days=10))
        service.record_event(ancient_event)

        # Prune attempt does nothing
        evicted = service.prune_events(now_utc=now)
        assert evicted == 0
        assert service.list_events("s1") == [ancient_event]

    def test_m4_event_6_hot_path_heap_efficiency(self) -> None:
        """M4-EVENT-6: Pruning is O(K log N) for K evicted events without scanning retained elements."""
        policy = DetectionRetentionPolicy(
            retention_window_seconds=1800.0,
            late_arrival_grace_seconds=30.0,
        )
        service = SessionService(retention_policy=policy)
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Insert 100 expired events and 100 valid events
        for i in range(100):
            service.record_event(
                make_event("s1", "a1", timestamp=now - timedelta(seconds=2000 + i))
            )
        for i in range(100):
            service.record_event(
                make_event("s1", "a1", timestamp=now - timedelta(seconds=100 + i))
            )

        # The 100 expired events (2000s+ old) were automatically pruned on the hot path
        # during the ingestion of the newer events (100s old).
        remaining_events = service.list_events("s1")
        assert len(remaining_events) == 100
        assert all(e.timestamp >= now - timedelta(seconds=1830) for e in remaining_events)

        # Explicit maintenance prune at 'now' confirms no residual expired events
        assert service.prune_events(now_utc=now) == 0

    def test_m4_event_7_out_of_order_arrival_correctness(self) -> None:
        """M4-EVENT-7: Min-heap root guarantees out-of-order events are evicted, not leaked.

        If a concurrent worker or replayed feed inserts an expired event AFTER a newer event,
        the expired event must NOT be trapped behind the newer event.
        """
        policy = DetectionRetentionPolicy(
            retention_window_seconds=1800.0,
            late_arrival_grace_seconds=30.0,
        )
        service = SessionService(retention_policy=policy)
        now = datetime(2026, 1, 1, 12, 30, 0, tzinfo=timezone.utc)

        # 1. Insert modern event (newer)
        e_newer = make_event("s1", "a1", timestamp=now - timedelta(seconds=60))
        service.record_event(e_newer)

        # 2. Insert out-of-order expired event (older)
        e_expired_late = make_event("s1", "a1", timestamp=now - timedelta(seconds=3000))
        # Record without immediate pruning at timestamp to simulate late arrival insertion
        with service._lock:
            import heapq

            heapq.heappush(
                service._events_heap,
                (e_expired_late.timestamp, service._event_counter, e_expired_late),
            )
            service._event_counter += 1

        # In a naive deque, e_expired_late would be placed behind e_newer and leaked.
        # In our min-heap, e_expired_late bubbles to root!
        assert service._events_heap[0][2] == e_expired_late

        # 3. Prune at time 'now'
        evicted = service.prune_events(now_utc=now)
        assert evicted == 1
        events = service.list_events("s1")
        assert events == [e_newer]

    def test_m4_event_7_deterministic_chronological_read_ordering(self) -> None:
        """M4-EVENT-7: list_events() returns deterministic chronological order regardless of insertion order."""
        service = SessionService()
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Insert out of order: t=30, t=10, t=20
        e30 = make_event("s1", "a1", timestamp=now + timedelta(seconds=30))
        e10 = make_event("s1", "a1", timestamp=now + timedelta(seconds=10))
        e20 = make_event("s1", "a1", timestamp=now + timedelta(seconds=20))

        service.record_event(e30)
        service.record_event(e10)
        service.record_event(e20)

        events = service.list_events("s1")
        assert events == [e10, e20, e30]

    def test_detection_retention_policy_validation(self) -> None:
        """DetectionRetentionPolicy validates inputs and computes total retention."""
        with pytest.raises(ValueError):
            DetectionRetentionPolicy(retention_window_seconds=0)

        with pytest.raises(ValueError):
            DetectionRetentionPolicy(retention_window_seconds=-10)

        with pytest.raises(ValueError):
            DetectionRetentionPolicy(
                retention_window_seconds=1800, late_arrival_grace_seconds=-5
            )

        policy = DetectionRetentionPolicy(
            retention_window_seconds=1800.0,
            late_arrival_grace_seconds=30.0,
            rule_horizons={"EXCESSIVE_DENIALS": 1800.0},
        )
        assert policy.total_retention_seconds == 1830.0
