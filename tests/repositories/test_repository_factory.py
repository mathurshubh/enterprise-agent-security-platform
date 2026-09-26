"""Unit tests for RepositoryContainer and create_repositories factory (Plane 3, ADR-030)."""

import pytest

from app.repositories import (
    InMemoryAgentRepository,
    InMemoryApprovalGrantRepository,
    InMemoryAuditEvidenceRepository,
    InMemoryEnforcementStateRepository,
    InMemorySessionRepository,
    InMemoryToolRepository,
    RepositoryContainer,
    create_repositories,
)
from app.repositories.sql import (
    SqlApprovalGrantRepository,
    SqlEnforcementStateRepository,
    SqlSessionRepository,
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
    assert isinstance(container.approval_grant_repository, InMemoryApprovalGrantRepository)
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


def test_create_repositories_sql_with_engine() -> None:
    """backend='sql' with engine constructs SQL repositories."""
    engine = create_sql_engine("sqlite:///:memory:")
    container = create_repositories(backend="sql", engine=engine)

    assert isinstance(container, RepositoryContainer)
    assert isinstance(container.session_repository, SqlSessionRepository)
    assert isinstance(container.enforcement_repository, SqlEnforcementStateRepository)
    assert isinstance(container.approval_grant_repository, SqlApprovalGrantRepository)


def test_create_repositories_sql_with_session_factory() -> None:
    """backend='sql' with session_factory constructs SQL repositories."""
    engine = create_sql_engine("sqlite:///:memory:")
    sf = create_session_factory(engine)
    container = create_repositories(backend="sql", session_factory=sf)

    assert isinstance(container, RepositoryContainer)
    assert isinstance(container.session_repository, SqlSessionRepository)
    assert isinstance(container.enforcement_repository, SqlEnforcementStateRepository)
    assert isinstance(container.approval_grant_repository, SqlApprovalGrantRepository)


def test_create_repositories_rejects_unknown_backend() -> None:
    """Unsupported backend raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported repository backend: 'redis'"):
        create_repositories(backend="redis")  # type: ignore[arg-type]
