"""Shared fixtures for the adversarial security regression corpus.

The corpus deliberately avoids mutating the shared application singletons in
``app.api.dependencies`` wherever a finding can be demonstrated at service level.
Two reasons:

1. ``AgentService`` exposes no writer, so an agent suspended by a future
   hardening milestone could never be restored for subsequent tests.
2. Existing suites assert filtered collection sizes against those singletons.

Tests that must exercise the HTTP boundary use read-only requests, unique
session identifiers, and delta assertions instead of absolute counts.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.auth.authorization_service import AuthorizationService
from app.detection.data_exfiltration_rule import DataExfiltrationRule
from app.detection.engine import DetectionEngine
from app.detection.prompt_injection_rule import PromptInjectionRule
from app.detection.registry import DetectionRegistry
from app.detection.sensitive_file_access_rule import SensitiveFileAccessRule
from app.models.agent import Agent, AgentStatus, RiskTier
from app.policy.policy_engine import PolicyEngine
from app.registry.tool_registry import ToolRegistry
from app.services.agent_service import AgentService
from app.services.audit_service import AuditService
from app.services.detection_service import DetectionService
from app.services.findings_service import FindingsService
from app.services.response_service import ResponseService
from app.services.risk_service import RiskService
from app.services.runtime_bootstrap import register_default_tools
from app.services.runtime_service import RuntimeService
from app.services.session_service import SessionService
from app.services.tool_service import ToolService
from app.tools.directory_list_tool import DirectoryListTool
from app.tools.file_read_tool import FileReadTool

PROTECTED_FILE = "secrets.txt"
BENIGN_FILE = "notes.txt"
PROTECTED_MARKER = "CORPUS_PROTECTED_VALUE"
BENIGN_MARKER = "CORPUS_BENIGN_VALUE"


@pytest.fixture
def security_workspace(tmp_path: Path) -> Path:
    """An isolated workspace containing one benign and one protected file."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / BENIGN_FILE).write_text(BENIGN_MARKER, encoding="utf-8")
    (workspace / PROTECTED_FILE).write_text(PROTECTED_MARKER, encoding="utf-8")
    return workspace


@pytest.fixture
def build_runtime():
    """Return a factory producing a fully isolated runtime security pipeline."""

    def _build(
        workspace: Path | None = None,
        agent_id: str = "corpus-agent",
        status: AgentStatus = AgentStatus.ACTIVE,
        risk_tier: RiskTier = RiskTier.HIGH,
    ) -> SimpleNamespace:
        agent_service = AgentService()
        agent_service.register_agent(
            Agent(
                agent_id=agent_id,
                name="Corpus Agent",
                owner="security-team",
                risk_tier=risk_tier,
                approved_tools=["file_read", "directory_list"],
                status=status,
            )
        )

        tool_registry = ToolRegistry()
        if workspace is not None:
            tool_registry.register(FileReadTool(str(workspace)))
            tool_registry.register(DirectoryListTool(str(workspace)))

        tool_service = ToolService(tool_registry=tool_registry)
        register_default_tools(tool_service)

        detection_registry = DetectionRegistry()
        detection_registry.register(PromptInjectionRule())
        detection_registry.register(SensitiveFileAccessRule())
        detection_registry.register(DataExfiltrationRule())

        audit_service = AuditService()
        session_service = SessionService()
        findings_service = FindingsService()
        risk_service = RiskService()

        runtime = RuntimeService(
            authorization_service=AuthorizationService(
                agent_service=agent_service,
                tool_service=tool_service,
                policy_engine=PolicyEngine(),
            ),
            session_service=session_service,
            detection_engine=DetectionEngine(detection_registry.rules()),
            detection_service=DetectionService(),
            risk_service=risk_service,
            response_service=ResponseService(),
            audit_service=audit_service,
            tool_registry=tool_registry,
            findings_service=findings_service,
        )

        return SimpleNamespace(
            runtime=runtime,
            agent_id=agent_id,
            agent_service=agent_service,
            audit_service=audit_service,
            session_service=session_service,
            findings_service=findings_service,
            risk_service=risk_service,
            tool_registry=tool_registry,
        )

    return _build
