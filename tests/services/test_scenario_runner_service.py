from app.models.attack_scenario import AttackScenario
from app.models.risk_assessment import RiskLevel
from app.services.scenario_runner_service import (
    ScenarioRunnerService,
)
from tests.services.test_runtime_service import (
    create_runtime_service,
)



def test_run_normal_behavior_scenario():
    runtime_service, _ = create_runtime_service(
        ["file_read"]
    )
    runner = ScenarioRunnerService(runtime_service)

    scenario = AttackScenario(
        scenario_id="scenario-1",
        name="Normal Behavior",
        session_id="session-1",
        agent_id="agent-1",
        tool_sequence=["file_read"],
        expected_findings=[],
        expected_risk_level=RiskLevel.LOW,
    )

    result = runner.run(scenario)

    assert result.scenario_id == "scenario-1"
    assert result.passed is True
    assert result.observed_findings == []
    assert (
        result.observed_risk_level
        == RiskLevel.LOW
    )



def test_run_excessive_denial_scenario():
    runtime_service, _ = create_runtime_service([])
    runner = ScenarioRunnerService(runtime_service)

    scenario = AttackScenario(
        scenario_id="scenario-2",
        name="Excessive Denials",
        session_id="session-2",
        agent_id="agent-1",
        tool_sequence=[
            "file_read",
            "file_read",
            "file_read",
        ],
        expected_findings=["EXCESSIVE_DENIALS"],
        expected_risk_level=RiskLevel.MEDIUM,
    )

    result = runner.run(scenario)

    assert result.scenario_id == "scenario-2"
    assert result.passed is True
    assert result.observed_findings == [
        "EXCESSIVE_DENIALS"
    ]
    assert (
        result.observed_risk_level
        == RiskLevel.MEDIUM
    )