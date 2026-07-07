from app.detection.category import DetectionCategory
from app.detection.metadata import RuleMetadata
from app.detection.rule import DetectionRule


class DetectionRegistry:
    """Manages the discovery, registration, and metadata lookup of detection rules."""

    def __init__(self) -> None:
        self._rules: dict[str, DetectionRule] = {}

    def register(self, rule: DetectionRule) -> DetectionRule:
        rule_name = rule.metadata.name
        if rule_name in self._rules:
            raise ValueError(f"Rule '{rule_name}' is already registered")
        self._rules[rule_name] = rule
        return rule

    def get(self, rule_name: str) -> DetectionRule:
        if rule_name not in self._rules:
            raise KeyError(f"Rule '{rule_name}' is not registered")
        return self._rules[rule_name]

    def rules(self) -> list[DetectionRule]:
        return list(self._rules.values())

    def categories(self) -> set[DetectionCategory]:
        return {rule.metadata.category for rule in self._rules.values()}

    def metadata(self) -> list[RuleMetadata]:
        return [rule.metadata for rule in self._rules.values()]
