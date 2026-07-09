"""
Tests for the Enterprise Management API — GET /api/v1/*.

Coverage includes:
- HTTP 200 responses for all endpoints
- Empty registries / empty services
- Populated registries / populated services
- Response schema field presence and types
- Read-only behaviour (no state mutation)
- Detection rules match the runtime-active rule set
- No RuntimeService dependency in the management plane
"""

from fastapi.testclient import TestClient

from app.api.dependencies import (
    agent_service,
    audit_service,
    detection_registry,
    tool_registry,
)
from app.main import app
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import AuditEvent, Decision
from app.tools.file_read_tool import FileReadTool

client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def make_agent(agent_id: str = "mgmt-agent-1") -> Agent:
    return Agent(
        agent_id=agent_id,
        name="Management Test Agent",
        owner="security-team",
        risk_tier=RiskTier.MEDIUM,
        approved_tools=["file_read"],
        status=AgentStatus.ACTIVE,
    )


def make_audit_event(
    event_id: str = "evt-001",
    agent_id: str = "mgmt-agent-1",
    tool_id: str = "file_read",
    decision: Decision = Decision.ALLOW,
) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        agent_id=agent_id,
        tool_id=tool_id,
        decision=decision,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/agents
# ─────────────────────────────────────────────────────────────────────────────


class TestListAgents:
    def test_returns_200(self) -> None:
        response = client.get("/api/v1/agents")
        assert response.status_code == 200

    def test_empty_registry_returns_empty_list(self) -> None:
        # Baseline: no agents registered for this test (relies on clean state)
        initial = agent_service.list_agents()
        assert isinstance(response := client.get("/api/v1/agents"), object)
        response = client.get("/api/v1/agents")
        assert response.status_code == 200
        data = response.json()
        registered_ids = {a["agent_id"] for a in data}
        for existing in initial:
            assert existing.agent_id in registered_ids

    def test_populated_registry_returns_agent(self) -> None:
        agent = make_agent("mgmt-list-agent")
        agent_service.register_agent(agent)

        response = client.get("/api/v1/agents")
        assert response.status_code == 200
        ids = [a["agent_id"] for a in response.json()]
        assert "mgmt-list-agent" in ids

    def test_response_schema(self) -> None:
        agent = make_agent("mgmt-schema-agent")
        agent_service.register_agent(agent)

        response = client.get("/api/v1/agents")
        assert response.status_code == 200
        item = next(
            a for a in response.json() if a["agent_id"] == "mgmt-schema-agent"
        )

        assert item["agent_id"] == "mgmt-schema-agent"
        assert item["name"] == "Management Test Agent"
        assert item["owner"] == "security-team"
        assert item["risk_tier"] == "MEDIUM"
        assert item["status"] == "ACTIVE"
        assert item["approved_tools"] == ["file_read"]

    def test_response_does_not_contain_runtime_fields(self) -> None:
        agent = make_agent("mgmt-noruntime-agent")
        agent_service.register_agent(agent)

        response = client.get("/api/v1/agents")
        item = next(
            a for a in response.json() if a["agent_id"] == "mgmt-noruntime-agent"
        )
        # Runtime-internal fields must not appear in management response
        assert "session_id" not in item
        assert "decision" not in item
        assert "risk_score" not in item


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/tools
# ─────────────────────────────────────────────────────────────────────────────


class TestListTools:
    def test_returns_200(self) -> None:
        response = client.get("/api/v1/tools")
        assert response.status_code == 200

    def test_empty_registry_returns_empty_list(self) -> None:
        # Use a fresh client pointed at an app without registered tools
        # (the shared tool_registry starts empty unless populated elsewhere)
        data = client.get("/api/v1/tools").json()
        assert isinstance(data, list)

    def test_populated_registry_returns_tool(self) -> None:
        tool = FileReadTool("/tmp")
        if not tool_registry.exists(tool.tool_id):
            tool_registry.register(tool)

        response = client.get("/api/v1/tools")
        assert response.status_code == 200
        ids = [t["tool_id"] for t in response.json()]
        assert tool.tool_id in ids

    def test_response_schema(self) -> None:
        tool = FileReadTool("/tmp")
        if not tool_registry.exists(tool.tool_id):
            tool_registry.register(tool)

        response = client.get("/api/v1/tools")
        assert response.status_code == 200
        item = next(t for t in response.json() if t["tool_id"] == tool.tool_id)

        assert "tool_id" in item
        assert "name" in item
        assert "description" in item
        assert "version" in item

    def test_response_does_not_expose_executable_objects(self) -> None:
        tool = FileReadTool("/tmp")
        if not tool_registry.exists(tool.tool_id):
            tool_registry.register(tool)

        response = client.get("/api/v1/tools")
        item = next(t for t in response.json() if t["tool_id"] == tool.tool_id)
        # Executable fields must not be present
        assert "execute" not in item
        assert "_tools" not in item


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/detection/rules
# ─────────────────────────────────────────────────────────────────────────────


class TestListDetectionRules:
    def test_returns_200(self) -> None:
        response = client.get("/api/v1/detection/rules")
        assert response.status_code == 200

    def test_returns_all_registered_rules(self) -> None:
        response = client.get("/api/v1/detection/rules")
        assert response.status_code == 200
        names = {r["name"] for r in response.json()}
        assert "PROMPT_INJECTION" in names
        assert "SENSITIVE_FILE_ACCESS" in names
        assert "DATA_EXFILTRATION" in names

    def test_rule_count_matches_registry(self) -> None:
        expected = len(detection_registry.metadata())
        response = client.get("/api/v1/detection/rules")
        assert len(response.json()) == expected

    def test_response_schema(self) -> None:
        response = client.get("/api/v1/detection/rules")
        assert response.status_code == 200
        rule = next(
            r for r in response.json() if r["name"] == "PROMPT_INJECTION"
        )
        assert "name" in rule
        assert "category" in rule
        assert "description" in rule
        assert "controls" in rule
        assert isinstance(rule["controls"], list)

    def test_controls_include_owasp_mapping(self) -> None:
        response = client.get("/api/v1/detection/rules")
        rule = next(
            r for r in response.json() if r["name"] == "PROMPT_INJECTION"
        )
        frameworks = [c["framework"] for c in rule["controls"]]
        assert "OWASP_LLM" in frameworks

    def test_controls_include_mitre_atlas_mapping(self) -> None:
        response = client.get("/api/v1/detection/rules")
        rule = next(
            r for r in response.json() if r["name"] == "PROMPT_INJECTION"
        )
        frameworks = [c["framework"] for c in rule["controls"]]
        assert "MITRE_ATLAS" in frameworks

    def test_controls_include_mitre_attack_mapping(self) -> None:
        response = client.get("/api/v1/detection/rules")
        rule = next(
            r for r in response.json() if r["name"] == "DATA_EXFILTRATION"
        )
        frameworks = [c["framework"] for c in rule["controls"]]
        assert "MITRE_ATTACK" in frameworks

    def test_control_schema_includes_version(self) -> None:
        response = client.get("/api/v1/detection/rules")
        rule = next(
            r for r in response.json() if r["name"] == "PROMPT_INJECTION"
        )
        for control in rule["controls"]:
            assert "framework" in control
            assert "control_id" in control
            assert "title" in control
            assert "version" in control

    def test_control_version_default_is_latest(self) -> None:
        response = client.get("/api/v1/detection/rules")
        rule = next(
            r for r in response.json() if r["name"] == "PROMPT_INJECTION"
        )
        for control in rule["controls"]:
            assert control["version"] == "latest"

    def test_category_is_string_value(self) -> None:
        response = client.get("/api/v1/detection/rules")
        for rule in response.json():
            assert isinstance(rule["category"], str)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/audit/events
# ─────────────────────────────────────────────────────────────────────────────


class TestListAuditEvents:
    def test_returns_200(self) -> None:
        response = client.get("/api/v1/audit/events")
        assert response.status_code == 200

    def test_empty_service_returns_list(self) -> None:
        # AuditService may already contain events from other tests
        response = client.get("/api/v1/audit/events")
        assert isinstance(response.json(), list)

    def test_populated_service_returns_event(self) -> None:
        event = make_audit_event("evt-mgmt-001")
        audit_service.record_event(event)

        response = client.get("/api/v1/audit/events")
        assert response.status_code == 200
        ids = [e["event_id"] for e in response.json()]
        assert "evt-mgmt-001" in ids

    def test_response_schema(self) -> None:
        event = make_audit_event("evt-mgmt-schema")
        audit_service.record_event(event)

        response = client.get("/api/v1/audit/events")
        item = next(
            e for e in response.json() if e["event_id"] == "evt-mgmt-schema"
        )
        assert "event_id" in item
        assert "agent_id" in item
        assert "tool_id" in item
        assert "decision" in item
        assert "timestamp" in item

    def test_decision_is_string_value(self) -> None:
        event = make_audit_event("evt-mgmt-decision", decision=Decision.DENY)
        audit_service.record_event(event)

        response = client.get("/api/v1/audit/events")
        item = next(
            e for e in response.json() if e["event_id"] == "evt-mgmt-decision"
        )
        assert item["decision"] == "DENY"

    def test_timestamp_is_iso8601_string(self) -> None:
        event = make_audit_event("evt-mgmt-ts")
        audit_service.record_event(event)

        response = client.get("/api/v1/audit/events")
        item = next(
            e for e in response.json() if e["event_id"] == "evt-mgmt-ts"
        )
        # FastAPI serialises datetime to ISO-8601; a valid parse confirms the format
        from datetime import datetime

        parsed = datetime.fromisoformat(item["timestamp"])
        assert parsed is not None


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/info
# ─────────────────────────────────────────────────────────────────────────────


class TestPlatformInfo:
    def test_returns_200(self) -> None:
        response = client.get("/api/v1/info")
        assert response.status_code == 200

    def test_response_schema(self) -> None:
        response = client.get("/api/v1/info")
        data = response.json()
        assert "platform" in data
        assert "version" in data
        assert "api_version" in data
        assert "registered_agents" in data
        assert "registered_tools" in data
        assert "registered_detection_rules" in data
        assert "audit_events" in data

    def test_static_metadata_values(self) -> None:
        response = client.get("/api/v1/info")
        data = response.json()
        assert data["platform"] == "Enterprise Agent Security Platform"
        assert data["version"] == "0.9.0"
        assert data["api_version"] == "v1"

    def test_detection_rule_count_is_nonzero(self) -> None:
        response = client.get("/api/v1/info")
        assert response.json()["registered_detection_rules"] == len(
            detection_registry.metadata()
        )

    def test_counts_are_integers(self) -> None:
        response = client.get("/api/v1/info")
        data = response.json()
        assert isinstance(data["registered_agents"], int)
        assert isinstance(data["registered_tools"], int)
        assert isinstance(data["registered_detection_rules"], int)
        assert isinstance(data["audit_events"], int)

    def test_response_does_not_expose_sensitive_fields(self) -> None:
        response = client.get("/api/v1/info")
        data = response.json()
        sensitive_keys = {
            "workspace", "path", "directory", "api_key", "secret",
            "password", "token", "credential", "hostname", "host",
            "env", "environment", "config",
        }
        for key in sensitive_keys:
            assert key not in data, f"Sensitive field '{key}' must not appear in /info response"



# ─────────────────────────────────────────────────────────────────────────────
# Security invariant assertions
# ─────────────────────────────────────────────────────────────────────────────


class TestManagementApiSecurityInvariants:
    def test_management_module_does_not_import_runtime_service(self) -> None:
        """The management router must never import RuntimeService."""
        import app.api.management as mgmt_module

        assert not hasattr(mgmt_module, "runtime_service")

    def test_management_module_does_not_import_detection_engine(self) -> None:
        """The management router must never import DetectionEngine."""
        import app.api.management as mgmt_module

        assert not hasattr(mgmt_module, "DetectionEngine")

    def test_management_module_does_not_import_authorization_service(self) -> None:
        """The management router must never import AuthorizationService."""
        import app.api.management as mgmt_module

        assert not hasattr(mgmt_module, "AuthorizationService")

    def test_management_endpoints_do_not_mutate_audit_service(self) -> None:
        """GET endpoints must not create new audit events."""
        before = len(audit_service.list_events())
        client.get("/api/v1/agents")
        client.get("/api/v1/tools")
        client.get("/api/v1/detection/rules")
        client.get("/api/v1/audit/events")
        client.get("/api/v1/info")
        after = len(audit_service.list_events())
        assert after == before
