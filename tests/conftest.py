"""
Shared pytest fixtures and test helpers for authentication and API testing.

``JWT_SECRET_KEY`` is provisioned here before any test module imports the
application. Since finding H-1 was fixed, ``app.api.dependencies`` resolves the
signing key at import time and raises ``ConfigurationError`` when it is absent,
so the suite must supply one explicitly.

The assignment is unconditional to keep the suite hermetic: a developer shell
holding an unrelated (or retired) ``JWT_SECRET_KEY`` must not change how the
tests run.
"""

import os

os.environ["JWT_SECRET_KEY"] = "pytest-suite-signing-key-not-for-production-use"

import pytest  # noqa: E402

from app.api.dependencies import jwt_service  # noqa: E402
from app.models.jwt_claims import Role  # noqa: E402


def create_test_agent_service(
    agent_repository=None,
    enforcement_repository=None,
):
    """Test helper creating an AgentService wired with concrete in-memory repositories."""
    from app.repositories.in_memory.agent_repository import InMemoryAgentRepository
    from app.repositories.in_memory.enforcement_state_repository import (
        InMemoryEnforcementStateRepository,
    )
    from app.services.agent_service import AgentService

    return AgentService(
        agent_repository=agent_repository or InMemoryAgentRepository(),
        enforcement_repository=enforcement_repository
        or InMemoryEnforcementStateRepository(),
    )


def create_test_audit_service(
    audit_repository=None,
):
    """Test helper creating an AuditService wired with concrete in-memory repository."""
    from app.repositories.in_memory.audit_evidence_repository import (
        InMemoryAuditEvidenceRepository,
    )
    from app.services.audit_service import AuditService

    return AuditService(
        audit_repository=audit_repository or InMemoryAuditEvidenceRepository(),
    )


def register_test_agent(
    agent_id: str,
    approved_tools: list[str] | None = None,
) -> str:
    """Register an agent dedicated to one test module, and return its id.

    Enforcement posture accumulates per agent across sessions (M2b), so HTTP tests that
    expect a quiet agent must not share ``agent-1`` with the modules that deliberately
    escalate it. Registration is additive: no shared state is cleared, and the
    accumulation this project now guarantees is left intact.
    """
    from app.api.dependencies import agent_service
    from app.models.agent import Agent, AgentStatus, RiskTier
    from app.services.agent_service import AgentAlreadyExistsError

    try:
        agent_service.register_agent(
            Agent(
                agent_id=agent_id,
                name=f"Test Agent ({agent_id})",
                owner="security-team",
                risk_tier=RiskTier.HIGH,
                approved_tools=approved_tools or ["file_read", "directory_list"],
                status=AgentStatus.ACTIVE,
            )
        )
    except AgentAlreadyExistsError:
        pass

    return agent_id


def create_test_jwt(
    agent_id: str = "admin-agent",
    role: Role = Role.ADMIN,
    subject: str = "test-admin",
) -> str:
    """Generate a valid signed JWT using the platform singleton jwt_service."""
    return jwt_service.create_token(
        subject=subject,
        agent_id=agent_id,
        role=role,
    )


def auth_headers(
    agent_id: str = "admin-agent",
    role: Role = Role.ADMIN,
    subject: str = "test-admin",
) -> dict[str, str]:
    """Generate HTTP Authorization headers containing a valid Bearer token."""
    token = create_test_jwt(agent_id=agent_id, role=role, subject=subject)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return auth_headers(role=Role.ADMIN)


@pytest.fixture
def agent_headers() -> dict[str, str]:
    return auth_headers(agent_id="agent-1", role=Role.AGENT)


@pytest.fixture
def analyst_headers() -> dict[str, str]:
    return auth_headers(role=Role.ANALYST)
