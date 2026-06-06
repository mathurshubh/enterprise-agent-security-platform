import pytest

from app.auth.jwt_service import JWTService
from app.models.jwt_claims import Role


def test_create_token():
    service = JWTService("test-secret-key-at-least-32-bytes-long")

    token = service.create_token(
        subject="agent-service",
        agent_id="soc-agent",
        role=Role.AGENT,
    )

    assert isinstance(token, str)
    assert len(token) > 0


def test_verify_token():
    service = JWTService("test-secret-key-at-least-32-bytes-long")

    token = service.create_token(
        subject="agent-service",
        agent_id="soc-agent",
        role=Role.AGENT,
    )

    claims = service.verify_token(token)

    assert claims.agent_id == "soc-agent"
    assert claims.role == Role.AGENT


def test_invalid_token():
    service = JWTService("test-secret-key-at-least-32-bytes-long")

    with pytest.raises(Exception):
        service.verify_token("invalid-token")