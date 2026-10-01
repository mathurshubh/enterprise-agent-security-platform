"""Execution evidence must be attributable to the subject the grant was issued for.

The production caller passes no runtime context:

    app/services/agent_runtime_service.py
        output = self._executor.execute_descriptor(
            descriptor, parameters, grant=runtime_result.authorization
        )

The executor answered that by fabricating one, and then read identity out of the
thing it had just invented:

    effective_context = context or RuntimeContext(
        session_id="unspecified", authenticated_agent="unspecified", ...
    )
    session_id = effective_context.session_id
    agent_id = effective_context.authenticated_agent

So every sandboxed execution on the production path recorded a receipt whose
session and agent were the literal string ``"unspecified"``. The real
``grant_id`` was preserved, so the execution was not wholly untraceable — but the
two keys an investigator uses to ask "what did this agent do in this session"
carried no information, and no test asserted on the value, because the tests that
did check identity asserted the *context's* value and supplied a context.

The invariant is not that the fields are populated. It is that **execution
identity derives from the verified grant**, which is signed, and never from a
``RuntimeContext``, which is unsigned caller input. A caller that presents a
grant while claiming a different subject is refused rather than silently
recorded under the grant's subject.

Scope: provenance only. Capability binding, consumption ordering and sandbox
containment are unchanged and covered elsewhere.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from app.models.audit_event import Decision
from app.models.execution_binding import ExecutionBinding
from app.models.execution_capability import (
    ExecutionCapabilities,
    FilesystemCapability,
    NetworkCapability,
    ResourceLimits,
)
from app.models.execution_evidence_retention import (
    ExecutionEvidenceRetentionPolicy,
)
from app.models.execution_provenance import ExecutionProvenance
from app.models.runtime_context import RuntimeContext
from app.models.sandbox_execution_result import SandboxExecutionResult
from app.models.tool_capability import ToolCapability
from app.models.tool_descriptor import ToolDescriptor
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.runtime.capability_registry import InMemoryCapabilityProfileRegistry
from app.runtime.execution_authority import (
    ExecutionAuthority,
    ExecutionBindingError,
    ExecutionRefusalReason,
)
from app.runtime.tool_executor import DefaultToolExecutor
from app.services.execution_evidence_service import ExecutionEvidenceService
from app.tools.base_tool import BaseTool

PROFILE_ID = "profile-provenance"


# Generous bound: these tests exercise lifecycle semantics, not capacity.
_TEST_RETENTION = ExecutionEvidenceRetentionPolicy(max_terminal_receipts=1000)


class _Tool(BaseTool):
    def __init__(self, tool_id: str = "provenance_tool") -> None:
        self.implementation_id = "test_echo"
        self._metadata = ToolMetadata(
            identity=ToolIdentity(
                tool_id=tool_id,
                name="Provenance Tool",
                version="1.0.0",
                description="Execution provenance corpus",
            ),
            governance=ToolGovernance(risk_level=ToolRiskLevel.LOW),
            capability=ToolCapability(category="test"),
            operational=ToolOperational(),
        )

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def execute(self, parameters: dict[str, object]) -> dict[str, object]:
        return {"executed": True, **parameters}


class _RecordingSandbox:
    """Records the provenance the executor handed it, so it can be observed."""

    def __init__(self) -> None:
        self.provenance: list[ExecutionProvenance] = []

    def execute(
        self,
        *,
        tool: BaseTool,
        parameters: dict[str, Any],
        capabilities: ExecutionCapabilities,
        provenance: ExecutionProvenance,

        implementation_id: str | None = None,

        tool_version: str | None = None,
    ) -> SandboxExecutionResult:
        self.provenance.append(provenance)
        return SandboxExecutionResult(success=True, output={"ok": True})


def _capabilities() -> ExecutionCapabilities:
    return ExecutionCapabilities(
        capability_profile_id=PROFILE_ID,
        filesystem=FilesystemCapability(workspace_root="/tmp", read_only=True),
        environment_variables={},
        network=NetworkCapability(),
        resources=ResourceLimits(),
    )


def _harness():
    authority = ExecutionAuthority()
    store = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)
    sandbox = _RecordingSandbox()
    registry = InMemoryCapabilityProfileRegistry({PROFILE_ID: _capabilities()})
    executor = DefaultToolExecutor(
        authority=authority,
        evidence_store=store,
        sandbox=sandbox,
        capability_registry=registry,
    )
    return authority, store, sandbox, executor


_OMITTED = object()


def _grant(authority: ExecutionAuthority, tool_id: str, params: dict[str, str], *,
           agent_id: str = "agent-1", session_id: str = "session-1",
           capability_digest: object = _OMITTED):
    caps = _capabilities()
    digest = caps.compute_digest() if capability_digest is _OMITTED else capability_digest
    return authority.issue(
        ExecutionBinding.from_operation(tool_id, "1.0.0", params),
        Decision.ALLOW,
        agent_id=agent_id,
        session_id=session_id,
        capability_profile_id=PROFILE_ID,
        capability_digest=digest,
    )


@pytest.mark.security_invariant
def test_invariant_evidence_identity_comes_from_the_grant_on_the_production_call_shape() -> None:
    """The exact call AgentRuntimeService makes: no context at all.

    This is the shape that produced ``"unspecified"``. A narrower test that passed a
    context would have kept passing against the defect.
    """
    authority, store, _, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(
        authority, tool.tool_id, {"msg": "x"},
        agent_id="agent-real", session_id="session-real",
    )

    executor.execute_descriptor(descriptor, {"msg": "x"}, grant=grant)

    receipt = store.get_by_grant(grant.grant_id)
    assert receipt is not None
    assert receipt.agent_id == "agent-real"
    assert receipt.session_id == "session-real"


@pytest.mark.security_invariant
def test_invariant_no_placeholder_identity_is_recorded_without_a_context() -> None:
    """The specific regression: a fabricated subject must not reach evidence."""
    authority, store, _, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {})

    executor.execute_descriptor(descriptor, {}, grant=grant)

    receipt = store.get_by_grant(grant.grant_id)
    assert receipt.agent_id != "unspecified"
    assert receipt.session_id != "unspecified"
    assert receipt.agent_id and receipt.session_id


@pytest.mark.security_invariant
def test_invariant_a_contradicting_context_cannot_reattribute_an_execution() -> None:
    """Confused deputy: grant for one subject, context claiming another.

    Refused outright rather than recorded under the grant's subject, because a
    mismatch between authority and caller context is an anomaly worth surfacing.
    """
    authority, store, sandbox, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {}, agent_id="agent-a", session_id="session-a")
    impersonating = RuntimeContext(
        session_id="session-a",
        request_id="req-1",
        user_id="u",
        principal="p",
        authenticated_agent="agent-b",
    )

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {}, impersonating, grant=grant)

    assert exc_info.value.reason is ExecutionRefusalReason.IDENTITY_MISMATCH
    assert sandbox.provenance == [], "nothing may execute after an identity refusal"
    assert store.get_by_grant(grant.grant_id) is None, "no evidence for a refused attempt"


@pytest.mark.security_invariant
def test_invariant_a_contradicting_session_is_refused() -> None:
    authority, _, sandbox, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {}, agent_id="agent-a", session_id="session-a")
    rotated = RuntimeContext(
        session_id="session-b",
        request_id="req-1",
        user_id="u",
        principal="p",
        authenticated_agent="agent-a",
    )

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {}, rotated, grant=grant)

    assert exc_info.value.reason is ExecutionRefusalReason.IDENTITY_MISMATCH
    assert sandbox.provenance == []


@pytest.mark.security_invariant
def test_invariant_an_identity_refusal_does_not_consume_the_grant() -> None:
    """A refused attempt never spends authority, so a misrouted call does not
    destroy a legitimate one."""
    authority, _, _, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {}, agent_id="agent-a", session_id="session-a")
    wrong = RuntimeContext(
        session_id="session-a",
        request_id="req-1",
        user_id="u",
        principal="p",
        authenticated_agent="agent-b",
    )

    with pytest.raises(ExecutionBindingError):
        executor.execute_descriptor(descriptor, {}, wrong, grant=grant)

    assert authority.outstanding_grant_count == 1
    executor.execute_descriptor(descriptor, {}, grant=grant)
    assert authority.outstanding_grant_count == 0


@pytest.mark.security_regression
def test_the_sandbox_receives_the_grants_identity_not_a_placeholder() -> None:
    """Provenance reaching the isolation boundary is grant-derived too."""
    authority, _, sandbox, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(
        authority, tool.tool_id, {}, agent_id="agent-sb", session_id="session-sb"
    )

    executor.execute_descriptor(descriptor, {}, grant=grant)

    assert len(sandbox.provenance) == 1
    assert sandbox.provenance[0].agent_id == "agent-sb"
    assert sandbox.provenance[0].session_id == "session-sb"


@pytest.mark.security_regression
def test_an_agreeing_context_supplies_correlation_but_not_identity() -> None:
    """A context that agrees is accepted, and its request_id is used for tracing.
    Identity still comes from the grant, so the two sources cannot diverge."""
    authority, store, _, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(
        authority, tool.tool_id, {}, agent_id="agent-c", session_id="session-c"
    )
    context = RuntimeContext(
        session_id="session-c",
        request_id="req-trace-9",
        user_id="u",
        principal="p",
        authenticated_agent="agent-c",
    )

    executor.execute_descriptor(descriptor, {}, context, grant=grant)

    receipt = store.get_by_grant(grant.grant_id)
    assert receipt.agent_id == grant.agent_id
    assert receipt.session_id == grant.session_id


@pytest.mark.security_invariant
def test_invariant_an_empty_context_identity_does_not_blank_out_evidence() -> None:
    """The one case where the two sources genuinely diverge.

    ``RuntimeContext`` does not constrain its identity fields, so an empty
    ``authenticated_agent`` is constructible and passes the mismatch guard, which
    deliberately treats an absent claim as "no claim" rather than a contradiction.
    Evidence must still carry the grant's subject rather than the empty string.
    """
    authority, store, _, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(
        authority, tool.tool_id, {}, agent_id="agent-d", session_id="session-d"
    )
    blank = RuntimeContext(
        session_id="",
        request_id="req-blank",
        user_id="u",
        principal="p",
        authenticated_agent="",
    )

    executor.execute_descriptor(descriptor, {}, blank, grant=grant)

    receipt = store.get_by_grant(grant.grant_id)
    assert receipt.agent_id == "agent-d"
    assert receipt.session_id == "session-d"


@pytest.mark.security_regression
def test_the_executor_module_contains_no_placeholder_identity_fallback() -> None:
    """Guard against reintroduction: the fabricated subject is gone from the source,
    not merely unreachable on the paths these tests exercise."""
    from pathlib import Path

    import app.runtime.tool_executor as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert '"unspecified"' not in source


@pytest.mark.security_invariant
def test_invariant_the_authoritative_grant_id_reaches_the_isolation_boundary() -> None:
    """The F-003 regression: the descriptor's ``grant_id`` was the request id.

    ``grant_id=context.request_id`` meant the evidence store recorded one identifier
    while the child payload carried a different one under the same name, breaking the
    execution-to-grant join an investigator follows.
    """
    authority, store, sandbox, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {})

    executor.execute_descriptor(descriptor, {}, grant=grant)

    assert len(sandbox.provenance) == 1
    assert sandbox.provenance[0].grant_id == grant.grant_id
    assert store.get_by_grant(grant.grant_id).grant_id == grant.grant_id


@pytest.mark.security_invariant
def test_invariant_the_request_id_stays_distinct_from_the_grant_id() -> None:
    """Two different concepts with different lifetimes and different trust. They were
    the same value, so neither could be used to distinguish the other."""
    authority, _, sandbox, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {})
    context = RuntimeContext(
        session_id="session-1",
        request_id="req-distinct",
        user_id="u",
        principal="p",
        authenticated_agent="agent-1",
    )

    executor.execute_descriptor(descriptor, {}, context, grant=grant)

    carried = sandbox.provenance[0]
    assert carried.request_id == "req-distinct"
    assert carried.grant_id == grant.grant_id
    assert carried.request_id != carried.grant_id


@pytest.mark.security_invariant
def test_invariant_no_authority_material_crosses_the_isolation_boundary() -> None:
    """The sandbox enforces a physical boundary and makes no security decision, so it
    has no use for the grant signature and must not be in a position to serialize it.

    The identity fields are descriptive execution context — what ran, as what version,
    through which implementation — and the child must never read them to select an
    implementation or override its ToolExecutionDescriptor. Authority material is a
    different category: the signature and the issuing authority never cross.
    """
    fields = set(ExecutionProvenance.model_fields)

    assert fields == {
        "grant_id",
        "agent_id",
        "session_id",
        "request_id",
        "tool_id",
        "tool_version",
        "implementation_id",
    }
    assert "signature" not in fields
    assert "authority_id" not in fields
    assert "capability_digest" not in fields, (
        "confinement is applied by the parent, not asserted to the child"
    )


@pytest.mark.security_regression
def test_provenance_takes_every_identity_field_from_the_grant() -> None:
    """``from_grant`` takes every authorization fact from the grant.

    The caller supplies ``request_id`` for correlation and the ``implementation_id`` the
    registration declared — which cannot come from the grant, because a grant authorizes
    a tool version and not a packaged implementation (F-05). Nothing a caller claims
    becomes an authorization fact.
    """
    authority = ExecutionAuthority()
    grant = _grant(
        authority, "provenance_tool", {}, agent_id="agent-z", session_id="session-z"
    )

    provenance = ExecutionProvenance.from_grant(
        grant, "req-7", implementation_id="provenance_impl_v3"
    )

    assert provenance.grant_id == grant.grant_id
    assert provenance.agent_id == grant.agent_id
    assert provenance.session_id == grant.session_id
    assert provenance.request_id == "req-7"
    assert provenance.tool_id == grant.binding.tool_id
    assert provenance.tool_version == grant.binding.tool_version
    assert provenance.implementation_id == "provenance_impl_v3"


@pytest.mark.security_regression
def test_provenance_is_immutable_and_rejects_unknown_fields() -> None:
    provenance = ExecutionProvenance(
        grant_id="g",
        agent_id="a",
        session_id="s",
        request_id="r",
        tool_id="t",
        tool_version="1.0.0",
        implementation_id="i",
    )

    with pytest.raises(ValidationError):
        provenance.agent_id = "other"

    with pytest.raises(ValidationError):
        ExecutionProvenance(
            grant_id="g", agent_id="a", session_id="s", request_id="r", signature="x"
        )


@pytest.mark.security_invariant
def test_invariant_an_authority_that_cannot_verify_is_refused_at_wiring() -> None:
    """Verification was discovered with ``hasattr`` and had no fail-closed branch:

        if hasattr(self._authority, "verify_grant"):
            self._authority.verify_grant(grant, requested)   # no else

    Consumption had a fallback; verification did not. An authority exposing
    ``consume_grant`` but not ``verify_grant`` would therefore have executed with the
    grant never verified, and no test could see it, because the real class happens to
    provide every method. The contract is now required.
    """

    class _PartialAuthority:
        """Consumes grants but cannot verify them."""

        authority_id = "partial"

        def issue(self, *a, **k):  # pragma: no cover - never reached
            return None

        def consume_grant(self, grant) -> None:  # pragma: no cover - never reached
            return None

        def verify_and_consume(self, grant, requested) -> None:  # pragma: no cover
            return None

    with pytest.raises(TypeError, match="ExecutionAuthorityProtocol"):
        DefaultToolExecutor(
            authority=_PartialAuthority(),
            sandbox=_RecordingSandbox(),
            capability_registry=InMemoryCapabilityProfileRegistry(
                {PROFILE_ID: _capabilities()}
            ),
        )


@pytest.mark.security_invariant
def test_invariant_verification_precedes_the_claim_and_execution() -> None:
    """Ordering, asserted rather than assumed: a grant refused at verification is never
    claimed and nothing executes.

    The executor claims through ``claim_grant`` rather than ``consume_grant``: the claim
    is the single-use gate, and it re-validates under the same lock hold that removes
    the grant.
    """
    calls: list[str] = []

    class _RecordingAuthority(ExecutionAuthority):
        def verify_grant(self, grant, requested) -> None:
            calls.append("verify")
            super().verify_grant(grant, requested)

        def claim_grant(self, grant, requested) -> None:
            calls.append("claim")
            super().claim_grant(grant, requested)

        def consume_grant(self, grant) -> None:  # pragma: no cover - not the gate
            calls.append("consume")
            super().consume_grant(grant)

    authority = _RecordingAuthority()
    sandbox = _RecordingSandbox()
    executor = DefaultToolExecutor(
        authority=authority,
        sandbox=sandbox,
        capability_registry=InMemoryCapabilityProfileRegistry(
            {PROFILE_ID: _capabilities()}
        ),
    )
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {})

    executor.execute_descriptor(descriptor, {}, grant=grant)

    assert calls == ["verify", "claim"], (
        "the executor claims the grant; it must not fall back to bare consumption"
    )
    assert len(sandbox.provenance) == 1


@pytest.mark.security_regression
def test_the_real_authority_satisfies_the_contract() -> None:
    """The contract must describe the implementation, not an aspiration."""
    from app.runtime.contracts import ExecutionAuthorityProtocol

    assert isinstance(ExecutionAuthority(), ExecutionAuthorityProtocol)


@pytest.mark.security_regression
def test_the_capability_registry_contract_covers_existence_checks() -> None:
    """RuntimeService calls exists() at issuance; the protocol omitted it, so the call
    was another undeclared dependency on a concrete class."""
    from app.runtime.contracts import CapabilityProfileRegistryProtocol

    registry = InMemoryCapabilityProfileRegistry({PROFILE_ID: _capabilities()})

    assert isinstance(registry, CapabilityProfileRegistryProtocol)
    assert hasattr(CapabilityProfileRegistryProtocol, "exists")
    assert registry.exists(PROFILE_ID) is True
    assert registry.exists("profile-absent") is False


# ---------------------------------------------------------------------------
# v0.17.2 Step 1 — the receipt correlation chain, and the digest gate that
# guarantees it (residual half of F-008)
# ---------------------------------------------------------------------------


@pytest.mark.security_invariant
def test_invariant_a_profile_bound_grant_without_a_digest_cannot_execute() -> None:
    """The residual half of the unbound-grant fail-open.

    ``verify_capability_binding`` compared the digest only when the grant presented
    one, so a grant carrying a capability profile but no digest was admitted with its
    binding never verified. The profile half was closed in v0.17.1; this is the digest
    half, which surfaced when the receipt's ``capability_digest`` became required —
    a required evidence field whose guarantee rested on a gate that did not enforce it.
    """
    from app.runtime.exceptions import CapabilityDigestMismatchError

    authority, store, sandbox, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {}, capability_digest=None)

    assert grant.capability_profile_id == PROFILE_ID, "the profile half is bound"
    assert grant.capability_digest is None, "the digest half is not"

    with pytest.raises(CapabilityDigestMismatchError, match="no capability digest"):
        executor.execute_descriptor(descriptor, {}, grant=grant)

    assert sandbox.provenance == [], "nothing may execute on an unverifiable binding"
    assert store.get_by_grant(grant.grant_id) is None, "and no receipt is created"


@pytest.mark.security_invariant
def test_invariant_the_receipt_records_the_capability_that_governed_the_execution() -> None:
    """A receipt that cannot identify the capability set governing an execution is not
    evidence of what was permitted to happen."""
    authority, store, _, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {})

    assert grant.capability_profile_id is not None
    assert grant.capability_digest is not None

    executor.execute_descriptor(descriptor, {}, grant=grant)

    receipt = store.get_by_grant(grant.grant_id)
    assert receipt.capability_profile_id == grant.capability_profile_id
    assert receipt.capability_digest == grant.capability_digest


@pytest.mark.security_invariant
def test_invariant_the_receipt_records_the_timeout_governing_this_execution() -> None:
    """Reconciliation derives its deadline from this value rather than a global SLA, so
    an execution running inside its declared limit is never reconciled as timed out."""
    authority, store, _, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {})

    executor.execute_descriptor(descriptor, {}, grant=grant)

    receipt = store.get_by_grant(grant.grant_id)
    assert (
        receipt.declared_timeout_seconds
        == _capabilities().resources.wall_clock_timeout_seconds
    )


@pytest.mark.security_regression
def test_the_receipt_carries_the_request_id_as_correlation_not_authority() -> None:
    """``request_id`` identifies the ingress; ``grant_id`` remains the authoritative
    bridge between authorization and execution. They must not be the same value."""
    authority, store, _, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {})
    context = RuntimeContext(
        session_id="session-1",
        request_id="req-correlation",
        user_id="u",
        principal="p",
        authenticated_agent="agent-1",
    )

    executor.execute_descriptor(descriptor, {}, context, grant=grant)

    receipt = store.get_by_grant(grant.grant_id)
    assert receipt.request_id == "req-correlation"
    assert receipt.grant_id == grant.grant_id
    assert receipt.request_id != receipt.grant_id


# ---------------------------------------------------------------------------
# F-001 — a grant authorizes exactly one execution attempt, under concurrency
# ---------------------------------------------------------------------------


@pytest.mark.security_invariant
def test_invariant_two_concurrent_executions_of_one_grant_yield_one_execution() -> None:
    """Single-use is a property of the executor boundary, not just of replay.

    The executor verified the grant, ran the capability checks, then removed it — two
    separate lock holds. Between them the grant was observable as outstanding, so two
    callers could both pass verification and both reach removal. Removal is idempotent,
    so the second was a silent no-op and **both executed**. Sequential replay tests
    could not see this: they only ever presented the grant again after the first attempt
    had finished.

    The threads are synchronised at the claim boundary so both are inside it together,
    which is precisely the interleaving the old ordering permitted.
    """
    import threading

    authority, store, sandbox, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {})

    barrier = threading.Barrier(2, timeout=10)
    original_claim = authority.claim_grant

    def _synchronised_claim(g, requested):
        barrier.wait()
        return original_claim(g, requested)

    authority.claim_grant = _synchronised_claim  # type: ignore[method-assign]

    results: list[str] = []
    lock = threading.Lock()

    def _attempt() -> None:
        try:
            executor.execute_descriptor(descriptor, {}, grant=grant)
            outcome = "executed"
        except ExecutionBindingError as exc:
            outcome = f"refused:{exc.reason.value}"
        except Exception as exc:  # pragma: no cover - surfaced if it ever happens
            outcome = f"error:{type(exc).__name__}"
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=_attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert sorted(results) == ["executed", f"refused:{ExecutionRefusalReason.CONSUMED.value}"], (
        f"exactly one attempt may execute; got {results}"
    )
    assert len(sandbox.provenance) == 1, "the sandbox ran exactly once"
    assert len(store.list_receipts()) == 1, "and exactly one execution was recorded"
    assert authority.outstanding_grant_count == 0


@pytest.mark.security_invariant
def test_invariant_a_claim_is_indivisible_from_its_validation() -> None:
    """The authority-level property the executor relies on.

    Verifying and then removing as separate operations does not claim a grant, even
    when both take the lock: the grant is observable as outstanding in between. Only one
    of many concurrent claims may succeed.
    """
    import threading

    authority = ExecutionAuthority()
    binding = ExecutionBinding.from_operation("provenance_tool", "1.0.0", {})
    caps = _capabilities()
    grant = authority.issue(
        binding,
        Decision.ALLOW,
        agent_id="agent-1",
        session_id="session-1",
        capability_profile_id=PROFILE_ID,
        capability_digest=caps.compute_digest(),
    )

    workers = 8
    barrier = threading.Barrier(workers, timeout=10)
    claimed: list[bool] = []
    lock = threading.Lock()

    def _claim() -> None:
        barrier.wait()
        try:
            authority.claim_grant(grant, binding)
            ok = True
        except ExecutionBindingError:
            ok = False
        with lock:
            claimed.append(ok)

    threads = [threading.Thread(target=_claim) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert claimed.count(True) == 1, f"exactly one claim may succeed; got {claimed}"
    assert claimed.count(False) == workers - 1
    assert authority.outstanding_grant_count == 0


@pytest.mark.security_regression
def test_a_refused_claim_does_not_spend_the_grant() -> None:
    """Refusal semantics are unchanged: a mismatched request leaves the grant usable."""
    authority, _, _, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {"msg": "authorized"})

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {"msg": "substituted"}, grant=grant)

    assert exc_info.value.reason is ExecutionRefusalReason.PARAMETER_MISMATCH
    assert authority.outstanding_grant_count == 1, "a refusal must not spend the grant"

    executor.execute_descriptor(descriptor, {"msg": "authorized"}, grant=grant)
    assert authority.outstanding_grant_count == 0


@pytest.mark.security_regression
def test_a_revoked_grant_cannot_be_claimed() -> None:
    """Revocation participates in the same authority decision as the claim."""
    authority, _, sandbox, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {}, agent_id="agent-revoked")

    authority.suspend_issuance("agent-revoked")

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {}, grant=grant)

    assert exc_info.value.reason is ExecutionRefusalReason.REVOKED
    assert sandbox.provenance == []


class _CountingLock:
    """Wraps the authority lock to count acquisitions."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.acquisitions = 0

    def __enter__(self):
        self.acquisitions += 1
        return self._inner.__enter__()

    def __exit__(self, *exc):
        return self._inner.__exit__(*exc)


@pytest.mark.security_invariant
@pytest.mark.parametrize("method", ["claim_grant", "verify_and_consume"])
def test_invariant_a_claim_validates_and_removes_in_one_lock_hold(method: str) -> None:
    """Atomicity asserted structurally, because concurrency cannot assert it reliably.

    A split implementation — validate under the lock, release, remove under the lock
    again — is racy, but the window between the two holds is so small that a thread
    barrier almost never lands inside it. The end-to-end concurrency test above passes
    against such an implementation by luck, so it cannot be the only guard.

    One acquisition is the property that makes the claim indivisible: nothing can
    observe the grant as outstanding between its validation and its removal.
    """
    authority = ExecutionAuthority()
    binding = ExecutionBinding.from_operation("provenance_tool", "1.0.0", {})
    caps = _capabilities()
    grant = authority.issue(
        binding,
        Decision.ALLOW,
        agent_id="agent-1",
        session_id="session-1",
        capability_profile_id=PROFILE_ID,
        capability_digest=caps.compute_digest(),
    )

    counting = _CountingLock(authority._lock)
    authority._lock = counting  # type: ignore[assignment]

    getattr(authority, method)(grant, binding)

    assert counting.acquisitions == 1, (
        f"{method} acquired the authority lock {counting.acquisitions} times; "
        "validation and removal must occur inside a single hold"
    )


@pytest.mark.security_invariant
def test_invariant_the_executor_claims_rather_than_consuming() -> None:
    """The gate the executor uses is the atomic one.

    Bare consumption is idempotent, so it cannot report whether this caller was the one
    that claimed the grant — an executor calling it would admit every concurrent caller.
    """
    authority, _, sandbox, executor = _harness()
    tool = _Tool()
    descriptor = ToolDescriptor(
        metadata=tool.metadata,
        instance=tool,
        implementation_id=tool.implementation_id,
    )
    grant = _grant(authority, tool.tool_id, {})

    claimed: list[str] = []
    consumed: list[str] = []
    original_claim = authority.claim_grant
    original_consume = authority.consume_grant

    def _claim(g, requested):
        claimed.append(g.grant_id)
        return original_claim(g, requested)

    def _consume(g):  # pragma: no cover - asserted absent
        consumed.append(g.grant_id)
        return original_consume(g)

    authority.claim_grant = _claim  # type: ignore[method-assign]
    authority.consume_grant = _consume  # type: ignore[method-assign]

    executor.execute_descriptor(descriptor, {}, grant=grant)

    assert claimed == [grant.grant_id]
    assert consumed == [], "the executor must not spend grants through bare consumption"
    assert len(sandbox.provenance) == 1
