import json
from pathlib import Path

from pydantic import ValidationError

from app.models.attack_scenario import AttackScenario, ScenarioCategory
from app.registry.scenario_registry import ScenarioRegistry


DEFAULT_SCENARIO_PATH = (
    Path(__file__).resolve().parents[1]
    / "scenarios"
    / "attack_scenarios.json"
)


class ScenarioLoadError(Exception):
    """Raised when attack scenario assets cannot be loaded."""


class AttackScenarioService:
    def __init__(
        self,
        scenario_path: Path | None = None,
    ) -> None:
        self._scenario_path = scenario_path or DEFAULT_SCENARIO_PATH

    def load_scenarios(
        self,
    ) -> list[AttackScenario]:
        try:
            raw_scenarios = json.loads(
                self._scenario_path.read_text(encoding="utf-8")
            )
        except OSError as exc:
            raise ScenarioLoadError(
                f"Unable to read scenario file '{self._scenario_path}'"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ScenarioLoadError(
                f"Scenario file '{self._scenario_path}' is not valid JSON"
            ) from exc

        if not isinstance(raw_scenarios, list):
            raise ScenarioLoadError(
                "Scenario file must contain a JSON list"
            )

        scenarios: list[AttackScenario] = []
        scenario_ids: set[str] = set()

        for raw_scenario in raw_scenarios:
            try:
                scenario = AttackScenario.model_validate(raw_scenario)
            except ValidationError as exc:
                raise ScenarioLoadError(
                    "Scenario file contains an invalid scenario"
                ) from exc

            if scenario.scenario_id in scenario_ids:
                raise ScenarioLoadError(
                    f"Duplicate scenario_id '{scenario.scenario_id}'"
                )

            scenario_ids.add(scenario.scenario_id)
            scenarios.append(scenario)

        return sorted(
            scenarios,
            key=lambda scenario: scenario.scenario_id,
        )

    def load_registry(
        self,
    ) -> ScenarioRegistry:
        return ScenarioRegistry(self.load_scenarios())

    def list_by_category(
        self,
        category: ScenarioCategory,
    ) -> list[AttackScenario]:
        return [
            scenario
            for scenario in self.load_scenarios()
            if scenario.category == category
        ]
