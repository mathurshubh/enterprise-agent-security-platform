"""
Shared pytest fixtures and test helpers for authentication and API testing.
"""

import pytest

from app.api.dependencies import jwt_service
from app.models.jwt_claims import Role


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
