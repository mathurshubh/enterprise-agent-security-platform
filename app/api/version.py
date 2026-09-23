from fastapi import APIRouter

from app.models.api.platform_metadata import PlatformMetadataResponse
from app.version import PLATFORM_NAME, get_platform_version

router = APIRouter()


@router.get(
    "/version",
    response_model=PlatformMetadataResponse,
    summary="Platform version",
)
def version() -> PlatformMetadataResponse:
    """Return canonical platform release metadata.

    Exposes the platform name and semantic release version without authentication,
    enabling public discovery, monitoring, and frontend build compatibility validation.
    Health status is deliberately distinct and served at /health.
    """
    return PlatformMetadataResponse(
        name=PLATFORM_NAME,
        version=get_platform_version(),
    )
