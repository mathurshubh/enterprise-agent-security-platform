"""Unit tests for BehavioralEvent model and parameter hashing according to ADR-015."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from app.models.audit_event import Decision
from app.models.risk_assessment import RiskLevel
from app.models.telemetry.behavioral_event import (
    BehavioralEvent,
    compute_parameter_hash,
)
from app.models.telemetry.event_taxonomy import EventDomain, TelemetryEventType


def test_behavioral_event_creation_minimal() -> None:
    event = BehavioralEvent(
        event_type=TelemetryEventType.TOOL_INVOCATION_REQUESTED,
        session_id="sess-123",
        agent_id="agent-1",
    )

    assert event.event_id.startswith("bev-")
    assert event.event_type == TelemetryEventType.TOOL_INVOCATION_REQUESTED
    assert event.schema_version == "1.0"
    assert event.session_id == "sess-123"
    assert event.agent_id == "agent-1"
    assert event.tenant_id is None
    assert event.principal is None
    assert event.caller_role is None
    assert event.trace_id is None
    assert event.correlation_id is None
    assert event.tool_id is None
    assert event.resource_target is None
    assert event.parameter_hash is None
    assert event.decision is None
    assert event.risk_level is None
    assert event.execution_time_ms == 0
    assert event.error_code is None


def test_behavioral_event_immutability() -> None:
    event = BehavioralEvent(
        event_type=TelemetryEventType.SECURITY_AUTHORIZATION_CHECKED,
        session_id="sess-1",
        agent_id="agent-1",
    )

    with pytest.raises(ValidationError):
        event.session_id = "sess-mutated"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        event.decision = Decision.ALLOW  # type: ignore[misc]


def test_compute_parameter_hash_deterministic() -> None:
    dict_a = {"b": 2, "a": 1, "c": {"nested_y": 20, "nested_x": 10}}
    dict_b = {"a": 1, "c": {"nested_x": 10, "nested_y": 20}, "b": 2}

    hash_a = compute_parameter_hash(dict_a)
    hash_b = compute_parameter_hash(dict_b)

    assert hash_a is not None
    assert hash_a == hash_b

    # Verify matching manual SHA-256 calculation
    expected_json = json.dumps(dict_a, sort_keys=True, separators=(",", ":"))
    expected_hash = hashlib.sha256(expected_json.encode("utf-8")).hexdigest()
    assert hash_a == expected_hash


def test_compute_parameter_hash_edge_cases() -> None:
    assert compute_parameter_hash(None) is None
    empty_hash = compute_parameter_hash({})
    assert empty_hash == hashlib.sha256(b"{}").hexdigest()


def test_tenant_and_principal_not_invented() -> None:
    event = BehavioralEvent(
        event_type=TelemetryEventType.GOVERNANCE_DECISION_FINALIZED,
        session_id="sess-99",
        agent_id="agent-99",
    )
    assert event.tenant_id is None
    assert event.principal is None


def test_event_taxonomy_domains() -> None:
    assert EventDomain.AGENT_LIFECYCLE == "AGENT_LIFECYCLE"
    assert EventDomain.TOOL_INVOCATION == "TOOL_INVOCATION"
    assert EventDomain.SECURITY_EVALUATION == "SECURITY_EVALUATION"
    assert EventDomain.GOVERNANCE_ACTION == "GOVERNANCE_ACTION"

    assert TelemetryEventType.TOOL_INVOCATION_REQUESTED == "TOOL_INVOCATION.INVOCATION_REQUESTED"
    assert TelemetryEventType.SECURITY_AUTHORIZATION_CHECKED == "SECURITY_EVALUATION.AUTHORIZATION_CHECKED"
    assert TelemetryEventType.GOVERNANCE_DECISION_FINALIZED == "GOVERNANCE_ACTION.DECISION_FINALIZED"


def test_behavioral_event_full_payload_serialization() -> None:
    event = BehavioralEvent(
        event_type=TelemetryEventType.GOVERNANCE_DECISION_FINALIZED,
        session_id="sess-42",
        agent_id="agent-sec",
        tenant_id="tenant-corp",
        caller_role="AGENT",
        principal="spiffe://corp/agent-sec",
        tool_id="file_read",
        resource_target="workspace/report.txt",
        parameter_hash=compute_parameter_hash({"path": "workspace/report.txt"}),
        decision=Decision.ALLOW,
        risk_level=RiskLevel.LOW,
        execution_time_ms=12,
        error_code=None,
    )

    data = event.model_dump()
    assert data["session_id"] == "sess-42"
    assert data["tenant_id"] == "tenant-corp"
    assert data["principal"] == "spiffe://corp/agent-sec"
    assert data["decision"] == "ALLOW"
    assert data["risk_level"] == "LOW"
    assert data["execution_time_ms"] == 12

    json_str = event.model_dump_json()
    reconstructed = BehavioralEvent.model_validate_json(json_str)
    assert reconstructed == event
