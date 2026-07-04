import json

import pytest

from app.models.attack_scenario import ScenarioCategory
from app.models.risk_assessment import RiskLevel
from app.services.attack_scenario_service import (
    AttackScenarioService,
    ScenarioLoadError,
)


def write_scenarios(tmp_path, scenarios):
    scenario_path = tmp_path / "attack_scenarios.json"
    scenario_path.write_text(
        json.dumps(scenarios),
        encoding="utf-8",
    )
    return scenario_path


def create_scenario(
    scenario_id: str = "attack-001",
    category: str = "TOOL_ABUSE",
):
    return {
        "scenario_id": scenario_id,
        "name": "Unauthorized Tool Request",
        "description": "A user asks for an unauthorized tool.",
        "category": category,
        "severity": "HIGH",
        "user_prompt": "Delete the restricted report.",
        "expected_tool_id": "file_delete",
        "expected_detection": "UNAUTHORIZED_TOOL_REQUEST",
        "expected_risk": "HIGH",
        "expected_response": "REQUIRE_APPROVAL",
        "tags": ["tool-abuse"],
    }


def test_load_packaged_attack_scenarios():
    service = AttackScenarioService()

    scenarios = service.load_scenarios()

    assert len(scenarios) == 8
    assert [scenario.scenario_id for scenario in scenarios] == sorted(
        scenario.scenario_id for scenario in scenarios
    )
    assert {
        ScenarioCategory.PROMPT_INJECTION,
        ScenarioCategory.DATA_EXFILTRATION,
        ScenarioCategory.RUNTIME_REPLAY,
    }.issubset({scenario.category for scenario in scenarios})


def test_load_scenarios_returns_domain_models(tmp_path):
    scenario_path = write_scenarios(
        tmp_path,
        [
            create_scenario("attack-002"),
            create_scenario("attack-001"),
        ],
    )
    service = AttackScenarioService(scenario_path)

    scenarios = service.load_scenarios()

    assert [scenario.scenario_id for scenario in scenarios] == [
        "attack-001",
        "attack-002",
    ]
    assert scenarios[0].expected_risk == RiskLevel.HIGH


def test_load_registry_contains_loaded_scenarios(tmp_path):
    scenario_path = write_scenarios(
        tmp_path,
        [create_scenario("attack-001")],
    )
    service = AttackScenarioService(scenario_path)

    registry = service.load_registry()

    assert registry.get_scenario("attack-001").name == (
        "Unauthorized Tool Request"
    )


def test_load_duplicate_scenario_ids_raises_error(tmp_path):
    scenario_path = write_scenarios(
        tmp_path,
        [
            create_scenario("attack-001"),
            create_scenario("attack-001"),
        ],
    )
    service = AttackScenarioService(scenario_path)

    with pytest.raises(
        ScenarioLoadError,
        match="Duplicate scenario_id 'attack-001'",
    ):
        service.load_scenarios()


def test_load_invalid_json_raises_error(tmp_path):
    scenario_path = tmp_path / "attack_scenarios.json"
    scenario_path.write_text("{", encoding="utf-8")
    service = AttackScenarioService(scenario_path)

    with pytest.raises(
        ScenarioLoadError,
        match="not valid JSON",
    ):
        service.load_scenarios()


def test_load_non_list_json_raises_error(tmp_path):
    scenario_path = tmp_path / "attack_scenarios.json"
    scenario_path.write_text("{}", encoding="utf-8")
    service = AttackScenarioService(scenario_path)

    with pytest.raises(
        ScenarioLoadError,
        match="must contain a JSON list",
    ):
        service.load_scenarios()


def test_list_by_category_filters_scenarios(tmp_path):
    scenario_path = write_scenarios(
        tmp_path,
        [
            create_scenario("attack-001", "TOOL_ABUSE"),
            create_scenario("attack-002", "DATA_EXFILTRATION"),
        ],
    )
    service = AttackScenarioService(scenario_path)

    scenarios = service.list_by_category(ScenarioCategory.DATA_EXFILTRATION)

    assert len(scenarios) == 1
    assert scenarios[0].scenario_id == "attack-002"
