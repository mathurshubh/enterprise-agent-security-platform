from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.watermark import UNASSIGNED_SEQUENCE


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingCategory(str, Enum):
    PROMPT_INJECTION = "PROMPT_INJECTION"
    DATA_EXFILTRATION = "DATA_EXFILTRATION"
    PRIVILEGE_ESCALATION = "PRIVILEGE_ESCALATION"
    UNAUTHORIZED_TOOL = "UNAUTHORIZED_TOOL"
    SENSITIVE_FILE_ACCESS = "SENSITIVE_FILE_ACCESS"
    BROWSER_ABUSE = "BROWSER_ABUSE"
    SECRET_LEAKAGE = "SECRET_LEAKAGE"
    MULTI_STEP_ATTACK = "MULTI_STEP_ATTACK"
    UNKNOWN = "UNKNOWN"


class FindingStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class Finding(BaseModel):
    """Derived evidence of an observed security pattern.

    The record is **frozen**. ADR-017 requires that "once generated, a Behavioral
    Finding is immutable... must never be modified in place", and ADR-029 section 6
    requires the same of the derived occurrence evidence a finding carries: the
    artifact that decides whether a crossing is still the same one must not be
    rewritten by the evaluation asking the question.

    Neither was enforced. ``FindingsService.list_findings`` returns the stored records,
    so any caller could edit recorded evidence, and nothing named like a mutator had to
    exist for that to be possible.

    Changing a finding still works through ``model_copy``, which the store already uses
    to assign ``evidence_sequence`` and ``recorded_at`` on persistence; it produces a
    new record rather than editing the stored one.
    """

    model_config = ConfigDict(frozen=True)

    finding_id: str
    session_id: str
    agent_id: str
    rule_id: str = ""
    rule_name: str
    severity: Severity
    category: FindingCategory = FindingCategory.UNKNOWN
    status: FindingStatus = FindingStatus.OPEN
    description: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    recorded_at: datetime | None = None
    # The evidence this finding was derived from, and the enforcement lifecycle it
    # belongs to. A threshold crossing is re-derived by every later request in the
    # session, so the detector has to be able to tell "the crossing I already
    # reported" from "a new crossing". It reads that back from the finding rather
    # than recomputing it, because the set of in-window events slides continuously
    # while the underlying crossing does not.
    evidence_event_sequences: tuple[int, ...] = ()
    enforcement_epoch: int = Field(default=0, ge=0)
    evidence_sequence: int = Field(
        default=UNASSIGNED_SEQUENCE,
        ge=0,
        description=(
            "Monotonic 1-based sequence number per agent assigned exclusively "
            "by FindingsService upon persistence. 0 indicates UNASSIGNED candidate."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _default_rule_id_to_rule_name(cls, data: Any) -> Any:
        """Supply ``rule_id`` from ``rule_name`` when the caller omits it.

        Applied during validation rather than afterwards. The previous form assigned
        to ``self.rule_id`` in ``model_post_init``, which is an in-place mutation of a
        constructed finding and therefore incompatible with making the record
        immutable (ADR-017: a finding "must never be modified in place"). Defaulting
        an absent value at construction and editing a built record are different
        operations; only the first is compatible with that requirement.

        Behaviour is unchanged, including the cases the old form left alone: an
        explicit ``rule_id`` still wins, an empty string is still treated as absent,
        and ``model_copy`` still bypasses defaulting entirely because it does not
        re-validate.
        """
        if isinstance(data, dict) and not data.get("rule_id"):
            return {**data, "rule_id": data.get("rule_name", "")}
        return data

