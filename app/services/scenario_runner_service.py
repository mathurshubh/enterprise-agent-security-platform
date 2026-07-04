from app.models.attack_scenario import AttackScenario
from app.models.scenario_result import ScenarioResult
from app.services.runtime_service import RuntimeService


class ScenarioRunnerService:
    _RUNTIME_AGENT_ID = "agent-1"

    def __init__(
        self,
        runtime_service: RuntimeService,
    ) -> None:
        self._runtime_service = runtime_service

    def run(
        self,
        scenario: AttackScenario,
    ) -> ScenarioResult:
        runtime_result = None
        session_id = f"scenario-run-{scenario.scenario_id}"

        for tool_id in scenario.tool_sequence:
            runtime_result = self._runtime_service.execute(
                session_id=session_id,
                agent_id=self._RUNTIME_AGENT_ID,
                tool_id=tool_id,
            )

        if runtime_result is None:
            raise ValueError(
                "Scenario must contain at least one tool invocation"
            )

        observed_findings = [
            finding.rule_name
            for finding in runtime_result.findings
        ]

        passed = (
            observed_findings
            == list(scenario.expected_findings)
            and runtime_result.risk_assessment.risk_level
            == scenario.expected_risk_level
        )

        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            passed=passed,
            observed_findings=observed_findings,
            observed_risk_level=(
                runtime_result.risk_assessment.risk_level
            ),
        )
