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
