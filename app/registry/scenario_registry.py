from threading import RLock

from app.models.attack_scenario import AttackScenario, ScenarioCategory


class ScenarioAlreadyExistsError(Exception):
    """Raised when attempting to register an existing scenario."""


class ScenarioNotFoundError(Exception):
    """Raised when a scenario cannot be found."""


class ScenarioRegistry:
    def __init__(
        self,
        scenarios: list[AttackScenario] | None = None,
    ) -> None:
        self._scenarios: dict[str, AttackScenario] = {}
        self._lock = RLock()

        for scenario in scenarios or []:
            self.register_scenario(scenario)

    def register_scenario(
        self,
        scenario: AttackScenario,
    ) -> AttackScenario:
        with self._lock:
            if scenario.scenario_id in self._scenarios:
                raise ScenarioAlreadyExistsError(
                    f"Scenario '{scenario.scenario_id}' already exists"
                )

            self._scenarios[scenario.scenario_id] = scenario
            return scenario

    def get_scenario(
        self,
        scenario_id: str,
    ) -> AttackScenario:
        with self._lock:
            try:
                return self._scenarios[scenario_id]
            except KeyError as exc:
                raise ScenarioNotFoundError(
                    f"Scenario '{scenario_id}' not found"
                ) from exc

    def list_scenarios(
        self,
    ) -> list[AttackScenario]:
        with self._lock:
            return [
                self._scenarios[scenario_id]
                for scenario_id in sorted(self._scenarios)
            ]

    def list_by_category(
        self,
        category: ScenarioCategory,
    ) -> list[AttackScenario]:
        with self._lock:
            return [
                scenario
                for scenario in self.list_scenarios()
                if scenario.category == category
            ]
