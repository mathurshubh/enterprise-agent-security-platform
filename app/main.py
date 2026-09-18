"""Application assembly and the plane-level authorization boundary (M3).

Each router is mounted with the widest role set its plane admits. ``require_roles``
depends on ``get_current_principal``, so authentication still runs first and an
unauthenticated request is refused with 401 before any role is considered.

    runtime      AGENT             + per-route execution identity binding
    scenarios    ANALYST, ADMIN
    management   ANALYST, ADMIN    + ADMIN on reinstatement
    health       public

Operators administer the platform; agents execute only as themselves; analysts
evaluate scenarios, which run in an isolated sandbox (ADR-013).
"""

from fastapi import Depends, FastAPI

from app.api.auth import require_roles
from app.api.health import router as health_router
from app.api.management import router as management_router
from app.api.runtime import router as runtime_router
from app.api.scenarios import router as scenarios_router
from app.models.jwt_claims import Role

app = FastAPI()

app.include_router(health_router)
app.include_router(
    runtime_router,
    dependencies=[Depends(require_roles(Role.AGENT))],
)
app.include_router(
    scenarios_router,
    prefix="/api",
    dependencies=[Depends(require_roles(Role.ANALYST, Role.ADMIN))],
)
app.include_router(
    management_router,
    prefix="/api/v1",
    dependencies=[Depends(require_roles(Role.ANALYST, Role.ADMIN))],
)
