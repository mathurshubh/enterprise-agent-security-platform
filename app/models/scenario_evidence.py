from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class IntentSource(str, Enum):
    """The origin of the tool invocation being evaluated."""

    DETERMINISTIC_SEQUENCE = "DETERMINISTIC_SEQUENCE"
    UNTRUSTED_LLM_PARSER = "UNTRUSTED_LLM_PARSER"


class ScenarioToolInvocation(BaseModel):
    """The concrete tool operation submitted to authorization."""

    model_config = ConfigDict(frozen=True)

    tool_id: str
    resource: str | None = None


class ScenarioRequestEvidence(BaseModel):
    """Request inputs and the untrusted intent parser boundary."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    execution_mode: str  # "TOOL_SEQUENCE" | "PROMPT"
    user_prompt: str | None = None
    tool_sequence: tuple[str, ...] = ()
    tool_invocation: ScenarioToolInvocation | None = None
    intent_source: IntentSource


class ScenarioAuthorizationCheck(BaseModel):
    """Immutable outcome of a single deterministic authorization check."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str    # Canonical display name: "Agent existence", "Tool existence", etc.
    key: str     # Domain field key: "agent_check", "tool_check", etc.
    status: str  # "passed" | "failed" | "not_evaluated"
    reason: str
    details: Mapping[str, str] = Field(default_factory=dict)

    @field_validator("details", mode="after")
    @classmethod
    def _freeze_details(cls, v: Any) -> Any:
        if isinstance(v, Mapping):
            return MappingProxyType(dict(v))
        return v

    @field_serializer("details")
    def _serialize_details(self, v: Mapping[str, str]) -> dict[str, str]:
        return dict(v)


class ScenarioAuthorizationEvidence(BaseModel):
    """Deterministic authorization outcome and ordered check collection."""

    model_config = ConfigDict(frozen=True)

    decision: str  # "ALLOW" | "DENY" | "APPROVAL_REQUIRED"
    reason: str
    checks: tuple[ScenarioAuthorizationCheck, ...] = ()


class ScenarioFindingSummary(BaseModel):
    """Bounded finding evidence excluding internal runtime payloads."""

    model_config = ConfigDict(frozen=True)

    finding_id: str
    rule_name: str
    severity: str
    description: str


class ScenarioDetectionEvidence(BaseModel):
    """Threat detection findings."""

    model_config = ConfigDict(frozen=True)

    findings: tuple[ScenarioFindingSummary, ...] = ()
    finding_count: int = 0


class ScenarioRiskEvidence(BaseModel):
    """Calculated risk posture."""

    model_config = ConfigDict(frozen=True)

    level: str  # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    score: int  # 0 to 100
    finding_count: int


class ScenarioResponseEvidence(BaseModel):
    """Response action and causal justification."""

    model_config = ConfigDict(frozen=True)

    action: str  # "MONITOR" | "ALERT" | "REQUIRE_APPROVAL" | "SUSPEND_AGENT"
    reason: str


class ScenarioAuditEvidence(BaseModel):
    """Direct correlation to append-only audit trail."""

    model_config = ConfigDict(frozen=True)

    event_id: str


class ScenarioFinalDecisionEvidence(BaseModel):
    """Final pipeline outcome."""

    model_config = ConfigDict(frozen=True)

    decision: str  # "ALLOW" | "DENY" | "APPROVAL_REQUIRED"


class ScenarioExecutionEvidence(BaseModel):
    """Authoritative security evidence across all pipeline phases.

    Optional fields represent unreached pipeline stages (e.g. boundary refusals).
    """

    model_config = ConfigDict(frozen=True)

    request: ScenarioRequestEvidence
    authorization: ScenarioAuthorizationEvidence | None = None
    detection: ScenarioDetectionEvidence | None = None
    risk: ScenarioRiskEvidence | None = None
    response: ScenarioResponseEvidence | None = None
    audit: ScenarioAuditEvidence | None = None
    final_decision: ScenarioFinalDecisionEvidence | None = None
    refusal_reason: str | None = None
