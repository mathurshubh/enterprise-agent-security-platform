"""Enforcement state and governance history for a registered agent (M2b).

Two distinct things are modelled here:

``AgentEnforcementState``
    The agent's *current* enforcement state: whether it is suspended, why, and the
    baseline from which findings still count toward enforcement. It is replaced
    wholesale on every transition.

``EnforcementTransition``
    One immutable record of a state change. ``AgentService`` keeps these as an
    append-only governance history, deliberately outside the state model, so the
    current state stays a small value object rather than a growing event log.

The authoritative status remains ``Agent.status``, which ``PolicyEngine`` already
evaluates. This module records why that status changed and who changed it.
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.agent import AgentStatus
from app.models.risk_assessment import RiskLevel


class EnforcementAction(str, Enum):
    """The state changes an agent's enforcement state can undergo."""

    SUSPEND = "SUSPEND"
    REINSTATE = "REINSTATE"


class EnforcementTrigger(BaseModel):
    """What caused an enforcement transition.

    Suspension is attributable: it records the session that produced the decision, the
    risk posture at the time, and the findings that constituted the evidence.
    """

    model_config = ConfigDict(frozen=True)

    session_id: str | None = None
    risk_level: RiskLevel | None = None
    risk_score: int | None = None
    finding_ids: tuple[str, ...] = ()


class EnforcementTransition(BaseModel):
    """An immutable record of one enforcement state change."""

    model_config = ConfigDict(frozen=True)

    transition_id: str
    agent_id: str
    action: EnforcementAction
    actor: str
    reason: str
    previous_status: AgentStatus
    new_status: AgentStatus
    trigger: EnforcementTrigger | None = None
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class AgentEnforcementState(BaseModel):
    """The current enforcement state of one agent."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    suspended_at: datetime | None = None
    suspension_reason: str | None = None
    # Reinstatement resets enforcement eligibility, not security history: findings
    # recorded before this moment remain evidence but no longer drive enforcement.
    enforcement_baseline_at: datetime | None = None
    last_transition_at: datetime | None = None
