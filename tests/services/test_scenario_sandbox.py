"""Scenario execution isolation (ADR-013, scenario isolation amendment).

A scenario deliberately drives the platform into states it is designed to punish, so
running one must not mutate live runtime state or enter the live behavioural telemetry
stream. These tests assert that boundary rather than the architecture describing it.
"""

from app.models.agent import AgentStatus
from app.models.attack_scenario import AttackScenario
from app.models.execution_status import ExecutionStatus
from app.models.risk_assessment import RiskLevel
from app.services.runtime_bootstrap import create_default_detection_registry
from app.services.scenario_runner_service import ScenarioRunnerService
from app.services.scenario_sandbox import SCENARIO_AGENT_ID, build_scenario_sandbox

# Three denied calls to an unregistered tool: crosses the denial threshold and records
# findings, risk and audit state. SES-002 exercises the same path.
DENIAL_SCENARIO = AttackScenario(
    scenario_id="sandbox-isolation-denials",
    name="Denial threshold",
    tool_sequence=["unauthorized_tool"] * 3,
    expected_detection="EXCESSIVE_DENIALS",
    expected_findings=["EXCESSIVE_DENIALS"],
    expected_risk=RiskLevel.MEDIUM,
)


class TestSandboxConstruction:
    def test_sandbox_state_is_not_shared_between_runs(self) -> None:
        first = build_scenario_sandbox()
        second = build_scenario_sandbox()

        assert first.agent_service is not second.agent_service
        assert first.session_service is not second.session_service
        assert first.findings_service is not second.findings_service
        assert first.risk_service is not second.risk_service
        assert first.audit_service is not second.audit_service
        assert first.tool_registry is not second.tool_registry
        assert first.execution_authority is not second.execution_authority
        assert first.execution_authority.authority_id != second.execution_authority.authority_id

    def test_sandbox_registers_the_expected_agent_and_emits_no_telemetry(self) -> None:
        sandbox = build_scenario_sandbox()

        agent = sandbox.agent_service.get_agent(SCENARIO_AGENT_ID)
        assert agent.status == AgentStatus.ACTIVE
        assert sandbox.runtime.telemetry_emitter is None

    def test_sandbox_shares_no_state_with_the_live_runtime(self) -> None:
        from app.api import dependencies

        sandbox = build_scenario_sandbox()

        assert sandbox.agent_service is not dependencies.agent_service
        assert sandbox.session_service is not dependencies.session_service
        assert sandbox.findings_service is not dependencies.findings_service
        assert sandbox.risk_service is not dependencies.risk_service
        assert sandbox.audit_service is not dependencies.audit_service
        assert sandbox.execution_authority is not dependencies.execution_authority
        assert sandbox.runtime is not dependencies.runtime_service


class TestScenarioRunIsolation:
    def test_run_does_not_mutate_live_runtime_state(self) -> None:
        from app.api import dependencies

        before = {
            "agent_status": dependencies.agent_service.get_agent("agent-1").status,
            "sessions": len(dependencies.session_service.list_sessions()),
            "session_events": len(
                dependencies.session_service.list_events("scenario-run-sandbox-isolation-denials")
            ),
            "findings": len(dependencies.findings_service.list_findings()),
            "risk": len(dependencies.risk_service.list_assessments()),
            "audit": len(dependencies.audit_service.list_events()),
            "telemetry_queued": dependencies.telemetry_dispatcher.queue_size,
            "telemetry_dropped": dependencies.telemetry_dispatcher.dropped_events_count,
        }

        execution = ScenarioRunnerService().run(DENIAL_SCENARIO)
        assert execution.status == ExecutionStatus.COMPLETED

        after = {
            "agent_status": dependencies.agent_service.get_agent("agent-1").status,
            "sessions": len(dependencies.session_service.list_sessions()),
            "session_events": len(
                dependencies.session_service.list_events("scenario-run-sandbox-isolation-denials")
            ),
            "findings": len(dependencies.findings_service.list_findings()),
            "risk": len(dependencies.risk_service.list_assessments()),
            "audit": len(dependencies.audit_service.list_events()),
            "telemetry_queued": dependencies.telemetry_dispatcher.queue_size,
            "telemetry_dropped": dependencies.telemetry_dispatcher.dropped_events_count,
        }

        assert after == before

    def test_run_records_evidence_inside_its_own_sandbox(self) -> None:
        sandboxes = []

        def factory():
            sandbox = build_scenario_sandbox()
            sandboxes.append(sandbox)
            return sandbox

        execution = ScenarioRunnerService(sandbox_factory=factory).run(DENIAL_SCENARIO)

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.result is not None
        assert "EXCESSIVE_DENIALS" in execution.result.observed_findings

        sandbox = sandboxes[0]
        assert len(sandbox.session_service.list_events(execution.session_id)) == 3
        assert len(sandbox.findings_service.list_findings()) == 1
        assert len(sandbox.audit_service.list_events()) == 3

    def test_each_run_starts_from_a_fresh_sandbox(self) -> None:
        sandboxes = []

        def factory():
            sandbox = build_scenario_sandbox()
            sandboxes.append(sandbox)
            return sandbox

        runner = ScenarioRunnerService(sandbox_factory=factory)
        first = runner.run(DENIAL_SCENARIO)
        second = runner.run(DENIAL_SCENARIO)

        assert len(sandboxes) == 2
        assert sandboxes[0] is not sandboxes[1]
        # A rerun accumulates no state from the previous run, so grading is identical.
        assert len(sandboxes[1].session_service.list_events(second.session_id)) == 3
        assert first.result.observed_risk_level == second.result.observed_risk_level
        assert first.result.observed_findings == second.result.observed_findings

    def test_injected_runtime_is_still_honoured(self) -> None:
        from tests.services.test_runtime_service import create_runtime_service

        runtime_service, session_service = create_runtime_service(["file_read"])
        scenario = AttackScenario(
            scenario_id="sandbox-injected-runtime",
            name="Injected runtime",
            tool_sequence=["file_read"],
            expected_findings=[],
            expected_risk=RiskLevel.LOW,
        )

        execution = ScenarioRunnerService(runtime_service=runtime_service).run(scenario)

        assert execution.status == ExecutionStatus.COMPLETED
        assert len(session_service.list_events(execution.session_id)) == 1


class TestDetectionRegistryFactory:
    """The factory moved from app.api.dependencies; behaviour must be unchanged."""

    def test_factory_rules_match_the_live_registry(self) -> None:
        from app.api import dependencies

        built = create_default_detection_registry()

        # Registration order and rule identity must be unchanged by the move.
        assert [rule.metadata.name for rule in built.rules()] == [
            rule.metadata.name for rule in dependencies.detection_registry.rules()
        ]
        assert [type(rule) for rule in built.rules()] == [
            type(rule) for rule in dependencies.detection_registry.rules()
        ]
        assert built.list_rule_names() == dependencies.detection_registry.list_rule_names()
        assert built.categories() == dependencies.detection_registry.categories()
        assert [m.name for m in built.metadata()] == [
            m.name for m in dependencies.detection_registry.metadata()
        ]

    def test_dependencies_still_exposes_the_factory(self) -> None:
        from app.api import dependencies

        assert dependencies.create_default_detection_registry is create_default_detection_registry

    def test_live_runtime_and_management_share_one_registry_instance(self) -> None:
        from app.api import dependencies

        assert (
            dependencies.runtime_service.detection_engine.list_rule_names()
            == dependencies.detection_registry.list_rule_names()
        )
