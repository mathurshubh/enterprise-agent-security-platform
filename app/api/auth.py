"""
Authentication and authorization dependencies for FastAPI boundary enforcement.

Every request is authenticated before it reaches application services or the
runtime pipeline, and, since M3, authorized there too. Authorization is applied at
the router mount points in ``app.main``, where FastAPI composes router-level and
route-level dependencies as an intersection::

    mount-level dependency   →  the widest role set this plane admits
    route-level dependency   →  narrowing, where one capability is more privileged

A route can therefore only ever narrow the plane it belongs to, never widen it, so
adding a route cannot silently grant access that its plane does not already allow.
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


def require_execution_identity(
    agent_id: str,
    principal: JWTClaims = Depends(get_current_principal),
) -> JWTClaims:
    """Bind runtime execution to the authenticated agent's own identity (M3).

    Execution identity and administrative identity are not interchangeable. An
    operator's authority to *manage* an agent is not authority to *act as* one:
    activity attributed to an agent accumulates into that agent's enforcement
    posture and can contain it (ADR-024), so executing on another agent's behalf
    would mean generating behavioural evidence against a subject one does not own.

        permitted  ⟺  role is AGENT  ∧  principal.agent_id == agent_id

    Expressed as a single positive rule rather than a set of denials, so no role
    reaches the runtime pipeline by falling through a gap between special cases.

    The identity comparison is independently meaningful: the mount admits the AGENT
    role but says nothing about *which* agent a principal may act as. The role check
    above it is redundant under the current mount contract, which already guarantees
    AGENT, and is kept so that this dependency stays correct if it is ever applied to
    a route outside the runtime mount.
    """
    if principal.role != Role.AGENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{principal.role.value}' is not authorized to execute agent "
                "runtime actions"
            ),
        )

    if principal.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Agent identity mismatch: token agent_id '{principal.agent_id}' "
                f"does not match path agent_id '{agent_id}'"
            ),
        )

    return principal
