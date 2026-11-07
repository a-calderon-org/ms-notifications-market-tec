from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from pydantic import BaseModel

from ms_notifications.api.errors import APIProblem
from ms_notifications.application.notification_history import (
    ListNotifications,
    MarkNotificationRead,
)
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
