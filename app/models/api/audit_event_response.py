from datetime import datetime

from pydantic import BaseModel, Field


class AuditEventResponse(BaseModel):
    """Management API representation of an immutable audit event.

    The timestamp field is a datetime object; FastAPI serialises it to an
    ISO-8601 string automatically.  Manual string conversion is avoided so
    that the serialisation format is governed by Pydantic's json_encoders
    configuration rather than ad-hoc formatting code.

    Tool identity is reported as the platform recorded it: what the request asked for,
    and separately what the security pipeline established. ``tool_id`` is deliberately
    nullable rather than echoing the request, so a consumer can tell a resolved tool from
    a claimed one — a distinction an evidence API cannot collapse without misreporting.
    """

    event_id: str
    session_id: str
    agent_id: str
    requested_tool_id: str = Field(
        description="The tool identity the request named, recorded as received."
    )
    tool_id: str | None = Field(
        default=None,
        description=(
            "Resolved tool-family identity, when tool resolution occurred. Null means "
            "the request was refused before any tool identity was established."
        ),
    )
    tool_version: str | None = Field(
        default=None,
        description=(
            "Resolved concrete tool version, when an implementation was established. "
            "Null where a family resolved but no implementation did."
        ),
    )
    decision: str
    timestamp: datetime
