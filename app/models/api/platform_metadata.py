from pydantic import BaseModel, Field


class PlatformMetadataResponse(BaseModel):
    """Platform release identity metadata."""

    name: str = Field(
        description="Official name of the platform."
    )
    version: str = Field(
        description="Canonical semantic release version of the running platform."
    )
