from app.detection.category import DetectionCategory
from app.detection.context import DetectionContext
from app.detection.engine import DetectionEngine
from app.detection.rule import DetectionRule
from app.models.finding import Finding, Severity


class StubRule(DetectionRule):
    def __init__(
        self,
        rule_name: str,
    ) -> None:
        self._rule_name = rule_name
        self.evaluated_contexts: list[DetectionContext] = []

    @property
    def rule_name(
        self,
    ) -> str:
        return self._rule_name

    @property
    def category(
        self,
    ) -> DetectionCategory:
        return DetectionCategory.PROMPT_SECURITY


    def evaluate(
        self,
        context: DetectionContext,
    ) -> list[Finding]:
        self.evaluated_contexts.append(context)
        return [
            Finding(
                finding_id=f"{self.rule_name}-finding",
                session_id=context.session_id,
                agent_id=context.agent_id,
                rule_name=self.rule_name,
                severity=Severity.LOW,
                description="stub finding",
            )
        ]


def create_context() -> DetectionContext:
    return DetectionContext(
        session_id="session-1",
        agent_id="agent-1",
        user_prompt="Summarize the report.",
    )


def test_detection_engine_runs_registered_rules_in_order():
    rule_1 = StubRule("RULE_ONE")
    rule_2 = StubRule("RULE_TWO")
    engine = DetectionEngine([rule_1, rule_2])
    context = create_context()

    findings = engine.evaluate(context)

    assert [finding.rule_name for finding in findings] == [
        "RULE_ONE",
        "RULE_TWO",
    ]
    assert rule_1.evaluated_contexts == [context]
    assert rule_2.evaluated_contexts == [context]


def test_detection_engine_supports_no_rules():
    engine = DetectionEngine([])

    findings = engine.evaluate(create_context())

    assert findings == []
