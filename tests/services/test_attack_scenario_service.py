import pytest
import yaml

from app.models.attack_scenario import ScenarioCategory
from app.models.risk_assessment import RiskLevel
from app.services.attack_scenario_service import (
    AttackScenarioService,
    ScenarioLoadError,
)


def write_scenarios(tmp_path, scenarios, filename="test_scenarios.yaml"):
    scenario_path = tmp_path / filename
    scenario_path.write_text(
        yaml.dump(scenarios),
        encoding="utf-8",
    )
    return scenario_path


def create_scenario(
    scenario_id: str = "AUTH-001",
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

    assert len(scenarios) == 14
    assert [scenario.scenario_id for scenario in scenarios] == sorted(
        scenario.scenario_id for scenario in scenarios
    )
    assert {
        ScenarioCategory.PROMPT_INJECTION,
        ScenarioCategory.DATA_EXFILTRATION,
        ScenarioCategory.AUTHORIZATION,
        ScenarioCategory.SENSITIVE_DATA,
        ScenarioCategory.TOOL_ABUSE,
        ScenarioCategory.PROVIDER_FAILURE,
        ScenarioCategory.SESSION_BEHAVIOR,
        ScenarioCategory.WORKFLOW_SECURITY,
        ScenarioCategory.BENIGN,
    }.issubset({scenario.category for scenario in scenarios})


def test_load_scenarios_returns_domain_models(tmp_path):
    scenario_path = write_scenarios(
        tmp_path,
        [
            create_scenario("AUTH-002"),
            create_scenario("AUTH-001"),
        ],
    )
    service = AttackScenarioService(scenario_path)

    scenarios = service.load_scenarios()

    assert [scenario.scenario_id for scenario in scenarios] == [
        "AUTH-001",
        "AUTH-002",
    ]
    assert scenarios[0].expected_risk == RiskLevel.HIGH


def test_load_multi_file_directory(tmp_path):
    write_scenarios(tmp_path, [create_scenario("PI-001", "PROMPT_INJECTION")], "prompt_injection.yaml")
    write_scenarios(tmp_path, [create_scenario("DEX-001", "DATA_EXFILTRATION")], "data_exfiltration.yaml")

    service = AttackScenarioService(tmp_path)
    scenarios = service.load_scenarios()

    assert len(scenarios) == 2
    assert [s.scenario_id for s in scenarios] == ["DEX-001", "PI-001"]


def test_load_registry_contains_loaded_scenarios(tmp_path):
    scenario_path = write_scenarios(
        tmp_path,
        [create_scenario("AUTH-001")],
    )
    service = AttackScenarioService(scenario_path)

    registry = service.load_registry()

    assert registry.get_scenario("AUTH-001").name == (
        "Unauthorized Tool Request"
    )


def test_load_duplicate_scenario_ids_raises_error(tmp_path):
    scenario_path = write_scenarios(
        tmp_path,
        [
            create_scenario("AUTH-001"),
            create_scenario("AUTH-001"),
        ],
    )
    service = AttackScenarioService(scenario_path)

    with pytest.raises(
        ScenarioLoadError,
        match="Duplicate scenario_id 'AUTH-001'",
    ):
        service.load_scenarios()


def test_load_invalid_yaml_raises_error(tmp_path):
    scenario_path = tmp_path / "test.yaml"
    scenario_path.write_text(":\n- invalid: [", encoding="utf-8")
    service = AttackScenarioService(scenario_path)

    with pytest.raises(
        ScenarioLoadError,
        match="not valid YAML",
    ):
        service.load_scenarios()


def test_load_non_list_yaml_raises_error(tmp_path):
    scenario_path = tmp_path / "test.yaml"
    scenario_path.write_text("key: value", encoding="utf-8")
    service = AttackScenarioService(scenario_path)

    with pytest.raises(
        ScenarioLoadError,
        match="must contain a YAML list",
    ):
        service.load_scenarios()


def test_load_duplicate_scenario_ids_across_files_raises_error(tmp_path):
    write_scenarios(tmp_path, [create_scenario("AUTH-001")], "file1.yaml")
    write_scenarios(tmp_path, [create_scenario("AUTH-001")], "file2.yaml")

    service = AttackScenarioService(tmp_path)

    with pytest.raises(
        ScenarioLoadError,
        match="Duplicate scenario_id 'AUTH-001'",
    ):
        service.load_scenarios()


def test_load_empty_yaml_file_handled_gracefully(tmp_path):
    empty_file = tmp_path / "empty.yaml"
    empty_file.write_text("# Only comments\n", encoding="utf-8")
    write_scenarios(tmp_path, [create_scenario("AUTH-001")], "scenarios.yaml")

    service = AttackScenarioService(tmp_path)
    scenarios = service.load_scenarios()

    assert len(scenarios) == 1
    assert scenarios[0].scenario_id == "AUTH-001"


def test_load_invalid_category_raises_error(tmp_path):
    scenario = create_scenario("INVALID-001")
    scenario["category"] = "NON_EXISTENT_CATEGORY"
    scenario_path = write_scenarios(tmp_path, [scenario])

    service = AttackScenarioService(scenario_path)

    with pytest.raises(
        ScenarioLoadError,
        match="contains an invalid scenario",
    ):
        service.load_scenarios()


def test_load_disabled_scenario_preserves_enabled_false(tmp_path):
    scenario = create_scenario("AUTH-001")
    scenario["enabled"] = False
    scenario_path = write_scenarios(tmp_path, [scenario])

    service = AttackScenarioService(scenario_path)
    scenarios = service.load_scenarios()

    assert len(scenarios) == 1
    assert scenarios[0].enabled is False


def test_list_by_category_filters_scenarios(tmp_path):
    scenario_path = write_scenarios(
        tmp_path,
        [
            create_scenario("AUTH-001", "TOOL_ABUSE"),
            create_scenario("DEX-001", "DATA_EXFILTRATION"),
        ],
    )
    service = AttackScenarioService(scenario_path)

    scenarios = service.list_by_category(ScenarioCategory.DATA_EXFILTRATION)

    assert len(scenarios) == 1
    assert scenarios[0].scenario_id == "DEX-001"
