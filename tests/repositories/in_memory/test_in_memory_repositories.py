"""Concrete contract test suite executing against all InMemory repository adapters."""

from app.repositories.in_memory import (
    InMemoryAdministrativeStateRepository,
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
    SessionRepository,
    ToolRepository,
)
from tests.repositories.contracts import (
    BaseAdministrativeStateRepositoryContractTests,
    BaseAgentRepositoryContractTests,
    BaseApprovalContinuationRepositoryContractTests,
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


class TestInMemoryApprovalContinuationRepository(BaseApprovalContinuationRepositoryContractTests):
    def create_repository(self) -> ApprovalContinuationRepository:
        return InMemoryApprovalContinuationRepository()


class TestInMemoryAdministrativeStateRepository(
    BaseAdministrativeStateRepositoryContractTests
):
    def create_repository(self) -> InMemoryAdministrativeStateRepository:
        return InMemoryAdministrativeStateRepository()
