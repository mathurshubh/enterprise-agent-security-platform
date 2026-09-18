"""Isolated execution pipeline for scenario runs (ADR-013, scenario isolation amendment).

Scenario execution is a security-test path, not a production runtime path. A scenario
deliberately drives the platform into states it is designed to punish — denial
thresholds, critical risk, agent suspension — so running one against the live pipeline
would let a test mutate production security state.

Every sandbox therefore owns its agent, session, findings, risk, audit, tool and
execution-grant state, and emits no behavioural telemetry. Only the scenario result
leaves the sandbox. Each run builds a fresh one, so repeated runs of the same scenario
start from the same state and grade identically.
"""

from dataclasses import dataclass

from app.registry.tool_registry import ToolRegistry
from app.runtime.execution_authority import ExecutionAuthority
from app.services.agent_service import AgentService
from app.services.audit_service import AuditService
from app.services.findings_service import FindingsService
from app.services.risk_service import RiskService
from app.services.runtime_bootstrap import (
    bootstrap_runtime_service,
    create_default_detection_registry,
)
from app.services.runtime_service import RuntimeService
from app.services.session_service import SessionService

# Scenario activity is attributed to the platform's default agent identifier, but the
# agent record itself belongs to the sandbox and never reaches the live registry.
SCENARIO_AGENT_ID = "agent-1"


@dataclass(frozen=True)
class ScenarioSandbox:
    """One scenario run's isolated pipeline and the state it is allowed to mutate."""

    runtime: RuntimeService
    agent_service: AgentService
    session_service: SessionService
    findings_service: FindingsService
    risk_service: RiskService
    audit_service: AuditService
    tool_registry: ToolRegistry
    execution_authority: ExecutionAuthority


def build_scenario_sandbox(agent_id: str = SCENARIO_AGENT_ID) -> ScenarioSandbox:
    """Build a throwaway pipeline that shares no state with the live runtime."""
    agent_service = AgentService()
    session_service = SessionService()
    audit_service = AuditService()
    findings_service = FindingsService()
    risk_service = RiskService()
    tool_registry = ToolRegistry()
    execution_authority = ExecutionAuthority()

    runtime = bootstrap_runtime_service(
        agent_service=agent_service,
        session_service=session_service,
        audit_service=audit_service,
        detection_registry=create_default_detection_registry(),
        agent_id=agent_id,
        tool_registry=tool_registry,
        findings_service=findings_service,
        risk_service=risk_service,
        # No telemetry emitter: synthetic security-test activity must not enter the
        # live behavioural telemetry stream, where consumers could not distinguish it
        # from real runtime activity.
        telemetry_emitter=None,
        execution_authority=execution_authority,
    )

    return ScenarioSandbox(
        runtime=runtime,
        agent_service=agent_service,
        session_service=session_service,
        findings_service=findings_service,
        risk_service=risk_service,
        audit_service=audit_service,
        tool_registry=tool_registry,
        execution_authority=execution_authority,
    )
