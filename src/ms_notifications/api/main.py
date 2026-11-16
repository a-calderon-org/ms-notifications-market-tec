import hmac
import re
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ms_notifications.api.errors import APIProblem
from ms_notifications.api.notifications import router as notifications_router
from ms_notifications.application.connection_limiter import RealtimeConnectionLimiter
from ms_notifications.application.ports import Authenticator, NotificationRepository
from ms_notifications.config import Settings, get_settings
from ms_notifications.container import build_repository
from ms_notifications.infrastructure.auth import build_authenticator

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


CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
GATEWAY_KEY_HEADER = "X-MTEC-Notifications-Gateway-Key"
GATEWAY_EXEMPT_PREFIX = "/health/"
MIN_GATEWAY_KEY_LENGTH = 32


def _error_body(code: str, message: str, correlation_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "correlationId": correlation_id}}


def create_app(
    settings: Settings | None = None,
    repository: NotificationRepository | None = None,
    authenticator: Authenticator | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    gateway_key = app_settings.apim_gateway_key.encode("utf-8")
    if gateway_key and len(gateway_key) < MIN_GATEWAY_KEY_LENGTH:
        raise ValueError("APIM_GATEWAY_KEY must contain at least 32 characters")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        active_repository = repository or build_repository(app_settings)
        application.state.repository = active_repository
        yield
        close = getattr(active_repository, "close", None)
        if close is not None:
            close()

    application = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.authenticator = authenticator or build_authenticator(app_settings)
    application.state.sse_connection_limiter = RealtimeConnectionLimiter(
        max_total=app_settings.sse_max_connections,
        max_per_user=app_settings.sse_max_connections_per_user,
    )

    @application.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        incoming = request.headers.get("X-Correlation-ID")
        if incoming is not None and not CORRELATION_ID_PATTERN.fullmatch(incoming):
            correlation_id = str(uuid4())
            return JSONResponse(
                status_code=400,
                content=_error_body(
                    "INVALID_CORRELATION_ID",
                    "X-Correlation-ID must contain 1-128 safe characters",
                    correlation_id,
                ),
                headers={"X-Correlation-ID": correlation_id},
            )
        correlation_id = incoming or str(uuid4())
        request.state.correlation_id = correlation_id
        if gateway_key and not request.url.path.startswith(GATEWAY_EXEMPT_PREFIX):
            presented = request.headers.get(GATEWAY_KEY_HEADER, "").encode("utf-8")
            if not hmac.compare_digest(presented, gateway_key):
                return JSONResponse(
                    status_code=403,
                    content=_error_body(
                        "DIRECT_ACCESS_FORBIDDEN",
                        "Requests must be routed through the MarketTec API gateway",
                        correlation_id,
                    ),
                    headers={"X-Correlation-ID": correlation_id},
                )
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    @application.exception_handler(APIProblem)
    async def api_problem_handler(request: Request, exc: APIProblem):
        correlation_id = getattr(request.state, "correlation_id", str(uuid4()))
        headers = {**exc.headers, "X-Correlation-ID": correlation_id}
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, correlation_id),
            headers=headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        del exc
        correlation_id = getattr(request.state, "correlation_id", str(uuid4()))
        return JSONResponse(
            status_code=400,
            content=_error_body("VALIDATION_ERROR", "Request validation failed", correlation_id),
            headers={"X-Correlation-ID": correlation_id},
        )

    application.include_router(router)
    application.include_router(notifications_router)
    return application


app = create_app()
