from collections import defaultdict
from uuid import uuid4

from app.models.audit_event import Decision
from app.models.finding import Finding, Severity
from app.models.session_event import SessionEvent


class DetectionService:
    def detect_excessive_denials(
        self,
        events: list[SessionEvent],
    ) -> list[Finding]:
        denied_events: dict[str, list[SessionEvent]] = defaultdict(list)

        for event in events:
            if event.decision == Decision.DENY:
                denied_events[event.session_id].append(event)

        findings: list[Finding] = []

        for session_id, session_denials in denied_events.items():
            if len(session_denials) < 3:
                continue

            findings.append(
                Finding(
                    finding_id=str(uuid4()),
                    session_id=session_id,
                    agent_id=session_denials[0].agent_id,
                    rule_name="EXCESSIVE_DENIALS",
                    severity=Severity.MEDIUM,
                    description=(
                        f"Session contains {len(session_denials)} "
                        "denied actions"
                    ),
                )
            )

        return findings
