from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from app.models.audit_event import Decision
from app.models.detection_rule import DetectionRuleDescriptor
from app.models.finding import Finding, Severity
from app.models.session_event import AggregationScope, SessionEvent

EXCESSIVE_DENIAL_THRESHOLD = 3
DEFAULT_EXCESSIVE_DENIALS_WINDOW_SECONDS = 1800.0
EXCESSIVE_DENIALS_RULE_NAME = "EXCESSIVE_DENIALS"

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
    """Evaluates behavioral detection rules over authoritative horizon evidence (M4 Step 2C-A, Plane 2)."""

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

    def get_rule_descriptor(self, rule_name: str) -> DetectionRuleDescriptor:
        """Return the declarative horizon descriptor for a specific rule."""
        if rule_name == EXCESSIVE_DENIALS_RULE_NAME:
            return DetectionRuleDescriptor(
                name=EXCESSIVE_DENIALS_RULE_NAME,
                scope=AggregationScope.AGENT,
                horizon_seconds=self._excessive_denials_window_seconds,
            )
        raise KeyError(f"Unknown detection rule: '{rule_name}'")

    def get_rule_horizon(self, rule_name: str) -> float:
        """Return the declared evaluation horizon in seconds for a specific rule."""
        return self.get_rule_descriptor(rule_name).horizon_seconds

    def detect_excessive_denials(
        self,
        events: list[SessionEvent],
        *,
        evaluation_time: datetime,
        prior_findings: Sequence[Finding] = (),
        enforcement_epoch: int = 0,
    ) -> list[Finding]:
        """Report agents whose cumulative denial count within the evaluation window reaches the threshold.

        Semantics (M4 Step 2C-A, Plane 2):
        - Scope: AggregationScope.AGENT (aggregates denials across sessions for the same agent)
        - Threshold: >= EXCESSIVE_DENIAL_THRESHOLD (3) cumulative DENY decisions
        - Evaluation: cumulative (intervening ALLOW or APPROVAL_REQUIRED decisions do not reset count)
        - Evidence Stream: Evaluates ordered agent evidence provided by the authoritative detection horizon.
        """
        cutoff = evaluation_time - timedelta(
            seconds=self._excessive_denials_window_seconds
        )

        denied_events: dict[str, list[SessionEvent]] = defaultdict(list)

        for event in events:
            if (
                event.decision == Decision.DENY
                and cutoff <= event.timestamp <= evaluation_time
            ):
                denied_events[event.agent_id].append(event)

        findings: list[Finding] = []

        for agent_id, agent_denials in denied_events.items():
            if len(agent_denials) < EXCESSIVE_DENIAL_THRESHOLD:
                continue

            latest_session_id = agent_denials[-1].session_id

            evidence = self._crossing_evidence(
                agent_denials,
                prior_findings=prior_findings,
                session_id=latest_session_id,
                agent_id=agent_id,
                enforcement_epoch=enforcement_epoch,
            )

            all_same_session = all(
                e.session_id == agent_denials[0].session_id for e in agent_denials
            )
            description = (
                f"Session contains {len(agent_denials)} denied actions"
                if all_same_session
                else f"Agent contains {len(agent_denials)} denied actions across sessions"
            )

            findings.append(
                Finding(
                    finding_id=session_finding_id(
                        EXCESSIVE_DENIALS_RULE_NAME,
                        latest_session_id,
                        agent_id,
                        EXCESSIVE_DENIAL_THRESHOLD,
                        evidence,
                        enforcement_epoch,
                    ),
                    session_id=latest_session_id,
                    agent_id=agent_id,
                    rule_name=EXCESSIVE_DENIALS_RULE_NAME,
                    severity=Severity.MEDIUM,
                    description=description,
                    evidence_event_sequences=evidence,
                    enforcement_epoch=enforcement_epoch,
                )
            )

        return findings

    def _crossing_evidence(
        self,
        agent_denials: list[SessionEvent],
        *,
        prior_findings: Sequence[Finding],
        session_id: str,
        agent_id: str,
        enforcement_epoch: int,
    ) -> tuple[int, ...]:
        """Return the evidence identifying this crossing."""
        use_agent_seq = any(e.agent_sequence > 0 for e in agent_denials)
        if use_agent_seq:
            in_window = {
                e.agent_sequence for e in agent_denials if e.agent_sequence > 0
            }
        else:
            in_window = {e.sequence_number for e in agent_denials}

        for prior in prior_findings:
            if (
                prior.rule_name != EXCESSIVE_DENIALS_RULE_NAME
                or prior.agent_id != agent_id
                or prior.enforcement_epoch != enforcement_epoch
                or not prior.evidence_event_sequences
            ):
                continue
            if any(seq in in_window for seq in prior.evidence_event_sequences):
                return prior.evidence_event_sequences

        if use_agent_seq:
            ordered = sorted(agent_denials, key=lambda e: e.agent_sequence)
            return tuple(
                event.agent_sequence
                for event in ordered[:EXCESSIVE_DENIAL_THRESHOLD]
            )
        else:
            ordered = sorted(
                agent_denials, key=lambda e: (e.timestamp, e.sequence_number)
            )
            return tuple(
                event.sequence_number
                for event in ordered[:EXCESSIVE_DENIAL_THRESHOLD]
            )

    def registered_rule_names(self) -> set[str]:
        """Return a set of all session behavioral detection rule names."""
        return {EXCESSIVE_DENIALS_RULE_NAME}
