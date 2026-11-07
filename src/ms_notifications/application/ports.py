from dataclasses import dataclass
from typing import Protocol

from ms_notifications.domain.models import Notification


class NotificationRepository(Protocol):
    def save_if_absent(self, notification: Notification) -> bool:
        """Persist once by event_id; return False when it already exists."""

    def ping(self) -> bool:
        """Return whether the backing store is available."""


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

