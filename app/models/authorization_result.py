from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)

from app.models.audit_event import Decision


class AuthorizationCheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"


class AuthorizationCheck(BaseModel):
    """The immutable outcome of a single deterministic authorization check.

    ``details`` is held as a read-only mapping to prevent in-place mutation, and
    isolated from any mutable dictionary supplied by the producer.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    status: AuthorizationCheckStatus
    reason: str
    details: Mapping[str, str] = Field(default_factory=dict)

    @field_validator("details", mode="after")
    @classmethod
    def _freeze_mapping(cls, v: Any) -> Any:
        if isinstance(v, Mapping):
            return MappingProxyType(dict(v))
        return v

    @field_serializer("details")
    def _serialize_details(self, v: Mapping[str, str]) -> dict[str, str]:
        return dict(v)


def not_evaluated_check(skipped_after: str) -> AuthorizationCheck:
    """Return a standardized check representing a fail-closed skipped check."""
    return AuthorizationCheck(
        status=AuthorizationCheckStatus.NOT_EVALUATED,
        reason="Skipped due to prior check failure",
        details={"skipped_after": skipped_after},
    )


class AuthorizationResult(BaseModel):
    """Immutable structured evidence for an authorization evaluation.

    In accordance with the PR #169 boundary:
    ``decision`` represents strictly what authorization concluded before
    detection, risk, and response actions. It is never rewritten by
    downstream pipeline stages.

    All check fields are always present. Checks skipped due to fail-closed
    short-circuiting at an earlier boundary are explicitly recorded as
    ``NOT_EVALUATED``.
    """

    model_config = ConfigDict(frozen=True)

    decision: Decision
    agent_id: str
    tool_id: str
    resource: str | None = None

    # Checks in deterministic evaluation order:
    agent_check: AuthorizationCheck
    tool_check: AuthorizationCheck
    approved_tool_check: AuthorizationCheck
    status_check: AuthorizationCheck
    risk_tier_check: AuthorizationCheck
    resource_check: AuthorizationCheck

    reason: str
