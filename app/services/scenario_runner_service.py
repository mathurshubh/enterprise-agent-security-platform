import uuid
from datetime import datetime, timezone

from app.models.attack_scenario import AttackScenario
from app.models.execution_mode import ExecutionMode
from app.models.execution_status import ExecutionStatus
from app.models.scenario_execution import ScenarioExecution
from app.models.scenario_execution_result import ScenarioExecutionResult
from app.services.agent_runtime_service import AgentRuntimeService
from app.services.runtime_service import RuntimeService


class ScenarioRunnerService:
    """Orchestrates scenario execution and evaluates outcomes against expectations."""

    _RUNTIME_AGENT_ID = "agent-1"

    def __init__(
        self,
        runtime_service: RuntimeService,
        agent_runtime_service: AgentRuntimeService | None = None,
    ) -> None:
        self._runtime_service = runtime_service
        self._agent_runtime_service = agent_runtime_service or AgentRuntimeService(
            runtime_service=runtime_service
        )

    def run(
        self,
        scenario: AttackScenario,
    ) -> ScenarioExecution:
        started_at = datetime.now(timezone.utc)
        execution_id = f"exec-{uuid.uuid4()}"
        session_id = f"scenario-run-{scenario.scenario_id}"

        # Determine Execution Mode based on prompt presence
        execution_mode = (
            ExecutionMode.PROMPT
            if scenario.user_prompt.strip()
            else ExecutionMode.TOOL_SEQUENCE
        )

        try:
            # ── 1. Execution Phase ───────────────────────────────────────────
            runtime_result = None

            if execution_mode == ExecutionMode.PROMPT:
                # Prompt Mode: route through the agent loop
                self._agent_runtime_service.execute(scenario.user_prompt)
                runtime_result = getattr(self._runtime_service, "_last_result", None)
                if runtime_result is None:
                    raise ValueError(
                        "Failed to capture runtime execution results from agent run"
                    )

            elif execution_mode == ExecutionMode.TOOL_SEQUENCE:
                # Tool Sequence Mode: direct pipeline execution
                if not scenario.tool_sequence:
                    raise ValueError(
                        "Scenario must contain at least one tool invocation"
                    )

                for tool_id in scenario.tool_sequence:
                    runtime_result = self._runtime_service.execute(
                        session_id=session_id,
                        agent_id=self._RUNTIME_AGENT_ID,
                        tool_id=tool_id,
                        user_prompt=scenario.user_prompt,
                    )

            # ── 2. Grading / Assertions Phase ────────────────────────────────
            session_id = runtime_result.event.session_id
            observed_findings = [
                finding.rule_name
                for finding in runtime_result.findings
            ]

            observed_decision = runtime_result.event.decision.value
            observed_response = runtime_result.response_action.response_type.value
            observed_risk_level = runtime_result.risk_assessment.risk_level.value

            mismatches = []

            # A. Assert Response Recommendation
            if runtime_result.response_action.response_type != scenario.expected_response:
                mismatches.append(
                    f"response: expected {scenario.expected_response.value}, "
                    f"observed {runtime_result.response_action.response_type.value}"
                )

            # B. Assert Risk Level
            if runtime_result.risk_assessment.risk_level != scenario.expected_risk:
                mismatches.append(
                    f"risk: expected {scenario.expected_risk.value}, "
                    f"observed {runtime_result.risk_assessment.risk_level.value}"
                )

            # C. Assert Tool ID (if expected)
            if scenario.expected_tool_id is not None:
                # Verify if the expected tool was invoked in the session events
                events = self._runtime_service._session_service.list_events(session_id)
                invoked_tools = [e.tool_id for e in events]
                if scenario.expected_tool_id not in invoked_tools:
                    mismatches.append(
                        f"tool: expected {scenario.expected_tool_id} to be invoked, "
                        f"observed invocations: {invoked_tools}"
                    )

            # D. Assert Detections / Findings
            if scenario.expected_detection is not None:
                if scenario.expected_detection not in observed_findings:
                    mismatches.append(
                        f"detection: expected {scenario.expected_detection} in findings, "
                        f"observed findings: {observed_findings}"
                    )

            for expected_finding in scenario.expected_findings:
                if expected_finding not in observed_findings:
                    mismatches.append(
                        f"finding: expected {expected_finding} in findings, "
                        f"observed findings: {observed_findings}"
                    )

            passed = len(mismatches) == 0

            result = ScenarioExecutionResult(
                passed=passed,
                observed_decision=observed_decision,
                observed_response=observed_response,
                observed_risk_level=observed_risk_level,
                observed_findings=observed_findings,
                mismatches=mismatches,
            )

            finished_at = datetime.now(timezone.utc)
            return ScenarioExecution(
                execution_id=execution_id,
                scenario_id=scenario.scenario_id,
                session_id=session_id,
                execution_mode=execution_mode,
                status=ExecutionStatus.COMPLETED,
                started_at=started_at,
                finished_at=finished_at,
                result=result,
            )

        except Exception as e:
            finished_at = datetime.now(timezone.utc)
            return ScenarioExecution(
                execution_id=execution_id,
                scenario_id=scenario.scenario_id,
                session_id=session_id,
                execution_mode=execution_mode,
                status=ExecutionStatus.FAILED,
                started_at=started_at,
                finished_at=finished_at,
                error_message=str(e),
            )
