from fastapi import FastAPI

from .api.routes.onboarding import router as onboarding_router
from .api.routes.checkin import router as checkin_router
from .core.llm import initialize_env


def create_app() -> FastAPI:
    initialize_env()
    application = FastAPI(title="DTW Chat Interface API", version="0.1.0")

    # Routers
    application.include_router(onboarding_router, prefix="/api/onboarding")
    application.include_router(checkin_router, prefix="/api/checkin")

    return application



