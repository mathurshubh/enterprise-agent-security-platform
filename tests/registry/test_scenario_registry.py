import pytest

from app.models.attack_scenario import AttackScenario, ScenarioCategory
from app.registry.scenario_registry import (
    ScenarioAlreadyExistsError,
    ScenarioNotFoundError,
    ScenarioRegistry,
)


def create_scenario(
    scenario_id: str = "attack-001",
    category: ScenarioCategory = ScenarioCategory.TOOL_ABUSE,
) -> AttackScenario:
    return AttackScenario(
        scenario_id=scenario_id,
        name="Unauthorized Tool Request",
        category=category,
    )


def test_register_and_get_scenario():
    registry = ScenarioRegistry()
    scenario = create_scenario()

    result = registry.register_scenario(scenario)

    assert result == scenario
    assert registry.get_scenario("attack-001") == scenario


def test_duplicate_scenario_rejected():
    registry = ScenarioRegistry()
    scenario = create_scenario()

    registry.register_scenario(scenario)

    with pytest.raises(ScenarioAlreadyExistsError):
        registry.register_scenario(scenario)


def test_get_unknown_scenario_raises_error():
    registry = ScenarioRegistry()

    with pytest.raises(ScenarioNotFoundError):
        registry.get_scenario("missing-scenario")


def test_list_scenarios_is_deterministic():
    registry = ScenarioRegistry(
        [
            create_scenario("attack-002"),
            create_scenario("attack-001"),
        ]
    )

    scenarios = registry.list_scenarios()

    assert [scenario.scenario_id for scenario in scenarios] == [
        "attack-001",
        "attack-002",
    ]


def test_list_by_category():
    registry = ScenarioRegistry(
        [
            create_scenario(
                "attack-001",
                ScenarioCategory.TOOL_ABUSE,
            ),
            create_scenario(
                "attack-002",
                ScenarioCategory.DATA_EXFILTRATION,
            ),
        ]
    )

    scenarios = registry.list_by_category(
        ScenarioCategory.DATA_EXFILTRATION
    )

    assert len(scenarios) == 1
    assert scenarios[0].scenario_id == "attack-002"
