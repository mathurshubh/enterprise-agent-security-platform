from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from app.detection.category import DetectionCategory
from app.detection.context import DetectionContext
from app.detection.metadata import RuleMetadata
from app.detection.rule import DetectionRule
from app.models.finding import Finding, Severity


class SensitiveFileAccessRule(DetectionRule):
    """Detects access to sensitive files based on metadata resource path and user prompt."""

    _RULE_NAME = "SENSITIVE_FILE_ACCESS"
    _CREATED_AT = datetime(1970, 1, 1, tzinfo=timezone.utc)

    # Class-level constant containing the indicators for sensitive file access
    SENSITIVE_INDICATORS = (
        ".env",
        ".git/config",
        ".ssh/id_rsa",
        ".aws/credentials",
        "/etc/passwd",
        "/etc/shadow",
        "kubernetes secrets",
        "kubernetes secret",
        "k8s secrets",
        "k8s secret",
        "service account keys",
        "service account key",
        "service_account_keys",
        "service_account_key",
    )

    @property
    def rule_name(self) -> str:
        return self._RULE_NAME

    @property
    def category(self) -> DetectionCategory:
        return DetectionCategory.DATA_SECURITY

    @property
    def metadata(self) -> RuleMetadata:
        return RuleMetadata(
            name=self.rule_name,
            category=self.category,
            description="Detects access to sensitive files based on metadata resource path and user prompt.",
        )



    def evaluate(self, context: DetectionContext) -> list[Finding]:
        resource = context.metadata.get("resource", "").strip().casefold()
        user_prompt = context.user_prompt.casefold()

        matched_indicator = None

        # Check the metadata resource path first
        if resource:
            for indicator in self.SENSITIVE_INDICATORS:
                if indicator in resource:
                    matched_indicator = indicator
                    break

        # If not matched, check the user prompt
        if not matched_indicator and user_prompt:
            for indicator in self.SENSITIVE_INDICATORS:
                if indicator in user_prompt:
                    matched_indicator = indicator
                    break

        if matched_indicator is None:
            return []

        return [
            Finding(
                finding_id=self._finding_id(context, matched_indicator),
                session_id=context.session_id,
                agent_id=context.agent_id,
                rule_name=self.rule_name,
                severity=Severity.HIGH,
                description=f"Sensitive file access attempt detected: {matched_indicator}",
                created_at=self._CREATED_AT,
            )
        ]

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
