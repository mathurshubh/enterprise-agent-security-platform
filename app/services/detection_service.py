from collections import defaultdict
from datetime import datetime, timedelta, timezone
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
) -> str:
    """Return the stable identifier for one threshold crossing.

    Threshold detections evaluate the whole session history on every request, so a
    crossed threshold is re-derived by every later request. A deterministic identity
    lets the findings store recognise the repeat as the same evidence instead of
    recording a new finding each time, which would inflate cumulative risk while the
    session's actual behaviour is unchanged.
    """
    return str(
        uuid5(
            SESSION_FINDING_NAMESPACE,
            f"{rule_name}|{session_id}|{agent_id}|{threshold}",
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
        now_utc: datetime | None = None,
    ) -> list[Finding]:
        """Report agents whose cumulative denial count within the evaluation window reaches the threshold.

        Semantics (M4 Step 2C-A):
        - Scope: (session_id, agent_id)
        - Threshold: >= EXCESSIVE_DENIAL_THRESHOLD (3) cumulative DENY decisions
        - Evaluation: cumulative (intervening ALLOW or APPROVAL_REQUIRED decisions do not reset count)
        - Temporal window: sliding window of excessive_denials_window_seconds (default: 1800s / 30m)
        - Boundary: event.timestamp >= now - window is included, strictly older (<) is excluded
        """
        now = now_utc or datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self._excessive_denials_window_seconds)

        denied_events: dict[tuple[str, str], list[SessionEvent]] = defaultdict(list)

        for event in events:
            if event.decision == Decision.DENY and event.timestamp >= cutoff:
                denied_events[(event.session_id, event.agent_id)].append(event)

        findings: list[Finding] = []

        for (session_id, agent_id), session_denials in denied_events.items():
            if len(session_denials) < EXCESSIVE_DENIAL_THRESHOLD:
                continue

            findings.append(
                Finding(
                    finding_id=session_finding_id(
                        "EXCESSIVE_DENIALS",
                        session_id,
                        agent_id,
                        EXCESSIVE_DENIAL_THRESHOLD,
                    ),
                    session_id=session_id,
                    agent_id=agent_id,
                    rule_name="EXCESSIVE_DENIALS",
                    severity=Severity.MEDIUM,
                    description=(
                        f"Session contains {len(session_denials)} "
                        "denied actions"
                    ),
                )
            )

        return findings

    def registered_rule_names(self) -> set[str]:
        """Return a set of all session behavioral detection rule names."""
        return {"EXCESSIVE_DENIALS"}
