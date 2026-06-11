from pydantic import BaseModel

from app.models.finding import Finding
from app.models.response_action import ResponseAction
from app.models.risk_assessment import RiskAssessment
from app.models.session_event import SessionEvent


class RuntimeResult(BaseModel):
    event: SessionEvent
    findings: list[Finding]
    risk_assessment: RiskAssessment
    response_action: ResponseAction