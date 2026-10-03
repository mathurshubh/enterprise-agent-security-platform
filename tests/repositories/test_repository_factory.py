"""Unit tests for RepositoryContainer and create_repositories factory (Plane 3, ADR-030)."""

import pytest

from app.repositories import (
    InMemoryAgentRepository,
    InMemoryApprovalContinuationRepository,
    InMemoryAuditEvidenceRepository,
    InMemoryEnforcementStateRepository,
    InMemorySessionRepository,
    InMemoryToolRepository,
    RepositoryCompositionError,
    RepositoryContainer,
    create_repositories,
)
from app.repositories.sql import (
    Base,
    SqlApprovalContinuationRepository,
    SqlAuditEvidenceRepository,
    SqlEnforcementStateRepository,
    SqlSessionRepository,
    SqlToolRepository,
    create_session_factory,
    create_sql_engine,
)


def test_create_repositories_memory_defaults() -> None:
    """backend='memory' returns a container with in-memory repository instances."""
    container = create_repositories(backend="memory")
    assert isinstance(container, RepositoryContainer)
    assert isinstance(container.agent_repository, InMemoryAgentRepository)
    assert isinstance(container.tool_repository, InMemoryToolRepository)
    assert isinstance(container.session_repository, InMemorySessionRepository)
    assert isinstance(container.enforcement_repository, InMemoryEnforcementStateRepository)
    assert isinstance(container.approval_grant_repository, InMemoryApprovalContinuationRepository)
    assert isinstance(container.audit_repository, InMemoryAuditEvidenceRepository)


def test_create_repositories_memory_rejects_sql_params() -> None:
    """backend='memory' raises ValueError if engine or session_factory is supplied."""
    engine = create_sql_engine("sqlite:///:memory:")
    with pytest.raises(ValueError, match="Cannot provide 'engine' or 'session_factory'"):
        create_repositories(backend="memory", engine=engine)

    sf = create_session_factory(engine)
    with pytest.raises(ValueError, match="Cannot provide 'engine' or 'session_factory'"):
        create_repositories(backend="memory", session_factory=sf)


def test_create_repositories_sql_requires_engine_or_session_factory() -> None:
    """backend='sql' raises ValueError if neither engine nor session_factory is supplied."""
    with pytest.raises(ValueError, match="Must provide either 'engine' or 'session_factory'"):
        create_repositories(backend="sql")


def test_create_repositories_sql_rejects_both_engine_and_session_factory() -> None:
    """backend='sql' raises ValueError if both engine and session_factory are supplied."""
    engine = create_sql_engine("sqlite:///:memory:")
    sf = create_session_factory(engine)
    with pytest.raises(ValueError, match="Cannot provide both 'engine' and 'session_factory'"):
        create_repositories(backend="sql", engine=engine, session_factory=sf)


_IN_MEMORY_TYPES = (
    InMemoryAgentRepository,
    InMemoryApprovalContinuationRepository,
    InMemoryAuditEvidenceRepository,
    InMemoryEnforcementStateRepository,
    InMemorySessionRepository,
    InMemoryToolRepository,
)


def _assert_sql_backed_except_agent(container: RepositoryContainer) -> None:
    assert isinstance(container.tool_repository, SqlToolRepository)
    assert isinstance(container.session_repository, SqlSessionRepository)
    assert isinstance(container.enforcement_repository, SqlEnforcementStateRepository)
    assert isinstance(container.approval_grant_repository, SqlApprovalContinuationRepository)
    assert isinstance(container.audit_repository, SqlAuditEvidenceRepository)


def test_create_repositories_sql_with_engine() -> None:
    """backend='sql' with engine defaults every repository that has a SQL adapter to it."""
    engine = create_sql_engine("sqlite:///:memory:")
    agents = InMemoryAgentRepository()
    container = create_repositories(backend="sql", engine=engine, agent_repository=agents)

    assert isinstance(container, RepositoryContainer)
    assert container.agent_repository is agents
    _assert_sql_backed_except_agent(container)


def test_create_repositories_sql_with_session_factory() -> None:
    """backend='sql' with session_factory defaults every repository that has a SQL adapter."""
    engine = create_sql_engine("sqlite:///:memory:")
    sf = create_session_factory(engine)
    agents = InMemoryAgentRepository()
    container = create_repositories(backend="sql", session_factory=sf, agent_repository=agents)

    assert isinstance(container, RepositoryContainer)
    assert container.agent_repository is agents
    _assert_sql_backed_except_agent(container)


@pytest.mark.security_invariant
def test_invariant_sql_backend_never_substitutes_an_in_memory_repository() -> None:
    """No silent persistence downgrade (ADR-030 §6).

    Every repository not explicitly supplied is SQL-backed; the only non-SQL instance in
    the container is the one the caller passed in.
    """
    engine = create_sql_engine("sqlite:///:memory:")
    agents = InMemoryAgentRepository()
    container = create_repositories(backend="sql", engine=engine, agent_repository=agents)

    implicit = [
        name
        for name in container.__dataclass_fields__
        if name != "agent_repository"
        and isinstance(getattr(container, name), _IN_MEMORY_TYPES)
    ]
    assert implicit == [], f"implicitly substituted in-memory repositories: {implicit}"


@pytest.mark.security_invariant
def test_invariant_sql_backend_without_an_agent_repository_fails_at_composition() -> None:
    """There is no SQL AgentRepository, so the gap is refused before any service exists.

    Previously an in-memory registry was substituted, and every session bind then failed
    on its foreign key to ``agents`` at request time.
    """
    engine = create_sql_engine("sqlite:///:memory:")
    with pytest.raises(RepositoryCompositionError, match="agent_repository"):
        create_repositories(backend="sql", engine=engine)


def test_repository_composition_error_is_a_value_error() -> None:
    """Callers already handling the factory's ValueError keep working."""
    assert issubclass(RepositoryCompositionError, ValueError)


def test_create_repositories_sql_tool_repository_defaults_to_sql() -> None:
    engine = create_sql_engine("sqlite:///:memory:")
    container = create_repositories(
        backend="sql", engine=engine, agent_repository=InMemoryAgentRepository()
    )
    assert isinstance(container.tool_repository, SqlToolRepository)


def test_create_repositories_sql_audit_repository_defaults_to_sql() -> None:
    engine = create_sql_engine("sqlite:///:memory:")
    container = create_repositories(
        backend="sql", engine=engine, agent_repository=InMemoryAgentRepository()
    )
    assert isinstance(container.audit_repository, SqlAuditEvidenceRepository)


def test_create_repositories_sql_uses_explicitly_supplied_adapters_as_given() -> None:
    """Explicit injection is a visible composition choice and is honoured, not overridden."""
    engine = create_sql_engine("sqlite:///:memory:")
    agents = InMemoryAgentRepository()
    tools = InMemoryToolRepository()
    audit = InMemoryAuditEvidenceRepository()
    container = create_repositories(
        backend="sql",
        engine=engine,
        agent_repository=agents,
        tool_repository=tools,
        audit_repository=audit,
    )

    assert container.agent_repository is agents
    assert container.tool_repository is tools
    assert container.audit_repository is audit
    assert isinstance(container.session_repository, SqlSessionRepository)


def test_sql_audit_evidence_survives_a_new_container_on_the_same_database(tmp_path) -> None:
    """Restart-style durability: audit written through one container is read by the next.

    Under the previous in-memory audit default this evidence vanished with the container.
    """
    from app.models.audit_event import AuditEvent, Decision

    engine = create_sql_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    Base.metadata.create_all(engine)

    first = create_repositories(
        backend="sql", engine=engine, agent_repository=InMemoryAgentRepository()
    )
    first.audit_repository.append(
        AuditEvent(
            event_id="evt-durable",
            session_id="sess-1",
            agent_id="agent-1",
            requested_tool_id="tool-that-does-not-exist",
            decision=Decision.DENY,
        )
    )

    second = create_repositories(
        backend="sql", engine=engine, agent_repository=InMemoryAgentRepository()
    )
    stored = second.audit_repository.get("evt-durable")
    assert stored is not None
    assert stored.decision == Decision.DENY
    engine.dispose()


def test_create_repositories_rejects_unknown_backend() -> None:
    """Unsupported backend raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported repository backend: 'redis'"):
        create_repositories(backend="redis")  # type: ignore[arg-type]
