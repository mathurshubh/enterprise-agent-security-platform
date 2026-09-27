"""Application assembly and the plane-level authorization boundary (M3).

Each router is mounted with the widest role set its plane admits. ``require_roles``
depends on ``get_current_principal``, so authentication still runs first and an
unauthenticated request is refused with 401 before any role is considered.

    runtime      AGENT             + per-route execution identity binding
    scenarios    ANALYST, ADMIN
    management   ANALYST, ADMIN    + ADMIN on reinstatement
    health       public
    version      public

Operators administer the platform; agents execute only as themselves; analysts
evaluate scenarios, which run in an isolated sandbox (ADR-013).
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI

from app.api.auth import require_roles
from app.api.dependencies import execution_reconciler
from app.api.health import router as health_router
from app.api.management import router as management_router
from app.api.runtime import router as runtime_router
from app.api.scenarios import router as scenarios_router
from app.api.version import router as version_router
from app.models.jwt_claims import Role


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Recover the execution evidence plane before the application becomes ready.

    A process that died mid-execution leaves STARTED receipts whose outcome nobody
    observed. Reconciliation resolves them to UNKNOWN (ADR-032 N3-5, M4-7): a missing
    outcome is preserved as unknown rather than converted into success or failure.

    Ordering is the point. This runs inside the lifespan startup phase, so the
    application is not ready and serves no request until it returns — no live execution
    can enter the execution boundary while stale receipts are still unresolved. Running
    it at import time instead would make that ordering an accidental consequence of
    module import order, which becomes fragile once evidence is durable, workers are
    plural, and readiness probes exist.

    Reconciliation is synchronous today and is called synchronously here rather than
    dispatched as an unawaited task: a task would let the application report ready while
    recovery was still in flight, which is the failure this hook exists to prevent.

    A reconciliation failure propagates and fails startup. Coming up anyway would leave
    the platform serving requests with an unrecovered evidence plane, which is the
    condition the recovery boundary exists to rule out.
    """
    execution_reconciler.reconcile_on_startup(datetime.now(timezone.utc))
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(health_router)
app.include_router(version_router)
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
