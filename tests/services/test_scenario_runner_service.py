from datetime import datetime
from app.models.attack_scenario import AttackScenario
from app.models.execution_mode import ExecutionMode
from app.models.execution_status import ExecutionStatus
from app.models.scenario_execution import ScenarioExecution
from app.models.scenario_execution_result import ScenarioExecutionResult
from app.models.response_action import ResponseType
from app.models.risk_assessment import RiskLevel
from app.services.agent_runtime_service import AgentRuntimeService
from app.services.scenario_runner_service import ScenarioRunnerService
from app.models.agent_runtime_result import AgentRuntimeResult
from tests.services.test_runtime_service import (
    create_runtime_service,
)


class MockAgentRuntimeService(AgentRuntimeService):
    """Stub implementation of AgentRuntimeService to mock prompt execution in tests."""

    def __init__(self, runtime_service, mock_tool_id="file_read"):
        self._runtime_service = runtime_service
        self._mock_tool_id = mock_tool_id

    def execute(self, query: str) -> AgentRuntimeResult:
        # Simulate agent parsing prompt and invoking the tool on runtime_service
        result = self._runtime_service.execute(
            session_id="scenario-run-scenario-prompt-1",
            agent_id="agent-1",
            tool_id=self._mock_tool_id,
            user_prompt=query,
        )
        return AgentRuntimeResult(
            decision=result.event.decision.value,
            response_type=result.response_action.response_type,
            output="mock output",
        )


def test_execution_models_instantiation():
    """Verify all new execution-related models can be instantiated and type-checked."""
    result = ScenarioExecutionResult(
        passed=True,
        observed_decision="ALLOW",
        observed_response="MONITOR",
        observed_risk_level="LOW",
        observed_findings=[],
        mismatches=[],
    )
    execution = ScenarioExecution(
        execution_id="exec-123",
        scenario_id="scenario-1",
        session_id="session-123",
        execution_mode=ExecutionMode.TOOL_SEQUENCE,
        status=ExecutionStatus.COMPLETED,
        started_at=datetime.utcnow(),
        result=result,
    )
    assert execution.execution_id == "exec-123"
    assert execution.result.passed is True
    assert execution.execution_mode == ExecutionMode.TOOL_SEQUENCE
    assert execution.status == ExecutionStatus.COMPLETED


def test_run_normal_behavior_scenario():
    runtime_service, session_service = create_runtime_service(
        ["file_read"]
    )
    runner = ScenarioRunnerService(runtime_service)

    scenario = AttackScenario(
        scenario_id="scenario-1",
        name="Normal Behavior",
        tool_sequence=["file_read"],
        expected_findings=[],
        expected_risk_level=RiskLevel.LOW,
    )

    result = runner.run(scenario)

    assert result.scenario_id == "scenario-1"
    assert result.status == ExecutionStatus.COMPLETED
    assert result.execution_mode == ExecutionMode.TOOL_SEQUENCE
    assert result.result is not None
    assert result.result.passed is True
    assert result.result.observed_findings == []
    assert result.result.observed_risk_level == "LOW"
    assert len(session_service.list_events("scenario-run-scenario-1")) == 1


def test_run_excessive_denial_scenario():
    runtime_service, session_service = create_runtime_service([])
    runner = ScenarioRunnerService(runtime_service)

    scenario = AttackScenario(
        scenario_id="scenario-2",
        name="Excessive Denials",
        tool_sequence=[
            "file_read",
            "file_read",
            "file_read",
        ],
        expected_findings=["EXCESSIVE_DENIALS"],
        expected_risk_level=RiskLevel.MEDIUM,
        expected_response=ResponseType.ALERT,
    )

    result = runner.run(scenario)

    assert result.scenario_id == "scenario-2"
    assert result.status == ExecutionStatus.COMPLETED
    assert result.result is not None
    assert result.result.passed is True
    assert result.result.observed_findings == ["EXCESSIVE_DENIALS"]
    assert result.result.observed_risk_level == "MEDIUM"
    assert len(session_service.list_events("scenario-run-scenario-2")) == 3


def test_run_grading_mismatch():
    runtime_service, _ = create_runtime_service([])
    runner = ScenarioRunnerService(runtime_service)

    # Expect MONITOR, but pipeline will output ALERT due to excessive denials
    scenario = AttackScenario(
        scenario_id="scenario-2-mismatch",
        name="Excessive Denials Mismatch",
        tool_sequence=[
            "file_read",
            "file_read",
            "file_read",
        ],
        expected_findings=["EXCESSIVE_DENIALS"],
        expected_risk_level=RiskLevel.MEDIUM,
        expected_response=ResponseType.MONITOR,
    )

    result = runner.run(scenario)

    assert result.status == ExecutionStatus.COMPLETED
    assert result.result is not None
    assert result.result.passed is False
    assert len(result.result.mismatches) > 0
    assert any("response: expected MONITOR, observed ALERT" in m for m in result.result.mismatches)


def test_run_empty_scenario_fails_gracefully():
    runtime_service, _ = create_runtime_service(["file_read"])
    runner = ScenarioRunnerService(runtime_service)

    scenario = AttackScenario(
        scenario_id="scenario-3",
        name="Empty Scenario",
        tool_sequence=[],
        expected_findings=[],
        expected_risk_level=RiskLevel.LOW,
    )

    result = runner.run(scenario)

    assert result.status == ExecutionStatus.FAILED
    assert result.result is None
    assert result.error_message is not None
    assert "Scenario must contain at least one tool invocation" in result.error_message


def test_run_prompt_execution_mode():
    runtime_service, session_service = create_runtime_service(["file_read"])
    mock_agent_service = MockAgentRuntimeService(runtime_service)
    runner = ScenarioRunnerService(
        runtime_service=runtime_service,
        agent_runtime_service=mock_agent_service,
    )

    scenario = AttackScenario(
        scenario_id="scenario-prompt-1",
        name="Prompt Behavior",
        user_prompt="Read the file secrets.txt",
        expected_tool_id="file_read",
        expected_findings=[],
        expected_risk_level=RiskLevel.LOW,
    )

    result = runner.run(scenario)

    assert result.status == ExecutionStatus.COMPLETED
    assert result.execution_mode == ExecutionMode.PROMPT
    assert result.result is not None
    assert result.result.passed is True
    assert len(session_service.list_events("scenario-run-scenario-prompt-1")) == 1


def test_shared_runtime_service_consistency():
    """Verify that both runner and agent runtime service mutate the same state."""
    from app.api.dependencies import runtime_service as shared_runtime
    mock_agent = MockAgentRuntimeService(shared_runtime)
    runner_with_mock = ScenarioRunnerService(shared_runtime, mock_agent)

    scenario = AttackScenario(
        scenario_id="shared-consistency-check",
        name="Consistency Check",
        user_prompt="Run query",
        expected_tool_id="file_read",
        expected_findings=[],
        expected_risk_level=RiskLevel.LOW,
    )

    result = runner_with_mock.run(scenario)
    assert result.status == ExecutionStatus.COMPLETED
    
    # Assert event exists in shared session_service state
    events = shared_runtime._session_service.list_events(result.session_id)
    assert len(events) == 1
    assert events[0].tool_id == "file_read"
