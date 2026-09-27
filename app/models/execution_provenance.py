"""ExecutionProvenance — grant-derived execution identity for the isolation boundary (ADR-032)."""

from pydantic import BaseModel, ConfigDict, Field

from app.models.runtime_execution_grant import RuntimeExecutionGrant


class ExecutionProvenance(BaseModel):
    """The identity labels an authorized execution carries across the sandbox boundary.

    Constructed only from a verified ``RuntimeExecutionGrant``, so the sandbox receives
    provenance it can attribute without receiving the authority that produced it. The
    grant's ``signature`` deliberately has no representation here: the sandbox enforces
    a physical boundary and makes no security decision (ADR-032 §4.4), so it has no use
    for authority material and must not be in a position to serialize it into a child
    process payload or a diagnostic log.

    ``request_id`` is operational correlation rather than identity. It is carried
    alongside the three authoritative fields so the child payload can be tied back to
    the originating request without the sandbox consulting caller-supplied context.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    grant_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)

    @classmethod
    def from_grant(
        cls,
        grant: RuntimeExecutionGrant,
        request_id: str,
    ) -> "ExecutionProvenance":
        """Derive provenance from a grant the authority has already verified.

        The caller supplies only ``request_id``; every identity field comes from the
        grant, so there is no code path by which a caller's claim becomes provenance.
        """
        return cls(
            grant_id=grant.grant_id,
            agent_id=grant.agent_id,
            session_id=grant.session_id,
            request_id=request_id,
        )
