from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from app.models.audit_event import Decision
from app.models.finding import Finding, Severity
from app.models.session_event import SessionEvent

EXCESSIVE_DENIAL_THRESHOLD = 3
DEFAULT_EXCESSIVE_DENIALS_WINDOW_SECONDS = 1800.0

# Stable namespace for deterministic session-detection finding identifiers.
SESSION_FINDING_NAMESPACE = uuid5(
    NAMESPACE_URL,
    "https://enterprise-agent-security-platform/findings/session",
)


def session_finding_id(
    rule_name: str,
    session_id: str,
    agent_id: str,
    threshold: int,
    evidence_sequences: tuple[int, ...] = (),
    enforcement_epoch: int = 0,
) -> str:
    """Return the identifier for one threshold crossing.

    Threshold detections evaluate the whole session history on every request, so a
    crossed threshold is re-derived by every later request. A deterministic identity
    lets the findings store recognise the repeat as the same evidence instead of
    recording a new finding each time, which would inflate cumulative risk while the
    session's actual behaviour is unchanged.

    Identity therefore names *which* crossing, not merely that a crossing happened:

    ``evidence_sequences``
        the canonical positions of the events that established the crossing, pinned
        when it was first reported. Recomputing them from the current window instead
        would slide continuously under sustained denials and manufacture a new
        identity on every request.
    ``enforcement_epoch``
        which enforcement lifecycle the crossing belongs to. A reinstatement ends the
        previous one: without this, a crossing re-established after reinstatement
        would reuse the superseded identity and produce no new evidence, leaving the
        agent unenforceable.
    """
    return str(
        uuid5(
            SESSION_FINDING_NAMESPACE,
            f"{rule_name}|{session_id}|{agent_id}|{threshold}"
            f"|{','.join(str(s) for s in evidence_sequences)}|{enforcement_epoch}",
        )
    )


class DetectionService:
    """Evaluates multi-event session behavioral detection rules (M4 Step 2C-A)."""

    def __init__(
        self,
        excessive_denials_window_seconds: float = DEFAULT_EXCESSIVE_DENIALS_WINDOW_SECONDS,
    ) -> None:
        if excessive_denials_window_seconds <= 0:
            raise ValueError("excessive_denials_window_seconds must be positive")
        self._excessive_denials_window_seconds = excessive_denials_window_seconds

    @property
    def excessive_denials_window_seconds(self) -> float:
        return self._excessive_denials_window_seconds

    def get_rule_horizon(self, rule_name: str) -> float:
        """Return the declared evaluation horizon in seconds for a specific rule."""
        if rule_name == "EXCESSIVE_DENIALS":
            return self._excessive_denials_window_seconds
        raise KeyError(f"Unknown detection rule: '{rule_name}'")

    def detect_excessive_denials(
        self,
        events: list[SessionEvent],
        *,
        evaluation_time: datetime,
        prior_findings: Sequence[Finding] = (),
        enforcement_epoch: int = 0,
    ) -> list[Finding]:
        """Report agents whose cumulative denial count within the evaluation window reaches the threshold.

        Semantics (M4 Step 2C-A):
        - Scope: (session_id, agent_id)
        - Threshold: >= EXCESSIVE_DENIAL_THRESHOLD (3) cumulative DENY decisions
        - Evaluation: cumulative (intervening ALLOW or APPROVAL_REQUIRED decisions do not reset count)
        - Temporal window: sliding window of excessive_denials_window_seconds (default: 1800s / 30m)
        - Boundary: event.timestamp >= evaluation_time - window is included, strictly older (<) is excluded

        ``evaluation_time`` is supplied by the caller and is never read from the
        system clock here. A windowed rule answers a question about a moment, and
        taking that moment from the clock makes the answer depend on when it was
        asked rather than on the evidence: the same events evaluated later fall
        outside the window and yield a different result. ADR-017 requires a replay
        to produce the same findings as live analysis, which cannot hold while the
        boundary moves on its own. The live caller passes the timestamp of the event
        that triggered the evaluation; a replay passes the timestamp of the event
        being replayed.

        Required rather than defaulted: a default would leave the clock-reading path
        reachable, and a caller that omitted the argument would silently reintroduce
        the non-determinism instead of failing.

        ``prior_findings`` are read-only input, never state this service keeps. They
        are what lets a re-derivation be told apart from a new crossing:

            same epoch, any pinned evidence still in window  -> the same crossing
            all pinned evidence aged out                     -> re-arm
            epoch changed                                    -> re-arm
            re-armed and threshold met again                 -> a new crossing

        Without them the detector cannot know it already reported a crossing, and
        the only identity available describes the scope rather than the occurrence.

        ``enforcement_epoch`` must be evaluated at ``evaluation_time`` by the caller,
        not taken as the agent's current epoch, or an event from before a
        reinstatement would derive one identity live and a different one on replay.
        """
        cutoff = evaluation_time - timedelta(seconds=self._excessive_denials_window_seconds)

        denied_events: dict[tuple[str, str], list[SessionEvent]] = defaultdict(list)

        for event in events:
            if event.decision == Decision.DENY and event.timestamp >= cutoff:
                denied_events[(event.session_id, event.agent_id)].append(event)

        findings: list[Finding] = []

        for (session_id, agent_id), session_denials in denied_events.items():
            if len(session_denials) < EXCESSIVE_DENIAL_THRESHOLD:
                continue

            evidence = self._crossing_evidence(
                session_denials,
                prior_findings=prior_findings,
                session_id=session_id,
                agent_id=agent_id,
                enforcement_epoch=enforcement_epoch,
            )

            findings.append(
                Finding(
                    finding_id=session_finding_id(
                        "EXCESSIVE_DENIALS",
                        session_id,
                        agent_id,
                        EXCESSIVE_DENIAL_THRESHOLD,
                        evidence,
                        enforcement_epoch,
                    ),
                    session_id=session_id,
                    agent_id=agent_id,
                    rule_name="EXCESSIVE_DENIALS",
                    severity=Severity.MEDIUM,
                    description=(
                        f"Session contains {len(session_denials)} "
                        "denied actions"
                    ),
                    evidence_event_sequences=evidence,
                    enforcement_epoch=enforcement_epoch,
                )
            )

        return findings

    def _crossing_evidence(
        self,
        session_denials: list[SessionEvent],
        *,
        prior_findings: Sequence[Finding],
        session_id: str,
        agent_id: str,
        enforcement_epoch: int,
    ) -> tuple[int, ...]:
        """Return the evidence identifying this crossing.

        An active crossing keeps the evidence it was first reported with, so every
        later request in the session re-derives the same identity. It stays active
        while any of that evidence is still inside the window and the enforcement
        epoch has not moved on; once neither holds, the rule re-arms and the next
        crossing is identified by its own evidence.

        The evidence is the earliest denials in the window rather than all of them,
        because the full set grows with every request while the crossing does not.
        """
        in_window = {event.sequence_number for event in session_denials}

        for prior in prior_findings:
            if (
                prior.rule_name != "EXCESSIVE_DENIALS"
                or prior.session_id != session_id
                or prior.agent_id != agent_id
                or prior.enforcement_epoch != enforcement_epoch
                or not prior.evidence_event_sequences
            ):
                continue
            if any(seq in in_window for seq in prior.evidence_event_sequences):
                return prior.evidence_event_sequences

        ordered = sorted(session_denials, key=lambda e: (e.timestamp, e.sequence_number))
        return tuple(
            event.sequence_number
            for event in ordered[:EXCESSIVE_DENIAL_THRESHOLD]
        )

    def registered_rule_names(self) -> set[str]:
        """Return a set of all session behavioral detection rule names."""
        return {"EXCESSIVE_DENIALS"}
