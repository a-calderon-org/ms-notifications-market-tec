from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response, status

from ms_notifications.config import Settings, get_settings
from ms_notifications.container import build_repository

router = APIRouter()


@router.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
def readiness(request: Request, response: Response) -> dict[str, Any]:
    try:
        request.app.state.repository.ping()
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "repository": "unavailable"}
    settings: Settings = request.app.state.settings
    return {"status": "ok", "repository": settings.notifications_repository}


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        repository = build_repository(app_settings)
        application.state.repository = repository
        yield

    application = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.include_router(router)
    return application


app = create_app()
