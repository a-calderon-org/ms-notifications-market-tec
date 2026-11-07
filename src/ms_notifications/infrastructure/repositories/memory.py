from dataclasses import replace
from threading import Lock

from ms_notifications.application.ports import NotificationCursor
from ms_notifications.domain.models import Notification


class InMemoryNotificationRepository:
    def __init__(self) -> None:
        self._notifications: dict[str, Notification] = {}
        self._lock = Lock()

    def save_if_absent(self, notification: Notification) -> bool:
        with self._lock:
            if notification.event_id in self._notifications:
                return False
            self._notifications[notification.event_id] = notification
            return True

    def ping(self) -> bool:
        return True

    def list_by_recipient(
        self,
        recipient_user_id: str,
        limit: int,
        after: NotificationCursor | None = None,
    ) -> list[Notification]:
        with self._lock:
            notifications = [
                item
                for item in self._notifications.values()
                if item.recipient_user_id == recipient_user_id
            ]
            notifications.sort(
                key=lambda item: (item.created_at, item.event_id),
                reverse=True,
            )
            if after is not None:
                notifications = [
                    item
                    for item in notifications
                    if (item.created_at, item.event_id) < (after.created_at, after.event_id)
                ]
            return notifications[:limit]

    def mark_read(self, recipient_user_id: str, event_id: str) -> Notification | None:
        with self._lock:
            notification = self._notifications.get(event_id)
            if notification is None or notification.recipient_user_id != recipient_user_id:
                return None
            if not notification.is_read:
                notification = replace(notification, is_read=True)
                self._notifications[event_id] = notification
            return notification

    def count(self) -> int:
        with self._lock:
            return len(self._notifications)

