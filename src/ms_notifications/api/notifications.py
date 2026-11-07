import logging
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from ms_notifications.api.errors import APIProblem
from ms_notifications.application.connection_limiter import RealtimeConnectionLimiter
from ms_notifications.application.notification_history import (
    ListNotifications,
    MarkNotificationRead,
)
from ms_notifications.application.notification_stream import NotificationEventStream
from ms_notifications.application.ports import (
    AuthenticatedPrincipal,
    AuthenticationError,
    NotificationRepository,
)
from ms_notifications.domain.errors import InvalidCursorError, NotificationNotFoundError
from ms_notifications.domain.models import Notification

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])
READ_PERMISSION = "notifications:read"
WRITE_PERMISSION = "notifications:write"
LOGGER = logging.getLogger(__name__)


class NotificationResponse(BaseModel):
    notificationId: str
    eventId: str
    senderUserId: str
    chatId: str
    messageId: str
    occurredAt: int
    correlationId: str
    createdAt: int
    isRead: bool

    @classmethod
    def from_domain(cls, notification: Notification) -> "NotificationResponse":
        return cls(
            notificationId=notification.event_id,
            eventId=notification.event_id,
            senderUserId=notification.sender_user_id,
            chatId=notification.chat_id,
            messageId=notification.message_id,
            occurredAt=notification.occurred_at,
            correlationId=notification.correlation_id,
            createdAt=int(notification.created_at.timestamp()),
            isRead=notification.is_read,
        )


class NotificationPageResponse(BaseModel):
    items: list[NotificationResponse]
    nextCursor: str | None


def authenticated_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedPrincipal:
    try:
        return request.app.state.authenticator.authenticate(authorization)
    except AuthenticationError as exc:
        raise APIProblem(
            status_code=401,
            code="UNAUTHENTICATED",
            message="A valid authenticated session is required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _require_permission(principal: AuthenticatedPrincipal, permission: str) -> None:
    if permission not in principal.permissions:
        raise APIProblem(
            status_code=403,
            code="FORBIDDEN",
            message="The authenticated principal lacks the required permission",
        )


@router.get(
    "/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Recipient-scoped Server-Sent Events stream",
            "content": {"text/event-stream": {}},
        }
    },
)
async def stream_notifications(
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(authenticated_principal)],
    last_event_id: Annotated[
        UUID | None,
        Header(alias="Last-Event-ID"),
    ] = None,
) -> StreamingResponse:
    _require_permission(principal, READ_PERMISSION)
    limiter: RealtimeConnectionLimiter = request.app.state.sse_connection_limiter
    if not await limiter.acquire(principal.user_id):
        raise APIProblem(
            status_code=429,
            code="CONNECTION_LIMIT_REACHED",
            message="The real-time connection limit has been reached",
            headers={"Retry-After": "5"},
        )
    repository: NotificationRepository = request.app.state.repository
    settings = request.app.state.settings
    event_stream = NotificationEventStream(
        repository=repository,
        poll_interval_seconds=settings.sse_poll_interval_seconds,
        heartbeat_interval_seconds=settings.sse_heartbeat_interval_seconds,
        batch_size=settings.sse_batch_size,
        max_connection_duration_seconds=settings.sse_max_connection_duration_seconds,
    )
    content = event_stream.events(
        recipient_user_id=principal.user_id,
        last_event_id=str(last_event_id) if last_event_id is not None else None,
        is_disconnected=request.is_disconnected,
    )
    return StreamingResponse(
        _instrumented_stream(
            content,
            limiter=limiter,
            user_id=principal.user_id,
            correlation_id=request.state.correlation_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _instrumented_stream(
    content: AsyncIterator[str],
    limiter: RealtimeConnectionLimiter,
    user_id: str,
    correlation_id: str,
) -> AsyncIterator[str]:
    LOGGER.info(
        "event=sse_connection_opened user_id=%s correlation_id=%s",
        user_id,
        correlation_id,
    )
    try:
        async for frame in content:
            yield frame
    finally:
        await content.aclose()
        await limiter.release(user_id)
        LOGGER.info(
            "event=sse_connection_closed user_id=%s correlation_id=%s",
            user_id,
            correlation_id,
        )


@router.get("", response_model=NotificationPageResponse)
def list_notifications(
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(authenticated_principal)],
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
) -> NotificationPageResponse:
    _require_permission(principal, READ_PERMISSION)
    repository: NotificationRepository = request.app.state.repository
    try:
        page = ListNotifications(repository).execute(
            recipient_user_id=principal.user_id,
            page_size=page_size,
            cursor=cursor,
        )
    except InvalidCursorError as exc:
        raise APIProblem(400, "INVALID_CURSOR", "The pagination cursor is invalid") from exc
    return NotificationPageResponse(
        items=[NotificationResponse.from_domain(item) for item in page.items],
        nextCursor=page.next_cursor,
    )


@router.patch("/{notificationId}/read", response_model=NotificationResponse)
def mark_notification_read(
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(authenticated_principal)],
    notificationId: Annotated[UUID, Path()],
) -> NotificationResponse:
    _require_permission(principal, WRITE_PERMISSION)
    repository: NotificationRepository = request.app.state.repository
    try:
        notification = MarkNotificationRead(repository).execute(
            recipient_user_id=principal.user_id,
            notification_id=str(notificationId),
        )
    except NotificationNotFoundError as exc:
        raise APIProblem(404, "NOT_FOUND", "Notification not found") from exc
    return NotificationResponse.from_domain(notification)
