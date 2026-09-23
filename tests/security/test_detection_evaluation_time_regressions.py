"""Windowed detection answers a question about a moment the caller supplies.

`EXCESSIVE_DENIALS` reports denials inside a sliding window. That makes its result
a function of two things — the evidence, and the moment the window is measured
from. While the detector read that moment from the system clock, the second input
was invisible and uncontrolled:

    same events, asked at T        -> finding
    same events, asked at T + 1h   -> no finding

ADR-017 requires a forensic replay to produce the same findings as live analysis.
That cannot hold while the boundary moves on its own, so the moment is now an
explicit input. The live caller passes the timestamp of the event that triggered
the evaluation; a replay passes the timestamp of the event being replayed.

Replay equivalence for a windowed rule is **incremental temporal replay**: each
ordered event is evaluated at its own timestamp, carrying forward what preceding
evaluations produced. A single evaluation against the final retained history is
not equivalent and is not a replay — with a sliding window it can miss a crossing
that genuinely occurred, because the evidence has since aged out. The last test
below pins that distinction so it cannot be mistaken for an accepted contract.

Scope: this module is about the evaluation moment only. Finding identity and
occurrence semantics are unchanged here.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.audit_event import Decision
from app.models.session_event import SessionEvent
from app.services.detection_service import (
    EXCESSIVE_DENIAL_THRESHOLD,
    DetectionService,
)

ANCHOR = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def denial(offset_seconds: float, session_id: str = "eval-time") -> SessionEvent:
    return SessionEvent(
        session_id=session_id,
        agent_id="eval-agent",
        tool_id="unauthorized_tool",
        decision=Decision.DENY,
        timestamp=ANCHOR + timedelta(seconds=offset_seconds),
    )


def crossing_events(session_id: str = "eval-time") -> list[SessionEvent]:
    return [denial(i, session_id) for i in range(EXCESSIVE_DENIAL_THRESHOLD)]


@pytest.mark.security_invariant
def test_invariant_identical_events_and_time_produce_identical_results() -> None:
    """Determinism in the two inputs that decide the answer."""
    service = DetectionService()
    events = crossing_events()
    at = ANCHOR + timedelta(seconds=10)

    first = service.detect_excessive_denials(events, evaluation_time=at)
    second = service.detect_excessive_denials(events, evaluation_time=at)

    assert [f.finding_id for f in first] == [f.finding_id for f in second]
    assert len(first) == 1


@pytest.mark.security_invariant
def test_invariant_the_result_does_not_depend_on_the_system_clock() -> None:
    """The property the change exists for.

    `ANCHOR` is far enough in the past that every event here is many windows older
    than real time. A detector reading the clock would place all of them outside
    the window and report nothing; asked about the moment they actually occurred,
    the crossing is found. That gap between "now" and the supplied moment is
    exactly the live-versus-replay difference, and this asserts the answer follows
    the evidence rather than the clock.
    """
    service = DetectionService()
    window = service.excessive_denials_window_seconds
    assert (datetime.now(timezone.utc) - ANCHOR).total_seconds() > window * 10, (
        "the fixture must be far older than the window for this to mean anything"
    )

    findings = service.detect_excessive_denials(
        crossing_events(), evaluation_time=ANCHOR + timedelta(seconds=10)
    )

    assert len(findings) == 1


@pytest.mark.security_invariant
def test_invariant_the_detector_reads_no_clock() -> None:
    """Structural, because a behavioural test cannot distinguish a clock read
    that happens to agree with the supplied moment."""
    import inspect

    source = inspect.getsource(DetectionService.detect_excessive_denials)

    assert "datetime.now" not in source
    assert "utcnow" not in source


@pytest.mark.security_regression
def test_the_evaluation_moment_is_required() -> None:
    """A default would leave the clock-reading path reachable, and an omitted
    argument would silently reintroduce the non-determinism rather than fail."""
    service = DetectionService()

    with pytest.raises(TypeError):
        service.detect_excessive_denials(crossing_events())


@pytest.mark.security_regression
def test_the_window_boundary_is_deterministic() -> None:
    """Inclusive at the boundary, exclusive beyond it, decided by the supplied
    moment rather than by when the test happens to run."""
    service = DetectionService()
    window = service.excessive_denials_window_seconds
    at = ANCHOR + timedelta(seconds=window)

    on_boundary = service.detect_excessive_denials(
        crossing_events(), evaluation_time=at
    )
    just_past = service.detect_excessive_denials(
        crossing_events(), evaluation_time=at + timedelta(seconds=1)
    )

    assert on_boundary != [], "an event exactly on the boundary is included"
    assert just_past == [], "the same events one second later are outside it"


@pytest.mark.security_invariant
def test_invariant_incremental_replay_reproduces_live_detection() -> None:
    """Replay equivalence, as the contract defines it.

    Live evaluates after each event at that event's timestamp. A replay doing the
    same over the same ordered history must produce the same findings.
    """
    service = DetectionService()
    history = [denial(i * 600) for i in range(6)]

    def evaluate_incrementally() -> list[str]:
        produced: list[str] = []
        for index, event in enumerate(history):
            for finding in service.detect_excessive_denials(
                history[: index + 1], evaluation_time=event.timestamp
            ):
                if finding.finding_id not in produced:
                    produced.append(finding.finding_id)
        return produced

    live = evaluate_incrementally()
    replayed = evaluate_incrementally()

    assert live == replayed
    assert live != []


@pytest.mark.security_regression
def test_one_shot_evaluation_is_not_replay_equivalent() -> None:
    """Recorded so the cheaper approach is not mistaken for a replay.

    Evaluating once against the final history is not equivalent to live analysis:
    with a sliding window the early evidence has aged out by the final moment, so
    a crossing that genuinely occurred produces nothing.
    """
    service = DetectionService()
    window = service.excessive_denials_window_seconds
    history = crossing_events() + [denial(window * 2)]

    incremental = [
        finding.finding_id
        for index, event in enumerate(history)
        for finding in service.detect_excessive_denials(
            history[: index + 1], evaluation_time=event.timestamp
        )
    ]
    one_shot = service.detect_excessive_denials(
        history, evaluation_time=history[-1].timestamp
    )

    assert incremental != [], "the crossing did occur"
    assert one_shot == [], "a single final evaluation does not see it"


@pytest.mark.security_invariant
def test_invariant_the_runtime_evaluates_at_the_triggering_events_moment(
    build_runtime, security_workspace
) -> None:
    """The caller's side of the contract.

    Making the argument explicit only helps if the live caller supplies the right
    moment. A spy captures what the runtime actually passes: found by mutation,
    where substituting a clock read at the call site left every test in this
    module passing.
    """
    env = build_runtime(workspace=security_workspace)
    captured: list[datetime] = []
    real_detector = env.runtime._detection_service

    class CapturingDetector(DetectionService):
        def detect_excessive_denials(self, events, *, evaluation_time, **kwargs):
            captured.append(evaluation_time)
            return real_detector.detect_excessive_denials(
                events, evaluation_time=evaluation_time, **kwargs
            )

    env.runtime._detection_service = CapturingDetector()

    env.runtime.execute(
        session_id="eval-time-runtime",
        agent_id=env.agent_id,
        tool_id="file_read",
        resource="notes.txt",
    )

    recorded = env.session_service.list_events("eval-time-runtime")
    assert len(captured) == 1
    assert recorded != []
    assert captured[0] == recorded[-1].timestamp
