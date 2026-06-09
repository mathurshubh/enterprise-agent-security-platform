from enum import Enum

from pydantic import BaseModel

from app.models.agent import RiskTier


class ModelStatus(str, Enum):
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    DEPRECATED = "DEPRECATED"


class Model(BaseModel):
    model_id: str
    provider: str
    version: str
    owner: str
    description: str | None = None
    status: ModelStatus
    risk_tier: RiskTier