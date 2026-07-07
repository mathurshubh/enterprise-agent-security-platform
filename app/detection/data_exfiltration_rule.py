from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from app.detection.category import DetectionCategory
from app.detection.context import DetectionContext
from app.detection.metadata import RuleMetadata
from app.detection.rule import DetectionRule
from app.models.finding import Finding, Severity


class DataExfiltrationRule(DetectionRule):
    """Detects data exfiltration attempts based on presence of action and sensitive indicator."""

    _RULE_NAME = "DATA_EXFILTRATION"
    _CREATED_AT = datetime(1970, 1, 1, tzinfo=timezone.utc)

    EXFILTRATION_ACTIONS = (
        "upload",
        "send",
        "email",
        "post",
        "push",
        "copy",
        "export",
        "transfer",
        "sync",
        "publish",
        "share",
    )

    SENSITIVE_DATA_INDICATORS = (
        "password",
        "credentials",
        "token",
        "api key",
        "secret",
        "ssh key",
        ".env",
        "private key",
        "kubeconfig",
        "service account key",
    )

    @property
    def rule_name(self) -> str:
        return self._RULE_NAME

    @property
    def category(self) -> DetectionCategory:
        return DetectionCategory.DATA_SECURITY

    @property
    def metadata(self) -> RuleMetadata:
        from app.detection.security_standard import SecurityControlReference, SecurityFramework

        return RuleMetadata(
            name=self.rule_name,
            category=self.category,
            description="Detects data exfiltration attempts based on presence of action and sensitive indicator.",
            controls=(
                SecurityControlReference(
                    framework=SecurityFramework.MITRE_ATTACK,
                    control_id="T1048",
                    title="Exfiltration Over Alternative Protocol",
                ),
            ),
        )




    def evaluate(self, context: DetectionContext) -> list[Finding]:
        resource = context.metadata.get("resource", "").strip().casefold()
        user_prompt = context.user_prompt.casefold()

        search_content = f"{user_prompt} {resource}".strip()

        matched_action = None
        for action in self.EXFILTRATION_ACTIONS:
            if action in search_content:
                matched_action = action
                break

        matched_indicator = None
        for indicator in self.SENSITIVE_DATA_INDICATORS:
            if indicator in search_content:
                matched_indicator = indicator
                break

        if matched_action and matched_indicator:
            return [
                Finding(
                    finding_id=self._finding_id(context, matched_action, matched_indicator),
                    session_id=context.session_id,
                    agent_id=context.agent_id,
                    rule_name=self.rule_name,
                    severity=Severity.HIGH,
                    description=(
                        "Data exfiltration attempt detected: "
                        f"action '{matched_action}' combined with sensitive indicator '{matched_indicator}'"
                    ),
                    created_at=self._CREATED_AT,
                )
            ]

        return []

    def _finding_id(
        self,
        context: DetectionContext,
        action: str,
        indicator: str,
    ) -> str:
        raw_id = "|".join(
            (
                self.rule_name,
                context.session_id,
                context.agent_id,
                action,
                indicator,
            )
        )
        return str(uuid5(NAMESPACE_URL, raw_id))
