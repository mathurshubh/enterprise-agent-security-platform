from enum import Enum

from pydantic import BaseModel


class Role(str, Enum):
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    AGENT = "AGENT"


class JWTClaims(BaseModel):
    sub: str
    agent_id: str
    role: Role
    iat: int
    exp: int