"""Production execution evidence must be recorded, not merely recordable (NEW-003).

ADR-026 records NEW-003 as open because `DefaultToolExecutor` accepted an optional
evidence store and no production path supplied one:

    AgentRuntimeService.__init__
        self._executor = executor or DefaultToolExecutor(
            authority=authority,
            sandbox=sandbox,
            capability_registry=capability_registry,
        )          # evidence_store never passed

So every invariant of the evidence layer governed a capability that was implemented
and tested but sat on no running code path. `ExecutionEvidenceService` was
instantiated only by tests.

The invariant these tests hold is deliberately not "the dependency is present".
Asserting that a store object was handed to a constructor would pass against a chain
that never writes to it. Each test drives an authorized execution through the real
composition chain and then asserts the receipt is in the *externally supplied* store —
proving the dependency is used, not merely injected.

Scope: wiring and capacity only. Scenario isolation (ADR-013 M2a) and startup
reconciliation are separate steps.
"""

from pathlib import Path

import pytest

from app.agents.enterprise_agent import EnterpriseAgent
from app.config.settings import (
    DEFAULT_MAX_TERMINAL_EXECUTION_RECEIPTS,
    MAX_TERMINAL_EXECUTION_RECEIPTS_ENV_VAR,
    ConfigurationError,
    get_max_terminal_execution_receipts,
)
from app.models.execution_evidence_retention import ExecutionEvidenceRetentionPolicy
from app.models.execution_receipt import ExecutionStatus
from app.models.tool_invocation import ToolInvocation
from app.services.agent_runtime_service import AgentRuntimeService
from app.services.execution_evidence_service import ExecutionEvidenceService

from .conftest import BENIGN_FILE


class _FixedInvocationAgent(EnterpriseAgent):
    """Stands in for the LLM so the chain under test is the deterministic part.

    `AgentRuntimeService.execute` parses intent through the agent and then drives the
    security pipeline. Substituting the parser keeps every deterministic component real
    — runtime service, authority, executor, sandbox, evidence store — which is where the
    wiring being asserted lives. The LLM is an untrusted intent parser and is not part
    of this invariant.
    """

    def __init__(self, agent_id: str, tool_id: str, parameters: dict[str, str]) -> None:
        self._agent_id = agent_id
        self._invocation = ToolInvocation(tool_id=tool_id, parameters=parameters)

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def invoke(self, query: str) -> ToolInvocation:
        return self._invocation


def _live_chain(build_runtime, workspace: Path, evidence_store):
    """Build the composition chain the live root builds, with an injected store.

    `bootstrap_runtime_service` is what `app/api/dependencies.py` calls, and the corpus
    fixture wires the same way, so the store reaches the executor by the same route it
    does in production.
    """
    env = build_runtime(workspace=workspace, evidence_store=evidence_store)
    agent_runtime = AgentRuntimeService(
        agent=_FixedInvocationAgent(env.agent_id, "file_read", {"path": BENIGN_FILE}),
        runtime_service=env.runtime,
        tool_registry=env.tool_registry,
        execution_authority=env.execution_authority,
        evidence_store=evidence_store,
    )
    return env, agent_runtime


@pytest.mark.security_invariant
def test_invariant_an_authorized_execution_records_evidence_in_the_injected_store(
    build_runtime, security_workspace: Path
) -> None:
    """The NEW-003 acceptance property, executed rather than inspected."""
    store = ExecutionEvidenceService(
        retention_policy=ExecutionEvidenceRetentionPolicy(max_terminal_receipts=10)
    )
    env, agent_runtime = _live_chain(build_runtime, security_workspace, store)

    assert env.runtime.evidence_store is store, "the runtime carries the injected store"
    assert store.terminal_receipt_count == 0

    result = agent_runtime.execute("read the benign file")

    assert result.decision == "ALLOW"
    receipts = store.list_receipts()
    assert len(receipts) == 1, "the execution produced exactly one receipt"
    assert receipts[0].status == ExecutionStatus.SUCCEEDED
    assert receipts[0].tool_id == "file_read"


@pytest.mark.security_invariant
def test_invariant_the_recorded_receipt_carries_grant_derived_provenance(
    build_runtime, security_workspace: Path
) -> None:
    """Evidence written on the live path is attributable, which is what the whole
    correlation chain exists for."""
    store = ExecutionEvidenceService(
        retention_policy=ExecutionEvidenceRetentionPolicy(max_terminal_receipts=10)
    )
    env, agent_runtime = _live_chain(build_runtime, security_workspace, store)

    agent_runtime.execute("read the benign file")

    receipt = store.list_receipts()[0]
    assert receipt.agent_id == env.agent_id
    assert receipt.session_id, "the session the execution ran under is recorded"
    assert receipt.agent_id != "unspecified"
    assert receipt.capability_profile_id == "profile-file_read"
    assert receipt.capability_digest
    assert receipt.declared_timeout_seconds > 0


@pytest.mark.security_invariant
def test_invariant_the_effective_store_honours_the_configured_capacity(
    build_runtime, security_workspace: Path
) -> None:
    """Configuration cannot silently exist beside a differently configured service.

    A small capacity is used deliberately: it makes the bound observable without
    creating thousands of receipts, and it exercises the override rather than only the
    default.
    """
    configured = 2
    store = ExecutionEvidenceService(
        retention_policy=ExecutionEvidenceRetentionPolicy(
            max_terminal_receipts=configured
        )
    )
    env, agent_runtime = _live_chain(build_runtime, security_workspace, store)

    assert env.runtime.evidence_store.retention_policy.max_terminal_receipts == configured

    for _ in range(configured + 3):
        agent_runtime.execute("read the benign file")

    assert store.terminal_receipt_count == configured, (
        "the effective store retains no more than the configured capacity"
    )
    assert store.open_receipt_count == 0


@pytest.mark.security_regression
def test_the_configured_capacity_reaches_the_policy_unchanged(monkeypatch) -> None:
    """The configuration boundary itself: value in, same value on the policy."""
    monkeypatch.setenv(MAX_TERMINAL_EXECUTION_RECEIPTS_ENV_VAR, "37")

    policy = ExecutionEvidenceRetentionPolicy(
        max_terminal_receipts=get_max_terminal_execution_receipts()
    )
    store = ExecutionEvidenceService(retention_policy=policy)

    assert store.retention_policy.max_terminal_receipts == 37


@pytest.mark.security_regression
def test_an_absent_override_uses_the_documented_default(monkeypatch) -> None:
    monkeypatch.delenv(MAX_TERMINAL_EXECUTION_RECEIPTS_ENV_VAR, raising=False)

    assert get_max_terminal_execution_receipts() == DEFAULT_MAX_TERMINAL_EXECUTION_RECEIPTS
    assert DEFAULT_MAX_TERMINAL_EXECUTION_RECEIPTS == 10_000


@pytest.mark.security_regression
@pytest.mark.parametrize("bad", ["0", "-5", "many", "10.5", " "])
def test_a_malformed_capacity_override_fails_closed(monkeypatch, bad: str) -> None:
    """A deployment that tried to set a bound and failed must not look like one that
    never set it. The blank case is the exception: it is indistinguishable from unset."""
    monkeypatch.setenv(MAX_TERMINAL_EXECUTION_RECEIPTS_ENV_VAR, bad)

    if not bad.strip():
        assert (
            get_max_terminal_execution_receipts()
            == DEFAULT_MAX_TERMINAL_EXECUTION_RECEIPTS
        )
        return

    with pytest.raises(ConfigurationError, match=MAX_TERMINAL_EXECUTION_RECEIPTS_ENV_VAR):
        get_max_terminal_execution_receipts()


@pytest.mark.security_regression
def test_the_executor_never_constructs_its_own_evidence_store() -> None:
    """One authoritative store per composition root.

    If the executor could build its own, a wiring omission would produce a second
    store that silently collects the evidence nobody reads.
    """
    from app.runtime.tool_executor import DefaultToolExecutor

    executor = DefaultToolExecutor()

    assert executor._evidence_store is None


@pytest.mark.security_invariant
def test_invariant_the_live_composition_root_supplies_the_evidence_store() -> None:
    """The production composition root itself, not just an equivalent wiring.

    The tests above drive `bootstrap_runtime_service`, which is what
    `app/api/dependencies.py` calls — but that file is where the omission actually was,
    so the line that supplies the store is asserted directly. Otherwise removing it
    would leave every other test in this module passing.
    """
    from app.api import dependencies

    assert dependencies.runtime_service.evidence_store is not None, (
        "the live runtime must have an evidence store"
    )
    assert (
        dependencies.runtime_service.evidence_store
        is dependencies.execution_evidence_store
    ), "and it must be the one authoritative store, not a second instance"


@pytest.mark.security_regression
def test_the_live_store_is_bounded_by_configuration() -> None:
    """Step 6 made an unbounded store unrepresentable; this proves the live one is
    bounded by the configured capacity rather than an arbitrary constant."""
    from app.api import dependencies

    policy = dependencies.execution_evidence_store.retention_policy
    assert policy.max_terminal_receipts >= 1
    assert policy.max_terminal_receipts == get_max_terminal_execution_receipts()
