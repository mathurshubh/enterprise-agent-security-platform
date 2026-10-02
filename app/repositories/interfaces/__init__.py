"""Repository protocol interfaces defining domain persistence boundaries (ADR-030, ADR-031)."""

from app.repositories.interfaces.agent_repository import AgentRepository
from app.repositories.interfaces.approval_continuation_repository import (
    ApprovalContinuationRepository,
    InvalidContinuationTransitionError,
)
from app.repositories.interfaces.audit_evidence_repository import (
    AuditEvidenceRepository,
)
from app.repositories.interfaces.enforcement_state_repository import (
    EnforcementStateRepository,
)
from app.repositories.interfaces.session_repository import SessionRepository
from app.repositories.interfaces.tool_repository import ToolRepository

__all__ = [
    "AgentRepository",
    "ApprovalContinuationRepository",
    "AuditEvidenceRepository",
    "EnforcementStateRepository",
    "InvalidContinuationTransitionError",
    "SessionRepository",
    "ToolRepository",
]
