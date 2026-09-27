"""Bounded retention policy for in-memory execution evidence (ADR-032 §12)."""

from pydantic import BaseModel, ConfigDict, Field


class ExecutionEvidenceRetentionPolicy(BaseModel):
    """Capacity bound for retained terminal execution receipts.

    The domain contract is that retention is *bounded*; how many is a deployment
    decision. ``max_terminal_receipts`` therefore carries no default: a platform that
    knows nothing about a deployment's execution volume should not invent a capacity,
    and an absent bound is the dangerous state rather than a configured one.

    Only terminal receipts are subject to this bound. An open (``STARTED``) receipt is
    the reconciler's only input, so evicting one would convert a reconcilable unknown
    into a silently lost execution. Their accumulation is an operational signal about
    evidence health, not something retention should quietly absorb.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_terminal_receipts: int = Field(
        ge=1,
        description=(
            "Maximum number of terminal receipts retained in memory. Oldest-first by "
            "started_at once exceeded. A durable evidence store would replace eviction "
            "with retention; this policy is where that substitution happens."
        ),
    )
