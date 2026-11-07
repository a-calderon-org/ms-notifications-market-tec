from typing import Protocol

from ms_notifications.domain.models import Notification


class NotificationRepository(Protocol):
    def save_if_absent(self, notification: Notification) -> bool:
        """Persist once by event_id; return False when it already exists."""

    def ping(self) -> bool:
        """Return whether the backing store is available."""

