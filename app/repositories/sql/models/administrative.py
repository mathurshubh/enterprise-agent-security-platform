"""Relational models for the administrative lifecycle plane (ADR-030 L.3, ADR-024 A.6/A.8)."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.sql.base import Base

_ADMINISTRATIVE_STATES = "'REGISTERED', 'ACTIVE', 'DISABLED'"
_ACTOR_TYPES = "'human', 'system', 'runtime'"


class AgentAdministrativeStateModel(Base):
    """Authoritative administrative lifecycle state for one agent.

    The agent's identity record carries no lifecycle state (AP.1); this table is the
    authority. A missing row is not ``REGISTERED`` -- it is an administrative state that
    cannot be established, which L.10 reports as ``ADMINISTRATIVE_STATE_UNAVAILABLE``.

    That distinction is only meaningful if a missing row is genuinely impossible for a
    registered agent, which is why registration commits this row and the ``agents`` row in
    one transaction (AP.3, and the composition decision recorded in migration 0010).
    """

    __tablename__ = "agent_administrative_state"
    __table_args__ = (
        CheckConstraint(
            f"state IN ({_ADMINISTRATIVE_STATES})",
            name="chk_agent_administrative_state_value",
        ),
        # Registration commits version 1, so 0 is not a representable stored state. If it
        # were, a stored row and an absent one would again be indistinguishable -- the
        # ambiguity AP.1 removed from ``Agent.status``.
        CheckConstraint(
            "administrative_version >= 1",
            name="chk_agent_administrative_version_positive",
        ),
    )

    agent_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("agents.agent_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    administrative_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_transition_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AgentAdministrativeTransitionModel(Base):
    """Immutable ledger record of one administrative lifecycle change (ADR-024 A.8).

    Both transition history and authoritative lifecycle evidence: a committed transition
    is recorded once, here, and never duplicated into ``audit_events``.
    """

    __tablename__ = "agent_administrative_transitions"
    __table_args__ = (
        # One transition per version per agent. A duplicate would mean two records claiming
        # the same position in the chain, which is what makes the chain checkable at all.
        UniqueConstraint(
            "agent_id",
            "administrative_version_after",
            name="uq_agent_administrative_version_after",
        ),
        CheckConstraint(
            f"new_state IN ({_ADMINISTRATIVE_STATES})",
            name="chk_administrative_transition_new_state",
        ),
        CheckConstraint(
            f"previous_state IS NULL OR previous_state IN ({_ADMINISTRATIVE_STATES})",
            name="chk_administrative_transition_previous_state",
        ),
        CheckConstraint(
            f"actor_type IN ({_ACTOR_TYPES})",
            name="chk_administrative_transition_actor_type",
        ),
        # The version advances by exactly one. Expressed in the schema because the ledger
        # is evidence: a row that advanced by more would be unverifiable afterwards.
        CheckConstraint(
            "administrative_version_after = administrative_version_before + 1",
            name="chk_administrative_transition_version_advance",
        ),
        Index(
            "idx_administrative_transitions_agent_time", "agent_id", "occurred_at"
        ),
    )

    transition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("agents.agent_id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    # Structured actor: type and identity are never one overloaded string (A.8).
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_state: Mapped[str] = mapped_column(String(32), nullable=False)
    administrative_version_before: Mapped[int] = mapped_column(BigInteger, nullable=False)
    administrative_version_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Mandatory (A.8). There is no unattributed administrative transition.
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class AdministrativeAuditEventModel(Base):
    """Refused administrative attempts (ADR-028 §6, ADR-034 §8).

    Deliberately holds **no foreign key** to ``agents`` or to either lifecycle plane.
    ``UNKNOWN_AGENT`` is one of the refusals this record exists for, so a foreign key
    would make the evidence unrecordable exactly when it matters. Constraints express
    intra-record validity only, and interpreting a row requires no join.
    """

    __tablename__ = "administrative_audit_events"
    __table_args__ = (
        CheckConstraint(
            f"actor_type IN ({_ACTOR_TYPES})",
            name="chk_administrative_audit_actor_type",
        ),
        CheckConstraint(
            f"observed_state IS NULL OR observed_state IN ({_ADMINISTRATIVE_STATES})",
            name="chk_administrative_audit_observed_state",
        ),
        Index("idx_administrative_audit_agent_time", "agent_id", "occurred_at"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # A recorded identifier, not a reference. Meaningful for an agent that never existed.
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    attempted_action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    refusal_code: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    observed_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


__all__: list[Any] = [
    "AdministrativeAuditEventModel",
    "AgentAdministrativeStateModel",
    "AgentAdministrativeTransitionModel",
]
