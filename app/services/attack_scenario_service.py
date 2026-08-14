from pathlib import Path

import yaml
from pydantic import ValidationError

from app.models.attack_scenario import AttackScenario, ScenarioCategory
from app.registry.scenario_registry import ScenarioRegistry

DEFAULT_SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios"


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
        target_files: list[Path] = []

        if self._scenario_path.is_dir():
            target_files = sorted(
                list(self._scenario_path.glob("*.yaml"))
                + list(self._scenario_path.glob("*.yml"))
            )
        elif self._scenario_path.is_file():
            target_files = [self._scenario_path]
        else:
            raise ScenarioLoadError(
                f"Scenario path '{self._scenario_path}' does not exist"
            )

        scenarios: list[AttackScenario] = []
        scenario_ids: set[str] = set()

        for file_path in target_files:
            try:
                content = file_path.read_text(encoding="utf-8")
                raw_scenarios = yaml.safe_load(content)
            except OSError as exc:
                raise ScenarioLoadError(
                    f"Unable to read scenario file '{file_path}'"
                ) from exc
            except yaml.YAMLError as exc:
                raise ScenarioLoadError(
                    f"Scenario file '{file_path}' is not valid YAML"
                ) from exc

            if raw_scenarios is None:
                continue

            if not isinstance(raw_scenarios, list):
                raise ScenarioLoadError(
                    f"Scenario file '{file_path}' must contain a YAML list"
                )

            for raw_scenario in raw_scenarios:
                if not isinstance(raw_scenario, dict):
                    raise ScenarioLoadError(
                        f"Scenario entry in '{file_path}' must be a mapping"
                    )

                try:
                    scenario = AttackScenario.model_validate(raw_scenario)
                except ValidationError as exc:
                    raise ScenarioLoadError(
                        f"Scenario file '{file_path}' contains an invalid scenario"
                    ) from exc

                normalized_id = scenario.scenario_id.lower()
                if normalized_id in scenario_ids:
                    raise ScenarioLoadError(
                        f"Duplicate scenario_id '{scenario.scenario_id}'"
                    )

                scenario_ids.add(normalized_id)
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
