from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from app.detection.category import DetectionCategory
from app.detection.context import DetectionContext
from app.detection.rule import DetectionRule
from app.models.finding import Finding, Severity


class PromptInjectionRule(DetectionRule):
    """Detects common deterministic prompt injection indicators."""

    _RULE_NAME = "PROMPT_INJECTION"
    _CREATED_AT = datetime(1970, 1, 1, tzinfo=timezone.utc)
    _INDICATORS = (
        "ignore previous instructions",
        "system prompt",
        "you are now",
        "act as system",
        "developer message",
        "forget your instructions",
        "override your instructions",
        "new role",
    )

    @property
    def rule_name(
        self,
    ) -> str:
        return self._RULE_NAME

    @property
    def category(
        self,
    ) -> DetectionCategory:
        return DetectionCategory.PROMPT_SECURITY


    def evaluate(
        self,
        context: DetectionContext,
    ) -> list[Finding]:
        matched_indicator = self._first_indicator(context)

        if matched_indicator is None:
            return []

        return [
            Finding(
                finding_id=self._finding_id(
                    context,
                    matched_indicator,
                ),
                session_id=context.session_id,
                agent_id=context.agent_id,
                rule_name=self.rule_name,
                severity=Severity.HIGH,
                description=(
                    "Prompt injection indicator detected: "
                    f"{matched_indicator}"
                ),
                created_at=self._CREATED_AT,
            )
        ]

    def _first_indicator(
        self,
        context: DetectionContext,
    ) -> str | None:
        normalized_inputs = " ".join(
            value.casefold()
            for value in context.text_inputs()
        )

        for indicator in self._INDICATORS:
            if indicator in normalized_inputs:
                return indicator

        return None

    def _finding_id(
        self,
        context: DetectionContext,
        indicator: str,
    ) -> str:
        raw_id = "|".join(
            (
                self.rule_name,
                context.session_id,
                context.agent_id,
                indicator,
            )
        )
        return str(uuid5(NAMESPACE_URL, raw_id))
