from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.management import router as management_router
from app.api.runtime import router as runtime_router


app = FastAPI()

app.include_router(health_router)
app.include_router(runtime_router)
app.include_router(management_router, prefix="/api/v1")
