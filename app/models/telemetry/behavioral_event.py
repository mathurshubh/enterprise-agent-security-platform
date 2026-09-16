"""Canonical behavioral telemetry event envelope according to ADR-015."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.models.audit_event import Decision
from app.models.risk_assessment import RiskLevel
from app.models.telemetry.event_taxonomy import TelemetryEventType


def compute_parameter_hash(parameters: dict[str, Any] | None) -> str | None:
    """Compute a deterministic SHA-256 hash of canonicalized parameter key-value pairs.

    Parameters are sorted alphabetically by key and serialized to stable,
    whitespace-minimized JSON so that equivalent dictionaries with different key
    ordering produce identical hashes. Raw parameter values must never enter BehavioralEvent.
    """
    if parameters is None:
        return None
    canonical_json = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class BehavioralEvent(BaseModel):
    """Immutable, canonical behavioral telemetry event envelope according to ADR-015.

    Captures granular execution transitions and parameter hashes for stateful
    behavioral detection and forensic replay. Operates strictly within the
    Deterministic Platform Zone.

    Sensitive raw payloads (user prompts, model outputs, tool outputs) are
    prohibited to enforce data minimization.
    """

    model_config = ConfigDict(frozen=True)

    # Metadata Header
    event_id: str = Field(
        default_factory=lambda: f"bev-{uuid4()}",
        description="Unique identifier for the telemetry event.",
    )
    event_type: TelemetryEventType | str = Field(
        description="Categorized taxonomy event type string."
    )
    schema_version: str = Field(
        default="1.0",
        description="Semantic schema version.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of event creation.",
    )
    trace_id: str | None = Field(
        default=None,
        description="Distributed request/trace identifier (e.g. request_id).",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Multi-turn session or delegation correlation identifier.",
    )

    # Identity & Context Envelope (no invented defaults; strictly from trusted context)
    session_id: str = Field(description="Active execution session identifier.")
    agent_id: str = Field(description="Authenticated enterprise agent identifier.")
    tenant_id: str | None = Field(
        default=None,
        description="Enterprise tenant identifier if present in trusted context.",
    )
    caller_role: str | None = Field(
        default=None,
        description="Assigned RBAC role claim from trusted token context.",
    )
    principal: str | None = Field(
        default=None,
        description="Authenticated principal from trusted context.",
    )

    # Target & Resource Payload
    tool_id: str | None = Field(
        default=None,
        description="Target tool identifier.",
    )
    resource_target: str | None = Field(
        default=None,
        description="Cleaned, normalized target resource reference.",
    )
    capability_category: str | None = Field(
        default=None,
        description="Operational capability classification (e.g., filesystem).",
    )
    parameter_hash: str | None = Field(
        default=None,
        description="SHA-256 hash of canonicalized invocation parameters.",
    )

    # Evaluation & Outcome Envelope
    decision: Decision | str | None = Field(
        default=None,
        description="Evaluated or finalized security decision.",
    )
    risk_level: RiskLevel | str | None = Field(
        default=None,
        description="Assessed risk level at time of evaluation.",
    )
    execution_time_ms: int = Field(
        default=0,
        ge=0,
        description="Execution duration in milliseconds.",
    )
    error_code: str | None = Field(
        default=None,
        description="Error classification code if evaluation or execution failed.",
    )
