"""Request body for administrative reinstatement (M2b)."""

from pydantic import BaseModel, Field, field_validator


class ReinstateRequest(BaseModel):
    """Why an operator is returning a contained agent to service.

    The actor is taken from the authenticated principal, never from the request body:
    a caller cannot attribute its own action to someone else.
    """

    reason: str = Field(min_length=1, description="Why the agent is being reinstated")

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value
