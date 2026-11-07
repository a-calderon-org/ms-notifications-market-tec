from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ms_notifications.domain.models import Notification


@dataclass(frozen=True, slots=True)
class NotificationCursor:
    created_at: datetime
    event_id: str


class NotificationRepository(Protocol):
    def save_if_absent(self, notification: Notification) -> bool:
        """Persist once by event_id; return False when it already exists."""

    def ping(self) -> bool:
        """Return whether the backing store is available."""

    def list_by_recipient(
        self,
        recipient_user_id: str,
        limit: int,
        after: NotificationCursor | None = None,
    ) -> list[Notification]:
        """Return a stable newest-first page, scoped to one recipient."""

    def mark_read(self, recipient_user_id: str, event_id: str) -> Notification | None:
        """Mark one owned notification as read; return None when it is not visible."""


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user_id: str
    permissions: frozenset[str]


class AuthenticationError(ValueError):
    """Raised when a request has no valid authenticated principal."""


class Authenticator(Protocol):
    def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        """Validate credentials and return a trusted internal principal."""


@dataclass(frozen=True, slots=True)
class ReceivedQueueMessage:
    message_id: str
    pop_receipt: str
    content: str
    dequeue_count: int


class MessageQueue(Protocol):
    def receive_one(self, visibility_timeout: int) -> ReceivedQueueMessage | None:
        """Receive at most one message and temporarily hide it from other consumers."""

    def send(self, content: str) -> None:
        """Add a message to the queue."""

    def delete(self, message: ReceivedQueueMessage) -> None:
        """Permanently delete a previously received message."""

