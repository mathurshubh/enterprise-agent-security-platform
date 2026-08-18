from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingCategory(str, Enum):
    PROMPT_INJECTION = "PROMPT_INJECTION"
    DATA_EXFILTRATION = "DATA_EXFILTRATION"
    PRIVILEGE_ESCALATION = "PRIVILEGE_ESCALATION"
    UNAUTHORIZED_TOOL = "UNAUTHORIZED_TOOL"
    SENSITIVE_FILE_ACCESS = "SENSITIVE_FILE_ACCESS"
    BROWSER_ABUSE = "BROWSER_ABUSE"
    SECRET_LEAKAGE = "SECRET_LEAKAGE"
    MULTI_STEP_ATTACK = "MULTI_STEP_ATTACK"
    UNKNOWN = "UNKNOWN"


class FindingStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class Finding(BaseModel):
    finding_id: str
    session_id: str
    agent_id: str
    rule_id: str = ""
    rule_name: str
    severity: Severity
    category: FindingCategory = FindingCategory.UNKNOWN
    status: FindingStatus = FindingStatus.OPEN
    description: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def model_post_init(self, __context: Any) -> None:
        if not self.rule_id:
            self.rule_id = self.rule_name

