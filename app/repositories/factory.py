"""RepositoryContainer and create_repositories factory (Plane 3, ADR-030).

Provides a thin, explicit composition boundary for repository protocol instances.
Domain services depend strictly on domain protocols, never on concrete database models,
session makers, or engine lifecycles.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

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
from app.repositories.sql import (
    SqlApprovalGrantRepository,
    SqlEnforcementStateRepository,
    SqlSessionRepository,
    create_session_factory,
)


@dataclass(frozen=True)
class RepositoryContainer:
    """Deliberately thin composition container holding domain repository protocol instances.

    Domain services receive repository protocols exclusively; no database models,
    engines, or ORM sessions leak past this boundary.
    """

    agent_repository: AgentRepository
    tool_repository: ToolRepository
    session_repository: SessionRepository
    enforcement_repository: EnforcementStateRepository
    approval_grant_repository: ApprovalGrantRepository
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

    Raises:
        ValueError: On invalid parameter combinations (e.g. providing an engine
            with backend='memory', or providing neither engine nor session_factory
            with backend='sql').
    """
    if backend == "memory":
        if engine is not None or session_factory is not None:
            raise ValueError(
                "Cannot provide 'engine' or 'session_factory' when backend='memory'."
            )
        return RepositoryContainer(
            agent_repository=agent_repository or InMemoryAgentRepository(),
            tool_repository=tool_repository or InMemoryToolRepository(),
            session_repository=InMemorySessionRepository(),
            enforcement_repository=InMemoryEnforcementStateRepository(),
            approval_grant_repository=InMemoryApprovalGrantRepository(),
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
            agent_repository=agent_repository or InMemoryAgentRepository(),
            tool_repository=tool_repository or InMemoryToolRepository(),
            session_repository=SqlSessionRepository(sf),
            enforcement_repository=SqlEnforcementStateRepository(sf),
            approval_grant_repository=SqlApprovalGrantRepository(sf),
            audit_repository=audit_repository or InMemoryAuditEvidenceRepository(),
        )

    raise ValueError(
        f"Unsupported repository backend: '{backend}'. Expected 'memory' or 'sql'."
    )
