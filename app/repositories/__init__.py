"""Durable repository interfaces and persistence abstractions (ADR-030)."""

from app.repositories.factory import RepositoryContainer, create_repositories
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
    InvalidGrantTransitionError,
    SessionRepository,
    ToolRepository,
)

__all__ = [
    "AgentRepository",
    "ApprovalGrantRepository",
    "AuditEvidenceRepository",
    "EnforcementStateRepository",
    "InMemoryAgentRepository",
    "InMemoryApprovalGrantRepository",
    "InMemoryAuditEvidenceRepository",
    "InMemoryEnforcementStateRepository",
    "InMemorySessionRepository",
    "InMemoryToolRepository",
    "InvalidGrantTransitionError",
    "RepositoryContainer",
    "SessionRepository",
    "ToolRepository",
    "create_repositories",
]
