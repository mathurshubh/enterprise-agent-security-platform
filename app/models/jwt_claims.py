from pydantic import BaseModel


class JWTClaims(BaseModel):
    sub: str
    agent_id: str
    role: str