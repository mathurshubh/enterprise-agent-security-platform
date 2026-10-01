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
    tool_id: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    implementation_id: str = Field(min_length=1)

    @classmethod
    def from_grant(
        cls,
        grant: RuntimeExecutionGrant,
        request_id: str,
        implementation_id: str,
    ) -> "ExecutionProvenance":
        """Derive provenance from a grant the authority has already verified.

        The caller supplies ``request_id`` and the ``implementation_id`` the registration
        declared; the rest comes from the grant, so there is no code path by which a
        caller's claim becomes an authorization fact.

        ``implementation_id`` cannot come from the grant because the grant authorizes a
        tool version, not a packaged implementation — F-05 established those as separate
        namespaces, neither derivable from the other.

        Provenance is descriptive execution context, not authority. The child must never
        read these fields to select an implementation or to override its
        ``ToolExecutionDescriptor``; the authoritative path remains grant → descriptor →
        sandbox.
        """
        return cls(
            grant_id=grant.grant_id,
            agent_id=grant.agent_id,
            session_id=grant.session_id,
            request_id=request_id,
            tool_id=grant.binding.tool_id,
            tool_version=grant.binding.tool_version,
            implementation_id=implementation_id,
        )
