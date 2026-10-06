"""SQL persistence layer and repository adapters (Plane 3, ADR-030)."""

from app.repositories.sql.administrative_repository import (
    SqlAdministrativeAuditRepository,
    SqlAdministrativeStateRepository,
)
from app.repositories.sql.agent_repository import SqlAgentRepository
from app.repositories.sql.approval_continuation_repository import (
    SqlApprovalContinuationRepository,
)
from app.repositories.sql.audit_evidence_repository import SqlAuditEvidenceRepository
from app.repositories.sql.base import Base
from app.repositories.sql.enforcement_repository import SqlEnforcementStateRepository
from app.repositories.sql.engine import create_sql_engine, dispose_sql_engine
from app.repositories.sql.session import create_session_factory, transactional_session
from app.repositories.sql.session_repository import SqlSessionRepository
from app.repositories.sql.tool_repository import SqlToolRepository

__all__ = [
    "SqlAdministrativeAuditRepository",
    "SqlAdministrativeStateRepository",
    "SqlAgentRepository",
    "Base",
    "create_session_factory",
    "create_sql_engine",
    "dispose_sql_engine",
    "SqlApprovalContinuationRepository",
    "SqlAuditEvidenceRepository",
    "SqlEnforcementStateRepository",
    "SqlSessionRepository",
    "SqlToolRepository",
    "transactional_session",
]
