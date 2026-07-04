from collections.abc import Iterable

from app.detection.context import DetectionContext
from app.detection.rule import DetectionRule
from app.models.finding import Finding


class DetectionEngine:
    """Orchestrates rule execution without detection-specific logic."""

    def __init__(
        self,
        rules: Iterable[DetectionRule],
    ) -> None:
        self._rules = tuple(rules)

    def evaluate(
        self,
        context: DetectionContext,
    ) -> list[Finding]:
        findings: list[Finding] = []

        for rule in self._rules:
            findings.extend(rule.evaluate(context))

        return findings
