import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from json import JSONDecodeError

from pydantic import ValidationError
from requests.exceptions import RequestException

from app.models.attack_scenario import AttackScenario
from app.models.execution_mode import ExecutionMode
from app.models.execution_status import ExecutionStatus
from app.models.scenario_execution import ScenarioExecution
from app.models.scenario_execution_result import ScenarioExecutionResult
from app.registry.tool_registry import ToolNotRegisteredError
from app.runtime.execution_authority import ExecutionBindingError
from app.runtime.tool_executor import ToolDisabledError, ToolExecutionError
from app.services.agent_runtime_service import AgentRuntimeService
from app.services.runtime_service import RuntimeService
from app.services.scenario_sandbox import (
    SCENARIO_AGENT_ID,
    ScenarioSandbox,
    build_scenario_sandbox,
)


class ScenarioRunnerService:
    """Orchestrates scenario execution and evaluates outcomes against expectations.

    Scenario runs are isolated by default (ADR-013, scenario isolation amendment):
    each run builds a throwaway pipeline through ``sandbox_factory`` and mutates only
    that state. A caller may still inject a specific ``runtime_service`` — tests do —
    in which case the caller owns the isolation decision.
    """

    # Sandbox-local: never a live agent identifier (see ``scenario_sandbox``).
    _RUNTIME_AGENT_ID = SCENARIO_AGENT_ID

    def __init__(
        self,
        runtime_service: RuntimeService | None = None,
        agent_runtime_service: AgentRuntimeService | None = None,
        sandbox_factory: Callable[[], ScenarioSandbox] = build_scenario_sandbox,
    ) -> None:
        self._runtime_service = runtime_service
        self._agent_runtime_service = agent_runtime_service
        self._sandbox_factory = sandbox_factory

    def _resolve_pipeline(self) -> tuple[RuntimeService, AgentRuntimeService]:
        """Return the runtime and agent loop this run executes against."""
        if self._runtime_service is not None:
            runtime = self._runtime_service
            agent_runtime = self._agent_runtime_service or AgentRuntimeService(
                runtime_service=runtime
            )
            return runtime, agent_runtime

        sandbox = self._sandbox_factory()
        agent_runtime = self._agent_runtime_service or AgentRuntimeService(
            runtime_service=sandbox.runtime,
            tool_registry=sandbox.tool_registry,
            agent_id=self._RUNTIME_AGENT_ID,
            execution_authority=sandbox.execution_authority,
        )
        return sandbox.runtime, agent_runtime

    def run(
        self,
        scenario: AttackScenario,
    ) -> ScenarioExecution:
        started_at = datetime.now(timezone.utc)
        execution_id = f"exec-{uuid.uuid4()}"
        # Unique per run. Deriving this from scenario_id made every re-run of a
        # scenario reuse the identifier, which the session/execution identity
        # investigation measured on the tool-sequence path. Prompt mode was already
        # unique because AgentRuntimeService generates its own session identifier,
        # and line ~115 reassigns this from the actual runtime result either way.
        session_id = f"scenario-run-{uuid.uuid4()}"
        runtime_service, agent_runtime_service = self._resolve_pipeline()

        # Determine Execution Mode: tool_sequence takes precedence for deterministic replays
        execution_mode = (
            ExecutionMode.TOOL_SEQUENCE
            if scenario.tool_sequence
            else (
                ExecutionMode.PROMPT
                if scenario.user_prompt.strip()
                else ExecutionMode.TOOL_SEQUENCE
            )
        )

        try:
            # ── 1. Execution Phase ───────────────────────────────────────────
            runtime_result = None

            if execution_mode == ExecutionMode.PROMPT:
                # Prompt Mode: route through the agent loop
                agent_runtime_service.execute(scenario.user_prompt)
                runtime_result = getattr(runtime_service, "_last_result", None)
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
                    runtime_result = runtime_service.execute(
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
            # A scenario refused at a trust boundary produces no assessment to grade.
            if runtime_result.response_action is None or runtime_result.risk_assessment is None:
                raise ValueError(
                    "Scenario request was refused before evaluation: "
                    f"{runtime_result.refusal_reason or 'unknown reason'}"
                )
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
                events = runtime_service._session_service.list_events(session_id)
                invoked_tools = [e.tool_id for e in events]
                if scenario.expected_tool_id not in invoked_tools:
                    mismatches.append(
                        f"tool: expected {scenario.expected_tool_id} to be invoked, "
                        f"observed invocations: {invoked_tools}"
                    )

            # D. Assert Detections / Findings
            if scenario.expected_detection is not None and scenario.expected_detection not in observed_findings:
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

        except (
            # Infrastructure & Provider exceptions:
            RequestException,
            JSONDecodeError,
            ValidationError,
            KeyError,
            RuntimeError,
            # Orchestration & Tool exceptions:
            ValueError,
            ToolNotRegisteredError,
            ToolExecutionError,
            ToolDisabledError,
            ExecutionBindingError,
        ) as e:
            # Orchestration fault-isolation boundary: catches narrowly scoped
            # provider network failures, parsing errors, tool execution errors, and
            # validation faults to return ScenarioExecution(status=FAILED) rather than
            # bubbling uncaught exceptions to the API router.
            is_provider_error = isinstance(e, RequestException) or "connection" in str(e).lower() or "connect" in str(e).lower()
            error_prefix = "PROVIDER_UNAVAILABLE" if is_provider_error else ""
            error_msg = f"{error_prefix}: {e}" if error_prefix else str(e)

            finished_at = datetime.now(timezone.utc)
            return ScenarioExecution(
                execution_id=execution_id,
                scenario_id=scenario.scenario_id,
                session_id=session_id,
                execution_mode=execution_mode,
                status=ExecutionStatus.FAILED,
                started_at=started_at,
                finished_at=finished_at,
                error_message=error_msg,
            )
