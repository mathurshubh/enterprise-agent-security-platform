from pydantic import BaseModel, Field


class ToolOperational(BaseModel):
    """Operational configuration for a tool."""

    enabled: bool = True

    timeout_seconds: int = Field(
        default=30,
        ge=1,
        description="Maximum execution time."
    )

    supports_streaming: bool = False