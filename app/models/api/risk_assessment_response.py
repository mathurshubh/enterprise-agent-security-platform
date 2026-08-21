from datetime import datetime

from pydantic import BaseModel

from app.models.risk_assessment import RiskLevel


class RiskAssessmentResponse(BaseModel):
    """Management API representation of a dynamic risk assessment.

    Exposes non-authoritative process-local derived risk posture.
    Aligns with frontend contracts (frontend/src/types/riskAssessment.ts).
    """

    session_id: str
    agent_id: str
    risk_score: int
    risk_level: RiskLevel
    finding_count: int
    assessed_at: datetime
