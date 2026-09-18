from collections import defaultdict
from uuid import NAMESPACE_URL, uuid5

from app.models.audit_event import Decision
from app.models.finding import Finding, Severity
from app.models.session_event import SessionEvent

EXCESSIVE_DENIAL_THRESHOLD = 3

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
    def detect_excessive_denials(
        self,
        events: list[SessionEvent],
    ) -> list[Finding]:
        """Report sessions whose denial count has reached the threshold.

        The returned finding carries the identity of the threshold crossing, so
        recording it more than once is a no-op for the findings store.
        """
        denied_events: dict[str, list[SessionEvent]] = defaultdict(list)

        for event in events:
            if event.decision == Decision.DENY:
                denied_events[event.session_id].append(event)

        findings: list[Finding] = []

        for session_id, session_denials in denied_events.items():
            if len(session_denials) < EXCESSIVE_DENIAL_THRESHOLD:
                continue

            agent_id = session_denials[0].agent_id

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
