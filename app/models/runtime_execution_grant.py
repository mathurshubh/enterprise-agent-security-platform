"""RuntimeExecutionGrant — cryptographic authority to execute one ExecutionBinding (ADR-023)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.audit_event import Decision
from app.models.execution_binding import ExecutionBinding


class RuntimeExecutionGrant(BaseModel):
    """Signed, single-use, short-lived authority to execute exactly one binding.

    ``ExecutionBinding`` says *what* was authorized; a grant is the authority to
    execute it. Grants are issued only by ``ExecutionAuthority`` and only for a
    final ALLOW decision — ``decision`` is typed so no other value can be
    represented.

    Holding a grant object proves nothing by itself. ``DefaultToolExecutor`` trusts
    a grant only after the issuing authority verifies its signature, expiry and
    single-use status, and the requested operation matches ``binding`` exactly.

    Timestamps come from the issuing authority's monotonic clock and are meaningful
    only inside the issuing process. That is intentional: grants are never
    persisted and never cross a process boundary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    grant_id: str = Field(min_length=1)
    authority_id: str = Field(min_length=1)
    decision: Literal[Decision.ALLOW] = Decision.ALLOW
    binding: ExecutionBinding
    issued_at: float
    expires_at: float
    signature: str = Field(min_length=1)
