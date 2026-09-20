"""ExecutionReceipt — Immutable evidence of observed tool execution boundary traversal (NEW-003).

Invariants:
- N3-1 (Provenance): Derives identity and binding exclusively from the validated ExecutionGrant
  and verified execution context, never from tool-supplied strings.
- N3-7 (Diagnostic Safety): Captures controlled error_type and error_code,
  deliberately excluding raw exception messages.
- N3-10 (UTC Evidence Time): Durable timestamps are timezone-aware UTC.
"""

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExecutionStatus(str, Enum):
    """Lifecycle status of tool execution observed at the execution boundary."""

    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    INTERRUPTED = "INTERRUPTED"
    UNKNOWN = "UNKNOWN"


class ReconciliationReason(str, Enum):
    """Controlled taxonomy explaining why an execution was reconciled to UNKNOWN."""

    PROCESS_RESTART = "PROCESS_RESTART"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    WORKER_LOST = "WORKER_LOST"
    EVIDENCE_UNAVAILABLE = "EVIDENCE_UNAVAILABLE"


def compute_output_digest(output: Any) -> str | None:
    """Compute deterministic SHA-256 digest of canonicalizable tool output.

    Returns None if output is None or cannot be safely and deterministically canonicalized.
    Uses strict JSON formatting (allow_nan=False, sort_keys=True, compact separators).
    """
    if output is None:
        return None
    try:
        serialized = json.dumps(
            output,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    except (TypeError, ValueError):
        return None


class ExecutionReceipt(BaseModel):
    """Immutable record of observed execution facts.

    An ExecutionReceipt proves what the trusted execution boundary observed about a
    tool invocation. It is distinct from governance authorization (Decision.ALLOW)
    and authority grant consumption (GRANT_CONSUMED).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: str = Field(
        min_length=1, description="Unique identifier for this execution receipt."
    )
    grant_id: str = Field(
        min_length=1, description="Execution grant authorizing this execution."
    )
    session_id: str = Field(
        min_length=1, description="Session under which this execution was invoked."
    )
    agent_id: str = Field(
        min_length=1, description="Agent identity bound to the execution grant."
    )
    tool_id: str = Field(min_length=1, description="Target tool identifier.")
    binding_hash: str = Field(
        min_length=1, description="Canonical SHA-256 digest of the execution binding."
    )
    status: ExecutionStatus = Field(description="Observed execution lifecycle status.")

    # UTC Evidence Timestamps (must be timezone-aware)
    started_at: datetime = Field(
        description="UTC timestamp when the execution boundary was entered."
    )
    completed_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the tool execution completed (terminal observation).",
    )
    reconciled_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when reconciliation declared the outcome UNKNOWN.",
    )

    # Measured Performance (calculated via monotonic clock)
    duration_ms: int | None = Field(
        default=None,
        ge=0,
        description="Elapsed wall duration in milliseconds measured via monotonic clock.",
    )

    # Controlled Diagnostics (N3-7: raw error messages are excluded)
    error_type: str | None = Field(
        default=None,
        description="Python exception type name (e.g. FileNotFoundError, ToolExecutionError).",
    )
    error_code: str | None = Field(
        default=None,
        description="Controlled error code taxonomy (e.g. EXECUTION_TIMEOUT, TOOL_RESOURCE_NOT_FOUND).",
    )
    reconciliation_reason: ReconciliationReason | None = Field(
        default=None,
        description="Reason code if status was reconciled to UNKNOWN.",
    )

    # Deterministic Digest
    output_digest: str | None = Field(
        default=None,
        description="SHA-256 digest of canonical JSON output representation.",
    )

    @field_validator("started_at", "completed_at", "reconciled_at")
    @classmethod
    def _validate_utc_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("timestamp must be timezone-aware (UTC)")
            if value.utcoffset() != timezone.utc.utcoffset(value):
                raise ValueError("timestamp must be in UTC timezone")
        return value
