"""
Authentication dependencies for FastAPI boundary enforcement.

This module provides FastAPI security dependencies to enforce JWT Bearer
token authentication across platform API routers, ensuring every request
is authenticated before reaching application services or the runtime pipeline.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.dependencies import jwt_service
from app.models.jwt_claims import JWTClaims, Role

http_bearer = HTTPBearer(auto_error=False)


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> JWTClaims:
    """Validate Bearer JWT and return the authenticated principal claims.

    Fails closed with HTTP 401 Unauthorized and 'WWW-Authenticate: Bearer' header
    if credentials are missing, malformed, expired, have an invalid signature,
    or contain invalid claims structure.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme; Bearer scheme required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip() if credentials.credentials else ""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = jwt_service.verify_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return claims


def require_roles(*allowed_roles: Role):
    """Factory dependency restricting endpoint access to specific roles."""

    def role_checker(
        principal: JWTClaims = Depends(get_current_principal),
    ) -> JWTClaims:
        if principal.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{principal.role.value}' is not authorized for this resource",
            )
        return principal

    return role_checker
