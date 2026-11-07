from threading import Lock

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

    def count(self) -> int:
        with self._lock:
            return len(self._notifications)

