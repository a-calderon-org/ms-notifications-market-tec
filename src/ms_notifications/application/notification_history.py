import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from ms_notifications.application.ports import NotificationCursor, NotificationRepository
from ms_notifications.domain.errors import InvalidCursorError, NotificationNotFoundError
from ms_notifications.domain.models import Notification

MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class NotificationPage:
    items: tuple[Notification, ...]
    next_cursor: str | None


def _encode_cursor(notification: Notification) -> str:
    payload = json.dumps(
        {
            "createdAt": notification.created_at.astimezone(UTC).isoformat(),
            "eventId": notification.event_id,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> NotificationCursor:
    try:
        padding = "=" * (-len(value) % 4)
        payload = base64.urlsafe_b64decode(value + padding)
        raw = json.loads(payload.decode("utf-8"))
        if set(raw) != {"createdAt", "eventId"}:
            raise ValueError("unexpected cursor fields")
        created_at = datetime.fromisoformat(raw["createdAt"])
        event_id = raw["eventId"]
        if created_at.tzinfo is None or not isinstance(event_id, str) or not event_id:
            raise ValueError("invalid cursor values")
    except (ValueError, TypeError, KeyError, binascii.Error, UnicodeError) as exc:
        raise InvalidCursorError("cursor is invalid") from exc
    return NotificationCursor(created_at=created_at.astimezone(UTC), event_id=event_id)


class ListNotifications:
    def __init__(self, repository: NotificationRepository) -> None:
        self._repository = repository

    def execute(
        self,
        recipient_user_id: str,
        page_size: int,
        cursor: str | None,
    ) -> NotificationPage:
        if not MIN_PAGE_SIZE <= page_size <= MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be between {MIN_PAGE_SIZE} and {MAX_PAGE_SIZE}")
        after = _decode_cursor(cursor) if cursor else None
        rows = self._repository.list_by_recipient(
            recipient_user_id=recipient_user_id,
            limit=page_size + 1,
            after=after,
        )
        has_more = len(rows) > page_size
        items = tuple(rows[:page_size])
        next_cursor = _encode_cursor(items[-1]) if has_more and items else None
        return NotificationPage(items=items, next_cursor=next_cursor)


class MarkNotificationRead:
    def __init__(self, repository: NotificationRepository) -> None:
        self._repository = repository

    def execute(self, recipient_user_id: str, notification_id: str) -> Notification:
        notification = self._repository.mark_read(recipient_user_id, notification_id)
        if notification is None:
            # Deliberately do not reveal whether another user owns this identifier.
            raise NotificationNotFoundError("notification not found")
        return notification
