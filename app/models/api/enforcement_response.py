"""Management API representations of agent enforcement state (M2b).

Read-only governance visibility: current containment state and the history of how an
agent reached it. Exposing this does not give the management API role-based access
control — that remains finding H-2 and a separate milestone.
"""

from datetime import datetime

from pydantic import BaseModel


class EnforcementTransitionResponse(BaseModel):
    """One recorded change of an agent's enforcement state."""

    transition_id: str
    agent_id: str
    action: str
    actor: str
    reason: str
    previous_status: str
    new_status: str
    occurred_at: datetime
    trigger_session_id: str | None = None
    trigger_risk_level: str | None = None
    trigger_risk_score: int | None = None
    trigger_finding_ids: list[str] = []


class EnforcementStateResponse(BaseModel):
    """An agent's current enforcement state and how it got there."""

    agent_id: str
    status: str
    suspended_at: datetime | None = None
    suspension_reason: str | None = None
    enforcement_baseline_at: datetime | None = None
    last_transition_at: datetime | None = None
    transitions: list[EnforcementTransitionResponse] = []
