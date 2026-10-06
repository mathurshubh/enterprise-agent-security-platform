"""RepositoryContainer and create_repositories factory (Plane 3, ADR-030).

Provides a thin, explicit composition boundary for repository protocol instances.
Domain services depend strictly on domain protocols, never on concrete database models,
session makers, or engine lifecycles.

**No silent persistence downgrade** (ADR-030 §6). With ``backend="sql"``, no repository is
implicitly replaced by an in-memory implementation. Existing SQL adapters are used by
default; a repository with no SQL adapter must be supplied by the caller, and composition
fails with ``RepositoryCompositionError`` before any service is constructed otherwise.

An explicitly supplied adapter is used as given. That is a visible composition choice, not
a fallback — but an explicitly supplied in-memory adapter under ``backend="sql"`` is not a
durable topology, and this factory does not make it one. Production composition must
enforce its own durability contract.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.repositories.in_memory import (
    InMemoryAdministrativeAuditRepository,
    InMemoryAdministrativeStateRepository,
    InMemoryAgentRepository,
    InMemoryApprovalContinuationRepository,
    InMemoryAuditEvidenceRepository,
    InMemoryEnforcementStateRepository,
    InMemorySessionRepository,
    InMemoryToolRepository,
)
from app.repositories.interfaces import (
    AdministrativeAuditRepository,
    AdministrativeStateRepository,
    AgentRepository,
    ApprovalContinuationRepository,
    AuditEvidenceRepository,
    EnforcementStateRepository,
    SessionRepository,
    ToolRepository,
)
from app.repositories.sql import (
    SqlAdministrativeAuditRepository,
    SqlAdministrativeStateRepository,
    SqlAgentRepository,
    SqlApprovalContinuationRepository,
    SqlAuditEvidenceRepository,
    SqlEnforcementStateRepository,
    SqlSessionRepository,
    SqlToolRepository,
    create_session_factory,
)


class RepositoryCompositionError(ValueError):
    """The requested persistence topology cannot be constructed safely.

    A configuration failure raised at composition time, so that a topology the backend
    cannot honour is refused before any service exists rather than discovered by the
    first request that writes to it.
    """


@dataclass(frozen=True)
class RepositoryContainer:
    """Deliberately thin composition container holding domain repository protocol instances.

    Domain services receive repository protocols exclusively; no database models,
    engines, or ORM sessions leak past this boundary.
    """

    agent_repository: AgentRepository
    administrative_repository: AdministrativeStateRepository
    administrative_audit_repository: AdministrativeAuditRepository
    tool_repository: ToolRepository
    session_repository: SessionRepository
    enforcement_repository: EnforcementStateRepository
    approval_grant_repository: ApprovalContinuationRepository
    audit_repository: AuditEvidenceRepository


def create_repositories(
    backend: Literal["memory", "sql"] = "memory",
    *,
    engine: Engine | None = None,
    session_factory: sessionmaker[OrmSession] | None = None,
    agent_repository: AgentRepository | None = None,
    tool_repository: ToolRepository | None = None,
    audit_repository: AuditEvidenceRepository | None = None,
) -> RepositoryContainer:
    """Compose and return a RepositoryContainer for the specified backend.

    With ``backend="sql"``, the session, enforcement, approval-continuation, tool and audit
    repositories default to their SQL adapters. There is no SQL ``AgentRepository``, so
    ``agent_repository`` is required.

    Raises:
        ValueError: On invalid parameter combinations (e.g. providing an engine
            with backend='memory', or providing neither engine nor session_factory
            with backend='sql').
        RepositoryCompositionError: With backend='sql', when a repository that has no SQL
            adapter is not supplied by the caller.
    """
    if backend == "memory":
        if engine is not None or session_factory is not None:
            raise ValueError(
                "Cannot provide 'engine' or 'session_factory' when backend='memory'."
            )
        _memory_agents = agent_repository or InMemoryAgentRepository()
        return RepositoryContainer(
            agent_repository=_memory_agents,
            tool_repository=tool_repository or InMemoryToolRepository(),
            administrative_repository=InMemoryAdministrativeStateRepository(
                agent_repository=_memory_agents
            ),
            administrative_audit_repository=InMemoryAdministrativeAuditRepository(),
            session_repository=InMemorySessionRepository(),
            enforcement_repository=InMemoryEnforcementStateRepository(),
            approval_grant_repository=InMemoryApprovalContinuationRepository(),
            audit_repository=audit_repository or InMemoryAuditEvidenceRepository(),
        )

    if backend == "sql":
        if engine is None and session_factory is None:
            raise ValueError(
                "Must provide either 'engine' or 'session_factory' when backend='sql'."
            )
        if engine is not None and session_factory is not None:
            raise ValueError(
                "Cannot provide both 'engine' and 'session_factory'; provide exactly one."
            )

        sf = session_factory if session_factory is not None else create_session_factory(engine)  # type: ignore[arg-type]

        return RepositoryContainer(
            # A SQL agent repository now exists (F-09.D), so this no longer refuses.
            # An in-memory substitute is still never applied implicitly: the SQL tables
            # reference ``agents``, and a volatile registry would leave every bind failing
            # on its foreign key at request time.
            agent_repository=(
                agent_repository
                if agent_repository is not None
                else SqlAgentRepository(sf)
            ),
            tool_repository=(
                tool_repository if tool_repository is not None else SqlToolRepository(sf)
            ),
            administrative_repository=SqlAdministrativeStateRepository(sf),
            administrative_audit_repository=SqlAdministrativeAuditRepository(sf),
            session_repository=SqlSessionRepository(sf),
            enforcement_repository=SqlEnforcementStateRepository(sf),
            approval_grant_repository=SqlApprovalContinuationRepository(sf),
            audit_repository=(
                audit_repository
                if audit_repository is not None
                else SqlAuditEvidenceRepository(sf)
            ),
        )

    raise ValueError(
        f"Unsupported repository backend: '{backend}'. Expected 'memory' or 'sql'."
    )
