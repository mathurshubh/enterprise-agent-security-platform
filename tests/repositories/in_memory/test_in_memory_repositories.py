"""Concrete contract test suite executing against all InMemory repository adapters."""

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
from tests.repositories.contracts import (
    BaseAgentRepositoryContractTests,
    BaseApprovalGrantRepositoryContractTests,
    BaseAuditEvidenceRepositoryContractTests,
    BaseEnforcementStateRepositoryContractTests,
    BaseSessionRepositoryContractTests,
    BaseToolRepositoryContractTests,
)


class TestInMemoryAgentRepository(BaseAgentRepositoryContractTests):
    def create_repository(self) -> AgentRepository:
        return InMemoryAgentRepository()


class TestInMemoryToolRepository(BaseToolRepositoryContractTests):
    def create_repository(self) -> ToolRepository:
        return InMemoryToolRepository()


class TestInMemoryAuditEvidenceRepository(BaseAuditEvidenceRepositoryContractTests):
    def create_repository(self) -> AuditEvidenceRepository:
        return InMemoryAuditEvidenceRepository()


class TestInMemoryEnforcementStateRepository(
    BaseEnforcementStateRepositoryContractTests
):
    def create_repository(self) -> EnforcementStateRepository:
        return InMemoryEnforcementStateRepository()


class TestInMemorySessionRepository(BaseSessionRepositoryContractTests):
    def create_repository(self) -> SessionRepository:
        return InMemorySessionRepository()


class TestInMemoryApprovalGrantRepository(BaseApprovalGrantRepositoryContractTests):
    def create_repository(self) -> ApprovalGrantRepository:
        return InMemoryApprovalGrantRepository()
