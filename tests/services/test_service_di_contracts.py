"""Tests for Service Dependency Injection and Repository Protocol Boundaries (PR #180).

Verifies the architectural invariants established for Phase 3 Step 1:
1. Services accept repository protocols via dependency injection.
2. In-memory adapters satisfy repository protocols.
3. Domain services import exclusively from app.repositories.interfaces, never app.repositories.in_memory.
4. Composition root (app.api.dependencies) instantiates repository singletons and injects them.
5. PR #180 behavior neutrality: injected repositories are wiring only; no dual-writes or repository reads.
"""

import ast
from pathlib import Path

from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import AuditEvent, Decision
from app.models.session import Session
from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.repositories.in_memory import (
    InMemoryAgentRepository,
    InMemoryApprovalGrantRepository,
    InMemoryAuditEvidenceRepository,
    InMemoryEnforcementStateRepository,
    InMemorySessionRepository,
    InMemoryToolRepository,
)
from app.repositories.interfaces import (
    AgentRepository,
    ApprovalGrantRepository,
    AuditEvidenceRepository,
    EnforcementStateRepository,
    SessionRepository,
    ToolRepository,
)
from app.services.agent_service import AgentService
from app.services.audit_service import AuditService
from app.services.session_service import SessionService
from app.services.tool_service import ToolService


class TestServiceDIRepositoryContracts:
    """Verifies constructor dependencies and protocol acceptance across domain services."""

    def test_agent_service_accepts_repository_protocols(self) -> None:
        agent_repo = InMemoryAgentRepository()
        enf_repo = InMemoryEnforcementStateRepository()

        service = AgentService(
            agent_repository=agent_repo,
            enforcement_repository=enf_repo,
        )

        assert service.agent_repository is agent_repo
        assert service.enforcement_repository is enf_repo

    def test_audit_service_accepts_repository_protocol(self) -> None:
        audit_repo = InMemoryAuditEvidenceRepository()

        service = AuditService(audit_repository=audit_repo)

        assert service.audit_repository is audit_repo

    def test_session_service_accepts_repository_protocol(self) -> None:
        session_repo = InMemorySessionRepository()

        service = SessionService(session_repository=session_repo)

        assert service.session_repository is session_repo

    def test_tool_service_accepts_repository_protocol(self) -> None:
        tool_repo = InMemoryToolRepository()

        service = ToolService(tool_repository=tool_repo)

        assert service.tool_repository is tool_repo

    def test_default_service_construction_preserves_none_repository(self) -> None:
        """Existing parameterless construction continues to work for unmigrated services defaulting to None."""
        tool_service = ToolService()

        assert tool_service.tool_repository is None

    def test_session_service_requires_repository_dependency(self) -> None:
        """SessionService in PR #183 requires an explicit repository dependency."""
        import pytest

        with pytest.raises(TypeError):
            SessionService()  # type: ignore[call-arg]

    def test_audit_service_requires_repository_dependency(self) -> None:
        """AuditService in PR #182 requires an explicit repository dependency."""
        import pytest

        with pytest.raises(TypeError):
            AuditService()  # type: ignore[call-arg]

    def test_agent_service_requires_repository_dependencies(self) -> None:
        """AgentService in PR #181 requires explicit repository dependencies."""
        import pytest

        with pytest.raises(TypeError):
            AgentService()  # type: ignore[call-arg]


class TestProtocolCompliance:
    """Verifies that all concrete in-memory adapters satisfy their respective Protocol interfaces."""

    def test_in_memory_adapters_satisfy_protocols(self) -> None:
        agent_repo: AgentRepository = InMemoryAgentRepository()
        tool_repo: ToolRepository = InMemoryToolRepository()
        audit_repo: AuditEvidenceRepository = InMemoryAuditEvidenceRepository()
        enf_repo: EnforcementStateRepository = InMemoryEnforcementStateRepository()
        session_repo: SessionRepository = InMemorySessionRepository()
        grant_repo: ApprovalGrantRepository = InMemoryApprovalGrantRepository()

        # Check required protocol methods exist on the adapter classes
        assert (
            hasattr(agent_repo, "get")
            and hasattr(agent_repo, "save")
            and hasattr(agent_repo, "list")
        )
        assert (
            hasattr(tool_repo, "get")
            and hasattr(tool_repo, "save")
            and hasattr(tool_repo, "list")
        )
        assert (
            hasattr(audit_repo, "append")
            and hasattr(audit_repo, "get")
            and hasattr(audit_repo, "query")
        )
        assert (
            hasattr(enf_repo, "get_state")
            and hasattr(enf_repo, "record_transition")
            and hasattr(enf_repo, "list_transitions")
            and hasattr(enf_repo, "get_epoch")
        )
        assert (
            hasattr(session_repo, "get_session")
            and hasattr(session_repo, "save_session")
            and hasattr(session_repo, "list_sessions")
            and hasattr(session_repo, "create_session")
            and hasattr(session_repo, "bind_or_create_session")
            and hasattr(session_repo, "get_tombstone")
            and hasattr(session_repo, "save_tombstone")
            and hasattr(session_repo, "terminalize_session")
            and hasattr(session_repo, "record_event")
            and hasattr(session_repo, "list_events")
            and hasattr(session_repo, "prune_events")
            and hasattr(session_repo, "update_event_final_decision")
        )
        assert (
            hasattr(grant_repo, "create_grant")
            and hasattr(grant_repo, "get_grant")
            and hasattr(grant_repo, "transition_grant")
            and hasattr(grant_repo, "list_grants")
        )


class TestImportBoundaries:
    """Enforces strict architectural decoupling between domain services and repository implementations."""

    def test_domain_services_never_import_in_memory_adapters(self) -> None:
        """Domain services must only import repository protocols, never concrete in-memory adapters."""
        services_dir = Path("app/services")
        forbidden_import_substrings = [
            "app.repositories.in_memory",
            "InMemoryAgentRepository",
            "InMemoryToolRepository",
            "InMemoryAuditEvidenceRepository",
            "InMemoryEnforcementStateRepository",
            "InMemorySessionRepository",
            "InMemoryApprovalGrantRepository",
        ]

        # Scan all service files except composition roots (runtime_bootstrap.py, scenario_sandbox.py)
        domain_service_files = [
            f
            for f in services_dir.glob("*.py")
            if f.name not in {"runtime_bootstrap.py", "scenario_sandbox.py"}
        ]

        for service_file in domain_service_files:
            source = service_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(service_file))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for forbidden in forbidden_import_substrings:
                            assert forbidden not in alias.name, (
                                f"{service_file} illegally imports concrete adapter '{alias.name}'"
                            )
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    assert "app.repositories.in_memory" not in module, (
                        f"{service_file} illegally imports from '{module}'"
                    )
                    for alias in node.names:
                        for forbidden in forbidden_import_substrings:
                            assert forbidden != alias.name, (
                                f"{service_file} illegally imports concrete adapter '{alias.name}'"
                            )


class TestCompositionRootWiring:
    """Verifies that app.api.dependencies wires singletons with matching repository identities."""

    def test_composition_root_wires_shared_repository_instances(self) -> None:
        from app.api import dependencies

        assert (
            dependencies.agent_service.agent_repository is dependencies.agent_repository
        )
        assert (
            dependencies.agent_service.enforcement_repository
            is dependencies.enforcement_repository
        )
        assert (
            dependencies.audit_service.audit_repository is dependencies.audit_repository
        )
        assert (
            dependencies.session_service.session_repository
            is dependencies.session_repository
        )
        assert dependencies.tool_service.tool_repository is dependencies.tool_repository


class TestPR180BehaviorNeutrality:
    """Proves that PR #180 is strictly wiring-only with zero dual-writes or repository reads."""

    def test_agent_registration_writes_authoritatively_to_repository_in_pr181(
        self,
    ) -> None:
        agent_repo = InMemoryAgentRepository()
        enf_repo = InMemoryEnforcementStateRepository()
        service = AgentService(
            agent_repository=agent_repo,
            enforcement_repository=enf_repo,
        )

        agent = Agent(
            agent_id="test-agent",
            name="Test Agent",
            owner="sec",
            risk_tier=RiskTier.LOW,
            status=AgentStatus.ACTIVE,
        )
        service.register_agent(agent)

        # In PR #181, AgentRepository is the authoritative state source
        stored = agent_repo.get("test-agent")
        assert stored is not None
        assert stored.agent_id == "test-agent"
        assert service.get_agent("test-agent").agent_id == "test-agent"

    def test_audit_recording_persists_authoritatively_to_repository(self) -> None:
        audit_repo = InMemoryAuditEvidenceRepository()
        service = AuditService(audit_repository=audit_repo)

        event = AuditEvent(
            event_id="ev-test",
            session_id="sess-1",
            agent_id="agent-1",
            tool_id="file_read",
            action="file_read",
            decision=Decision.ALLOW,
            reason="policy permit",
        )
        service.record_event(event)

        # In PR #182, AuditEvidenceRepository is the authoritative state source
        assert len(service.list_events()) == 1
        assert len(audit_repo.query()) == 1
        stored = audit_repo.get("ev-test")
        assert stored is not None
        assert stored.event_id == "ev-test"
        assert not hasattr(service, "_events")

    def test_session_creation_writes_to_repository_authoritatively_in_pr183(
        self,
    ) -> None:
        session_repo = InMemorySessionRepository()
        service = SessionService(session_repository=session_repo)

        session = Session(session_id="sess-test", agent_id="agent-1")
        service.create_session(session)

        assert service.get_session("sess-test").session_id == "sess-test"
        stored = session_repo.get_session("sess-test")
        assert stored is not None
        assert stored.session_id == "sess-test"
        assert not hasattr(service, "_sessions")
        assert not hasattr(service, "_tombstones")
        assert not hasattr(service, "_events_heap")

    def test_tool_registration_does_not_dual_write_to_repository_in_pr180(self) -> None:
        tool_repo = InMemoryToolRepository()
        service = ToolService(tool_repository=tool_repo)

        tool = Tool(
            metadata=ToolMetadata(
                identity=ToolIdentity(
                    tool_id="tool-test", name="Tool", description="desc"
                ),
                governance=ToolGovernance(risk_level=ToolRiskLevel.LOW),
                capability=ToolCapability(category="filesystem"),
                operational=ToolOperational(),
            )
        )
        service.register_tool(tool)

        assert service.get_tool("tool-test").tool_id == "tool-test"
        assert tool_repo.get("tool-test") is None
