"""ExecutionGrant — Domain entity for human-in-the-loop authorization resumption (ADR-031)."""

from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class GrantState(str, Enum):
    """Lifecycle states of an ExecutionGrant per ADR-031."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


ALLOWED_GRANT_TRANSITIONS: frozenset[tuple[GrantState, GrantState]] = frozenset(
    {
        (GrantState.PENDING, GrantState.APPROVED),
        (GrantState.PENDING, GrantState.REJECTED),
        (GrantState.PENDING, GrantState.EXPIRED),
        (GrantState.APPROVED, GrantState.CONSUMED),
    }
)


def _deep_freeze(val: Any) -> Any:
    """Recursively freeze mappings to mappingproxy, lists to tuples, and sets to frozensets."""
    if isinstance(val, (dict, MappingProxyType)):
        return MappingProxyType({k: _deep_freeze(v) for k, v in val.items()})
    if isinstance(val, (list, tuple)):
        return tuple(_deep_freeze(v) for v in val)
    if isinstance(val, (set, frozenset)):
        return frozenset(_deep_freeze(v) for v in val)
    return val


def _deep_unfreeze(val: Any) -> Any:
    """Recursively unfreeze mappingproxy to dict, tuples to lists for serialization."""
    if isinstance(val, (Mapping, MappingProxyType)):
        return {k: _deep_unfreeze(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_deep_unfreeze(v) for v in val]
    if isinstance(val, (set, frozenset)):
        return [_deep_unfreeze(v) for v in val]
    return val


class ExecutionGrant(BaseModel):
    """Bound authority token permitting a single execution attempt of a specific tool invocation.

    Invariants (ADR-031):
    1. Frozen Continuation: An approved grant is NOT a new authorization decision,
       but a frozen continuation of the evaluated authorization decision that produced it.
    2. Deep Immutability: execution_parameters cannot be mutated after creation or approval.
    3. Monotonic State Machine: Transitions follow ADR-031 state machine
       (PENDING -> APPROVED -> CONSUMED, PENDING -> REJECTED, PENDING -> EXPIRED).
    4. Execution Boundary: CONSUMED signifies exactly one authorized execution attempt,
       not guaranteed success of the tool execution.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    grant_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    tool_id: str = Field(min_length=1)
    execution_parameters: Mapping[str, Any] = Field(default_factory=dict)
    originating_audit_event_id: str = Field(min_length=1)
    risk_score: int = Field(ge=0)
    required_response: str = Field(min_length=1)
    enforcement_epoch: int = Field(ge=0)
    state: GrantState = Field(default=GrantState.PENDING)
    created_at: datetime
    expires_at: datetime
    approved_by: str | None = None
    consumed_at: datetime | None = None

    @field_validator("execution_parameters", mode="after")
    @classmethod
    def _freeze_parameters(cls, v: Any) -> Any:
        return _deep_freeze(v)

    @field_serializer("execution_parameters", when_used="always")
    def _serialize_parameters(self, v: Any) -> Any:
        return _deep_unfreeze(v)

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> "ExecutionGrant":
        """Controlled deep copy preserving immutability without global interpreter dispatch mutation."""
        if memo is None:
            memo = {}
        if id(self) in memo:
            return memo[id(self)]

        # ExecutionGrant is frozen and execution_parameters is already deeply frozen/immutable.
        # Construct a distinct instance with copied attributes for complete object isolation.
        copied = self.__class__.model_construct(
            grant_id=self.grant_id,
            session_id=self.session_id,
            agent_id=self.agent_id,
            tool_id=self.tool_id,
            execution_parameters=self.execution_parameters,
            originating_audit_event_id=self.originating_audit_event_id,
            risk_score=self.risk_score,
            required_response=self.required_response,
            enforcement_epoch=self.enforcement_epoch,
            state=self.state,
            created_at=self.created_at,
            expires_at=self.expires_at,
            approved_by=self.approved_by,
            consumed_at=self.consumed_at,
        )
        memo[id(self)] = copied
        return copied
