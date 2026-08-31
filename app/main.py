from fastapi import Depends, FastAPI

from app.api.auth import get_current_principal
from app.api.health import router as health_router
from app.api.management import router as management_router
from app.api.runtime import router as runtime_router
from app.api.scenarios import router as scenarios_router

app = FastAPI()

app.include_router(health_router)
app.include_router(
    runtime_router,
    dependencies=[Depends(get_current_principal)],
)
app.include_router(
    scenarios_router,
    prefix="/api",
    dependencies=[Depends(get_current_principal)],
)
app.include_router(
    management_router,
    prefix="/api/v1",
    dependencies=[Depends(get_current_principal)],
)
