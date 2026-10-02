"""Durable repository interfaces and persistence abstractions (ADR-030)."""

from app.repositories.factory import RepositoryContainer, create_repositories
from app.repositories.in_memory import (
    InMemoryAgentRepository,
    InMemoryApprovalContinuationRepository,
    InMemoryAuditEvidenceRepository,
    InMemoryEnforcementStateRepository,
    InMemorySessionRepository,
    InMemoryToolRepository,
)
from app.repositories.interfaces import (
    AgentRepository,
    ApprovalContinuationRepository,
    AuditEvidenceRepository,
    EnforcementStateRepository,
    InvalidContinuationTransitionError,
    SessionRepository,
    ToolRepository,
)

__all__ = [
    "AgentRepository",
    "ApprovalContinuationRepository",
    "AuditEvidenceRepository",
    "EnforcementStateRepository",
    "InMemoryAgentRepository",
    "InMemoryApprovalContinuationRepository",
    "InMemoryAuditEvidenceRepository",
    "InMemoryEnforcementStateRepository",
    "InMemorySessionRepository",
    "InMemoryToolRepository",
    "InvalidContinuationTransitionError",
    "RepositoryContainer",
    "SessionRepository",
    "ToolRepository",
    "create_repositories",
]
