"""No live execution may enter the execution boundary before startup recovery completes.

A process that dies mid-execution leaves STARTED receipts whose outcome nobody
observed. ``ExecutionReconciler`` resolves them to UNKNOWN rather than inventing an
outcome (ADR-032 N3-5, M4-7) — but it was constructed nowhere in ``app/``, so the
recovery boundary existed as a class and not as a lifecycle property.

The invariant is an ordering one, so these tests assert ordering rather than
registration. "The reconciler is wired into the lifespan" is satisfiable by a hook that
runs after the application is already serving requests.

Boundary entry is observed at ``record_started``: by N3-3 that call happens before the
sandbox is invoked, so it is the moment an execution enters the boundary.
"""

import threading
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.agents.enterprise_agent import EnterpriseAgent
from app.api import dependencies
from app.main import app
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.tool_invocation import ToolInvocation
from app.services.agent_runtime_service import AgentRuntimeService

RECONCILIATION_STARTED = "reconciliation_started"
RECONCILIATION_COMPLETED = "reconciliation_completed"
EXECUTION_STARTED = "execution_started"


class _FixedAgent(EnterpriseAgent):
    """Substitutes the LLM so the deterministic chain under test stays real."""

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def invoke(self, query: str) -> ToolInvocation:
        return ToolInvocation(tool_id="file_read", parameters={"path": "notes.txt"})


def _record_boundary_entry(monkeypatch, log: list[str]) -> None:
    """Append EXECUTION_STARTED when an execution enters the boundary."""
    store = dependencies.execution_evidence_store
    original = store.record_started

    def _recording(**kwargs):
        log.append(EXECUTION_STARTED)
        return original(**kwargs)

    monkeypatch.setattr(store, "record_started", _recording)


def _record_reconciliation(monkeypatch, log: list[str], *, gate=None, boom=False):
    """Instrument startup reconciliation, optionally blocking or failing it."""
    reconciler = dependencies.execution_reconciler
    original = reconciler.reconcile_on_startup
    calls: list[datetime] = []

    def _recording(now_utc: datetime):
        calls.append(now_utc)
        log.append(RECONCILIATION_STARTED)
        if gate is not None:
            gate.wait(timeout=10)
        if boom:
            raise RuntimeError("evidence plane unavailable at startup")
        result = original(now_utc)
        log.append(RECONCILIATION_COMPLETED)
        return result

    monkeypatch.setattr(reconciler, "reconcile_on_startup", _recording)
    return calls


def _execute_once() -> None:
    """Drive one execution through the live chain, outcome irrelevant.

    Registers its own agent rather than reusing the shared one. The live composition
    root is process-wide, so another test can suspend or escalate the shared agent and
    authorization would then deny — no grant, no execution, and this test would fail for
    a reason unrelated to startup ordering. A freshly registered agent has pristine
    enforcement state, so the ordering assertion measures ordering.
    """
    import contextlib
    import uuid

    agent_id = f"startup-recovery-{uuid.uuid4()}"
    dependencies.agent_service.register_agent(
        Agent(
            agent_id=agent_id,
            name="Startup Recovery Probe",
            owner="security-team",
            risk_tier=RiskTier.LOW,
            approved_tools=["file_read"],
            status=AgentStatus.ACTIVE,
        )
    )

    agent_runtime = AgentRuntimeService(
        agent=_FixedAgent(agent_id),
        runtime_service=dependencies.runtime_service,
        tool_registry=dependencies.tool_registry,
        execution_authority=dependencies.execution_authority,
        evidence_store=dependencies.execution_evidence_store,
    )
    with contextlib.suppress(Exception):
        agent_runtime.execute("read a file")


@pytest.mark.security_invariant
def test_invariant_startup_reconciliation_runs_exactly_once_on_the_live_store(
    monkeypatch,
) -> None:
    log: list[str] = []
    calls = _record_reconciliation(monkeypatch, log)

    with TestClient(app):
        pass

    assert len(calls) == 1, "reconciliation runs once per process start"
    assert log == [RECONCILIATION_STARTED, RECONCILIATION_COMPLETED]
    assert calls[0].tzinfo is not None, "N3-10: evidence time is timezone-aware UTC"


@pytest.mark.security_invariant
def test_invariant_the_startup_reconciler_shares_the_live_evidence_plane() -> None:
    """One evidence plane, not two independently constructed services.

    A reconciler resolving a different store would report a clean recovery while the
    store the executor writes to still held unresolved receipts.
    """
    assert (
        dependencies.execution_reconciler.evidence_store
        is dependencies.execution_evidence_store
    )
    assert (
        dependencies.runtime_service.evidence_store
        is dependencies.execution_evidence_store
    )


@pytest.mark.security_invariant
def test_invariant_reconciliation_completes_before_any_execution_enters_the_boundary(
    monkeypatch,
) -> None:
    """The ordering invariant, against a real execution rather than call order alone."""
    log: list[str] = []
    _record_reconciliation(monkeypatch, log)
    _record_boundary_entry(monkeypatch, log)

    with TestClient(app):
        _execute_once()

    assert RECONCILIATION_STARTED in log
    assert RECONCILIATION_COMPLETED in log
    assert EXECUTION_STARTED in log, "an execution actually entered the boundary"
    assert log.index(RECONCILIATION_STARTED) < log.index(RECONCILIATION_COMPLETED)
    assert log.index(RECONCILIATION_COMPLETED) < log.index(EXECUTION_STARTED)


@pytest.mark.security_invariant
def test_invariant_startup_does_not_complete_while_reconciliation_is_in_flight(
    monkeypatch,
) -> None:
    """Stronger than call ordering: readiness is gated on recovery returning.

    Reconciliation is held open on another thread. While it is blocked, startup must not
    have completed — so nothing the application serves can have run. Releasing it lets
    startup finish.
    """
    log: list[str] = []
    gate = threading.Event()
    _record_reconciliation(monkeypatch, log, gate=gate)
    startup_completed = threading.Event()

    def _start() -> None:
        with TestClient(app):
            startup_completed.set()

    worker = threading.Thread(target=_start, daemon=True)
    worker.start()

    # Reconciliation has begun and is blocked.
    for _ in range(100):
        if RECONCILIATION_STARTED in log:
            break
        threading.Event().wait(0.01)

    assert RECONCILIATION_STARTED in log, "reconciliation began during startup"
    assert RECONCILIATION_COMPLETED not in log
    assert not startup_completed.is_set(), (
        "the application must not be ready while recovery is still in flight"
    )

    gate.set()
    worker.join(timeout=10)

    assert startup_completed.is_set()
    assert RECONCILIATION_COMPLETED in log


@pytest.mark.security_invariant
def test_invariant_a_reconciliation_failure_fails_startup(monkeypatch) -> None:
    """Fail closed. Coming up anyway would serve requests against an unrecovered
    evidence plane, which is the condition this boundary exists to rule out."""
    log: list[str] = []
    _record_reconciliation(monkeypatch, log, boom=True)
    _record_boundary_entry(monkeypatch, log)

    with pytest.raises(RuntimeError, match="evidence plane unavailable at startup"):
        with TestClient(app):
            pytest.fail("startup must not complete when recovery fails")

    assert RECONCILIATION_COMPLETED not in log
    assert EXECUTION_STARTED not in log, "the execution boundary was never entered"


@pytest.mark.security_regression
def test_the_composition_root_holds_exactly_one_reconciler_and_one_store() -> None:
    """Step 9's lesson applied to startup: check for a second, quietly-built plane."""
    from app.services.execution_evidence_service import ExecutionEvidenceService
    from app.services.execution_reconciler import ExecutionReconciler

    stores = [
        v
        for v in vars(dependencies).values()
        if isinstance(v, ExecutionEvidenceService)
    ]
    reconcilers = [
        v for v in vars(dependencies).values() if isinstance(v, ExecutionReconciler)
    ]

    assert len(stores) == 1, "one live evidence store"
    assert len(reconcilers) == 1, "one recovery boundary"
    assert reconcilers[0].evidence_store is stores[0]
