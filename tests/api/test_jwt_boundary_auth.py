from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    agent_service,
    jwt_service,
    runtime_service,
    scenario_registry,
)
from app.auth.jwt_service import JWTService
from app.main import app
from app.models.jwt_claims import Role
from tests.conftest import create_test_jwt

client = TestClient(app)


class TestBoundaryAuthentication:
    """Test suite verifying strict JWT enforcement at the FastAPI HTTP boundary."""

    def test_unauthenticated_request_rejected_on_runtime(self) -> None:
        with patch.object(runtime_service, "execute") as mock_execute:
            response = client.post(
                "/agents/agent-1/execute",
                json={"session_id": "sess-1", "tool_id": "file_read"},
            )
            assert response.status_code == 401
            assert "www-authenticate" in response.headers
            assert response.headers["www-authenticate"] == "Bearer"
            mock_execute.assert_not_called()

    def test_unauthenticated_request_rejected_on_management(self) -> None:
        with patch.object(agent_service, "list_agents") as mock_list:
            response = client.get("/api/v1/agents")
            assert response.status_code == 401
            assert "www-authenticate" in response.headers
            assert response.headers["www-authenticate"] == "Bearer"
            mock_list.assert_not_called()

    def test_unauthenticated_request_rejected_on_scenarios(self) -> None:
        with patch.object(scenario_registry, "list_scenarios") as mock_list:
            response = client.get("/api/scenarios")
            assert response.status_code == 401
            assert "www-authenticate" in response.headers
            assert response.headers["www-authenticate"] == "Bearer"
            mock_list.assert_not_called()

    def test_health_endpoint_remains_public(self) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.parametrize(
        "header_value",
        [
            "Basic dXNlcjpwYXNz",
            "Token some-raw-token",
            "CustomScheme abc",
        ],
    )
    def test_malformed_auth_scheme_rejected(self, header_value: str) -> None:
        response = client.get("/api/v1/agents", headers={"Authorization": header_value})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_empty_bearer_token_rejected(self) -> None:
        response = client.get("/api/v1/agents", headers={"Authorization": "Bearer "})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_invalid_jwt_format_rejected(self) -> None:
        response = client.get("/api/v1/agents", headers={"Authorization": "Bearer not-a-valid-token"})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_expired_jwt_rejected(self) -> None:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-expired",
            "agent_id": "test-agent",
            "role": Role.ADMIN.value,
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
        }
        expired_token = jwt.encode(payload, jwt_service.secret_key, algorithm=jwt_service.algorithm)

        with patch.object(agent_service, "list_agents") as mock_list:
            response = client.get("/api/v1/agents", headers={"Authorization": f"Bearer {expired_token}"})
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == "Bearer"
            assert "expired" in response.json()["detail"].lower()
            mock_list.assert_not_called()

    def test_invalid_signature_rejected(self) -> None:
        wrong_service = JWTService(secret_key="completely-wrong-secret-key-at-least-32-bytes")
        forged_token = wrong_service.create_token(
            subject="forged-admin",
            agent_id="admin",
            role=Role.ADMIN,
        )

        with patch.object(agent_service, "list_agents") as mock_list:
            response = client.get("/api/v1/agents", headers={"Authorization": f"Bearer {forged_token}"})
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == "Bearer"
            mock_list.assert_not_called()

    def test_malformed_claims_structure_rejected(self) -> None:
        now = datetime.now(timezone.utc)
        # Missing required claims 'agent_id' and 'role'
        payload = {
            "sub": "incomplete-claims",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        token = jwt.encode(payload, jwt_service.secret_key, algorithm=jwt_service.algorithm)

        response = client.get("/api/v1/agents", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


class TestRuntimeAgentIdentityBinding:
    """Test suite verifying agent identity binding on POST /agents/{agent_id}/execute."""

    def test_agent_identity_mismatch_rejected_with_403(self) -> None:
        # Token issued for 'agent-1'
        token = create_test_jwt(agent_id="agent-1", role=Role.AGENT, subject="agent-1-sub")

        with patch.object(runtime_service, "execute") as mock_execute:
            # Caller attempts to execute on behalf of 'victim-agent'
            response = client.post(
                "/agents/victim-agent/execute",
                headers={"Authorization": f"Bearer {token}"},
                json={"session_id": "sess-1", "tool_id": "file_read"},
            )
            assert response.status_code == 403
            assert "mismatch" in response.json()["detail"].lower()
            mock_execute.assert_not_called()

    def test_analyst_cannot_invoke_agent_execution(self) -> None:
        token = create_test_jwt(agent_id="analyst-1", role=Role.ANALYST, subject="analyst-user")

        with patch.object(runtime_service, "execute") as mock_execute:
            response = client.post(
                "/agents/agent-1/execute",
                headers={"Authorization": f"Bearer {token}"},
                json={"session_id": "sess-1", "tool_id": "file_read"},
            )
            assert response.status_code == 403
            assert "analyst" in response.json()["detail"].lower()
            mock_execute.assert_not_called()

    def test_matching_agent_allowed_to_invoke_execution(self) -> None:
        token = create_test_jwt(agent_id="agent-1", role=Role.AGENT, subject="agent-1-sub")

        response = client.post(
            "/agents/agent-1/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={"session_id": "sess-1", "tool_id": "file_read"},
        )
        assert response.status_code == 200
        assert response.json()["agent_id"] == "agent-1"
        assert response.json()["decision"] == "ALLOW"

    def test_admin_allowed_to_invoke_execution_for_any_agent(self) -> None:
        token = create_test_jwt(agent_id="admin-agent", role=Role.ADMIN, subject="admin-sub")

        response = client.post(
            "/agents/agent-1/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={"session_id": "sess-admin", "tool_id": "file_read"},
        )
        assert response.status_code == 200
        assert response.json()["agent_id"] == "agent-1"


class TestOpenAPISecurityScheme:
    """Test suite verifying OpenAPI schema accurately exposes Bearer authentication."""

    def test_openapi_schema_contains_http_bearer(self) -> None:
        schema = app.openapi()
        assert "components" in schema
        assert "securitySchemes" in schema["components"]
        assert "HTTPBearer" in schema["components"]["securitySchemes"]
        bearer_scheme = schema["components"]["securitySchemes"]["HTTPBearer"]
        assert bearer_scheme["type"] == "http"
        assert bearer_scheme["scheme"] == "bearer"

    def test_protected_routes_advertise_security(self) -> None:
        schema = app.openapi()
        paths = schema["paths"]

        # Runtime execute route
        assert "/agents/{agent_id}/execute" in paths
        assert "post" in paths["/agents/{agent_id}/execute"]
        assert "security" in paths["/agents/{agent_id}/execute"]["post"]
        assert any("HTTPBearer" in sec for sec in paths["/agents/{agent_id}/execute"]["post"]["security"])

        # Management route
        assert "/api/v1/agents" in paths
        assert "get" in paths["/api/v1/agents"]
        assert "security" in paths["/api/v1/agents"]["get"]
        assert any("HTTPBearer" in sec for sec in paths["/api/v1/agents"]["get"]["security"])

        # Public health route
        assert "/health" in paths
        assert "get" in paths["/health"]
        assert "security" not in paths["/health"]["get"] or paths["/health"]["get"]["security"] == []
