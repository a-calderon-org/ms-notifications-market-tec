import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from time import monotonic

from ms_notifications.application.ports import NotificationRepository
from ms_notifications.domain.models import Notification

DisconnectCheck = Callable[[], Awaitable[bool]]


class NotificationEventStream:
    """Poll persisted notifications and expose recipient-scoped SSE frames."""

    def __init__(
        self,
        repository: NotificationRepository,
        poll_interval_seconds: float,
        heartbeat_interval_seconds: float,
        batch_size: int,
        max_connection_duration_seconds: float,
    ) -> None:
        self._repository = repository
        self._poll_interval_seconds = poll_interval_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._batch_size = batch_size
        self._max_connection_duration_seconds = max_connection_duration_seconds

    async def events(
        self,
        recipient_user_id: str,
        last_event_id: str | None,
        is_disconnected: DisconnectCheck,
    ) -> AsyncIterator[str]:
        current = await self._load(recipient_user_id)
        anchor = current[0].event_id if current else None

        if last_event_id is not None:
            resumable = self._newer_than(current, last_event_id)
            if resumable is None:
                yield self._resync_frame("last_event_id_not_available")
            else:
                for notification in reversed(resumable):
                    yield self._notification_frame(notification)

        started_at = monotonic()
        last_heartbeat = started_at
        while not await is_disconnected():
            await asyncio.sleep(self._poll_interval_seconds)
            if monotonic() - started_at >= self._max_connection_duration_seconds:
                return
            current = await self._load(recipient_user_id)
            newer = current if anchor is None else self._newer_than(current, anchor)

            if newer is None:
                yield self._resync_frame("stream_window_exceeded")
            elif newer:
                for notification in reversed(newer):
                    yield self._notification_frame(notification)

            if current:
                anchor = current[0].event_id

            now = monotonic()
            if now - last_heartbeat >= self._heartbeat_interval_seconds:
                yield ": keep-alive\n\n"
                last_heartbeat = now

    async def _load(self, recipient_user_id: str) -> list[Notification]:
        return await asyncio.to_thread(
            self._repository.list_by_recipient,
            recipient_user_id,
            self._batch_size,
        )

    @staticmethod
    def _newer_than(
        notifications: list[Notification],
        event_id: str,
    ) -> list[Notification] | None:
        for index, notification in enumerate(notifications):
            if notification.event_id == event_id:
                return notifications[:index]
        return None

    @classmethod
    def _notification_frame(cls, notification: Notification) -> str:
        data = {
            "notificationId": notification.event_id,
            "eventId": notification.event_id,
            "senderUserId": notification.sender_user_id,
            "chatId": notification.chat_id,
            "messageId": notification.message_id,
            "occurredAt": notification.occurred_at,
            "correlationId": notification.correlation_id,
            "createdAt": int(notification.created_at.timestamp()),
            "isRead": notification.is_read,
        }
        payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        return (
            f"retry: 3000\nid: {notification.event_id}\n"
            f"event: notification\ndata: {payload}\n\n"
        )

    @staticmethod
    def _resync_frame(reason: str) -> str:
        payload = json.dumps(
            {"reason": reason, "historyUrl": "/v1/notifications"},
            separators=(",", ":"),
        )
        return f"event: resync\ndata: {payload}\n\n"
