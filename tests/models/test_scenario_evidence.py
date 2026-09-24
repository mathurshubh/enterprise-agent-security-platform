import pytest
from pydantic import ValidationError

from app.models.scenario_evidence import (
    IntentSource,
    ScenarioAuditEvidence,
    ScenarioAuthorizationCheck,
    ScenarioAuthorizationEvidence,
    ScenarioDetectionEvidence,
    ScenarioExecutionEvidence,
    ScenarioFinalDecisionEvidence,
    ScenarioFindingSummary,
    ScenarioRequestEvidence,
    ScenarioResponseEvidence,
    ScenarioRiskEvidence,
    ScenarioToolInvocation,
)
from app.models.scenario_execution_result import ScenarioExecutionResult


def test_scenario_evidence_immutability():
    """Verify all evidence models are frozen and immutable."""
    check = ScenarioAuthorizationCheck(
        name="Tool existence",
        key="tool_check",
        status="passed",
        reason="Tool exists in registry",
        details={"tool_id": "file_read"},
    )
    with pytest.raises(ValidationError):
        check.status = "failed"

    # Verify details mapping is frozen against alias mutation
    producer_dict = {"tool_id": "file_read"}
    check_with_alias = ScenarioAuthorizationCheck(
        name="Tool existence",
        key="tool_check",
        status="passed",
        reason="Tool exists in registry",
        details=producer_dict,
    )
    producer_dict["tool_id"] = "tampered"
    assert check_with_alias.details["tool_id"] == "file_read"

    with pytest.raises(TypeError):
        check_with_alias.details["new_key"] = "tampered"  # type: ignore[index]


def test_scenario_execution_result_properties_and_refusal_fidelity():
    """Verify single source of truth: properties read from evidence without default fallbacks."""
    # 1. Complete execution evidence
    evidence = ScenarioExecutionEvidence(
        request=ScenarioRequestEvidence(
            agent_id="agent-1",
            execution_mode="TOOL_SEQUENCE",
            tool_sequence=("file_read",),
            tool_invocation=ScenarioToolInvocation(tool_id="file_read", resource="safe.txt"),
            intent_source=IntentSource.DETERMINISTIC_SEQUENCE,
        ),
        authorization=ScenarioAuthorizationEvidence(
            decision="ALLOW",
            reason="All 6 checks passed",
            checks=(
                ScenarioAuthorizationCheck(
                    name="Agent existence",
                    key="agent_check",
                    status="passed",
                    reason="Agent is registered",
                ),
            ),
        ),
        detection=ScenarioDetectionEvidence(
            findings=(
                ScenarioFindingSummary(
                    finding_id="f-1",
                    rule_name="PROMPT_INJECTION",
                    severity="HIGH",
                    description="Detected injection attempt",
                ),
            ),
            finding_count=1,
        ),
        risk=ScenarioRiskEvidence(
            level="HIGH",
            score=75,
            finding_count=1,
        ),
        response=ScenarioResponseEvidence(
            action="SUSPEND_AGENT",
            reason="HIGH risk triggers suspension",
        ),
        audit=ScenarioAuditEvidence(
            event_id="evt-789",
        ),
        final_decision=ScenarioFinalDecisionEvidence(
            decision="DENY",
        ),
    )

    result = ScenarioExecutionResult(
        passed=True,
        mismatches=(),
        evidence=evidence,
    )

    assert result.authorization_decision == "ALLOW"
    assert result.final_decision == "DENY"
    assert result.observed_decision == "DENY"
    assert result.observed_response == "SUSPEND_AGENT"
    assert result.observed_risk_level == "HIGH"
    assert result.observed_findings == ["PROMPT_INJECTION"]
    assert result.evidence.audit.event_id == "evt-789"
    assert result.evidence.request.intent_source == IntentSource.DETERMINISTIC_SEQUENCE

    # 2. Refusal execution evidence (e.g. boundary refusal before authorization)
    refusal_evidence = ScenarioExecutionEvidence(
        request=ScenarioRequestEvidence(
            agent_id="agent-intruder",
            execution_mode="TOOL_SEQUENCE",
            tool_sequence=("file_read",),
            intent_source=IntentSource.DETERMINISTIC_SEQUENCE,
        ),
        authorization=None,
        detection=None,
        risk=None,
        response=None,
        audit=ScenarioAuditEvidence(event_id="evt-refusal-1"),
        final_decision=None,
        refusal_reason="SESSION_BINDING_INVALID",
    )

    refusal_result = ScenarioExecutionResult(
        passed=False,
        mismatches=("boundary refusal",),
        evidence=refusal_evidence,
    )

    # CRITICAL: Missing authorization MUST be None, never defaulted to "DENY"
    assert refusal_result.authorization_decision is None
    assert refusal_result.final_decision is None
    assert refusal_result.observed_decision is None
    assert refusal_result.observed_response is None
    assert refusal_result.observed_risk_level is None
    assert refusal_result.observed_findings == []
    assert refusal_result.evidence.refusal_reason == "SESSION_BINDING_INVALID"
    assert refusal_result.evidence.audit.event_id == "evt-refusal-1"


def test_scenario_execution_evidence_serialization():
    """Verify ScenarioExecutionEvidence serializes and deserializes cleanly."""
    evidence = ScenarioExecutionEvidence(
        request=ScenarioRequestEvidence(
            agent_id="agent-1",
            execution_mode="PROMPT",
            user_prompt="Read file test.txt",
            intent_source=IntentSource.UNTRUSTED_LLM_PARSER,
        ),
        authorization=ScenarioAuthorizationEvidence(
            decision="DENY",
            reason="Unauthorized tool",
            checks=(
                ScenarioAuthorizationCheck(
                    name="Approved tool (RBAC)",
                    key="approved_tool_check",
                    status="failed",
                    reason="Tool not approved for agent",
                    details={"tool_id": "file_write"},
                ),
            ),
        ),
        detection=ScenarioDetectionEvidence(findings=(), finding_count=0),
        risk=ScenarioRiskEvidence(level="LOW", score=0, finding_count=0),
        response=ScenarioResponseEvidence(action="MONITOR", reason="LOW risk"),
        audit=ScenarioAuditEvidence(event_id="evt-ser-1"),
        final_decision=ScenarioFinalDecisionEvidence(decision="DENY"),
    )

    dumped = evidence.model_dump()
    assert dumped["request"]["intent_source"] == "UNTRUSTED_LLM_PARSER"
    assert dumped["authorization"]["checks"][0]["status"] == "failed"
    assert dumped["audit"]["event_id"] == "evt-ser-1"

    restored = ScenarioExecutionEvidence.model_validate(dumped)
    assert restored.request.intent_source == IntentSource.UNTRUSTED_LLM_PARSER
    assert restored.authorization.checks[0].details["tool_id"] == "file_write"
