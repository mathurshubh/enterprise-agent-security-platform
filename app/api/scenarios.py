from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import runtime_service, scenario_registry
from app.models.api.scenario_execution_response import ScenarioExecutionResponse
from app.models.api.scenario_response import ScenarioResponse
from app.models.attack_scenario import AttackScenario
from app.registry.scenario_registry import ScenarioNotFoundError
from app.services.scenario_runner_service import ScenarioRunnerService

router = APIRouter(prefix="/scenarios", tags=["Scenarios"])


def _scenario_to_response(scenario: AttackScenario) -> ScenarioResponse:
    """Map an AttackScenario domain object to the API DTO."""
    expected_tools: list[str] = []
    if scenario.expected_tool_id is not None:
        expected_tools.append(scenario.expected_tool_id)

    expected_detection_rules: list[str] = []
    if scenario.expected_detection is not None:
        expected_detection_rules.append(scenario.expected_detection)

    return ScenarioResponse(
        scenario_id=scenario.scenario_id,
        name=scenario.name,
        description=scenario.description,
        category=scenario.category.value,
        severity=scenario.severity.value,
        prompt=scenario.user_prompt,
        expected_tools=expected_tools,
        expected_detection_rules=expected_detection_rules,
        expected_response=scenario.expected_response.value,
        expected_risk=scenario.expected_risk.value,
        expected_findings=list(scenario.expected_findings),
        tool_sequence=list(scenario.tool_sequence),
        tags=list(scenario.tags),
        enabled=scenario.enabled,
        version=scenario.scenario_version,
        schema_version=scenario.schema_version,
    )


@router.get(
    "",
    response_model=list[ScenarioResponse],
    summary="List registered scenarios",
)
def list_scenarios(
    category: str | None = Query(default=None, description="Filter by category"),
    severity: str | None = Query(default=None, description="Filter by severity"),
    tag: str | None = Query(default=None, description="Filter by tag"),
    enabled: bool | None = Query(default=None, description="Filter by enabled status"),
) -> list[ScenarioResponse]:
    """Return metadata for all security scenarios registered in the platform."""
    scenarios = scenario_registry.list_scenarios()

    if category is not None:
        category_upper = category.upper()
        scenarios = [s for s in scenarios if s.category.value == category_upper]

    if severity is not None:
        severity_upper = severity.upper()
        scenarios = [s for s in scenarios if s.severity.value == severity_upper]

    if tag is not None:
        scenarios = [s for s in scenarios if tag in s.tags]

    if enabled is not None:
        scenarios = [s for s in scenarios if s.enabled == enabled]

    return [_scenario_to_response(scenario) for scenario in scenarios]


@router.get(
    "/{scenario_id}",
    response_model=ScenarioResponse,
    summary="Get scenario by ID",
)
def get_scenario(scenario_id: str) -> ScenarioResponse:
    """Return a single attack scenario by its stable identifier."""
    try:
        scenario = scenario_registry.get_scenario(scenario_id)
    except ScenarioNotFoundError as err:
        raise HTTPException(
            status_code=404, detail=f"Scenario '{scenario_id}' not found"
        ) from err
    return _scenario_to_response(scenario)


@router.post(
    "/{scenario_id}/execute",
    response_model=ScenarioExecutionResponse,
    summary="Execute a security scenario",
)
def execute_scenario(scenario_id: str) -> ScenarioExecutionResponse:
    """Execute a scenario through the deterministic Runtime Security Pipeline."""
    try:
        scenario = scenario_registry.get_scenario(scenario_id)
    except ScenarioNotFoundError as err:
        raise HTTPException(
            status_code=404, detail=f"Scenario '{scenario_id}' not found"
        ) from err

    runner = ScenarioRunnerService(runtime_service=runtime_service)
    execution = runner.run(scenario)

    passed: bool | None = None
    observed_decision: str | None = None
    observed_response: str | None = None
    observed_risk_level: str | None = None
    observed_findings: list[str] = []
    mismatches: list[str] = []

    if execution.result is not None:
        passed = execution.result.passed
        observed_decision = execution.result.observed_decision
        observed_response = execution.result.observed_response
        observed_risk_level = execution.result.observed_risk_level
        observed_findings = execution.result.observed_findings
        mismatches = execution.result.mismatches

    return ScenarioExecutionResponse(
        execution_id=execution.execution_id,
        scenario_id=execution.scenario_id,
        session_id=execution.session_id,
        execution_mode=execution.execution_mode.value,
        status=execution.status.value,
        passed=passed,
        observed_decision=observed_decision,
        observed_response=observed_response,
        observed_risk_level=observed_risk_level,
        observed_findings=observed_findings,
        mismatches=mismatches,
        error_message=execution.error_message,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
    )
