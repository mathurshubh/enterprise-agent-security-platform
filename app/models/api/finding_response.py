from datetime import datetime

from pydantic import BaseModel

from app.models.finding import FindingCategory, FindingStatus, Severity


class FindingResponse(BaseModel):
    """Management API representation of a security finding.

    Aligns with the frontend contract defined in frontend/src/types/finding.ts.
    Exposes MITRE ATT&CK technique IDs resolved from active detection rule metadata.
    """

    id: str
    session_id: str
    agent_id: str
    rule_id: str
    rule_name: str
    severity: Severity
    category: FindingCategory
    status: FindingStatus
    description: str
    detected_at: datetime
    mitre_techniques: list[str] = []
