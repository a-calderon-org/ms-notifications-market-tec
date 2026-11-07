import asyncio
from datetime import UTC, datetime, timedelta

from ms_notifications.application.notification_stream import NotificationEventStream
from ms_notifications.domain.models import Notification
from ms_notifications.infrastructure.repositories.memory import InMemoryNotificationRepository

OLDER_EVENT = "11111111-1111-4111-8111-111111111111"
NEWER_EVENT = "22222222-2222-4222-8222-222222222222"
OTHER_USER_EVENT = "33333333-3333-4333-8333-333333333333"
UNKNOWN_EVENT = "44444444-4444-4444-8444-444444444444"


def make_notification(event_id: str, recipient: str, created_at: datetime) -> Notification:
    return Notification(
        event_id=event_id,
        recipient_user_id=recipient,
        sender_user_id="sender",
        chat_id="chat-1",
        message_id=f"message-{event_id[:4]}",
        occurred_at=int(created_at.timestamp()),
        correlation_id=f"correlation-{event_id[:4]}",
        created_at=created_at,
    )


def build_stream(repository: InMemoryNotificationRepository) -> NotificationEventStream:
    return NotificationEventStream(
        repository=repository,
        poll_interval_seconds=0.001,
        heartbeat_interval_seconds=60,
        batch_size=10,
        max_connection_duration_seconds=60,
    )


async def connected() -> bool:
    return False


def test_resume_emits_only_newer_events_owned_by_authenticated_recipient():
    async def scenario():
        repository = InMemoryNotificationRepository()
        now = datetime(2026, 11, 7, 12, tzinfo=UTC)
        repository.save_if_absent(make_notification(OLDER_EVENT, "user-a", now))
        repository.save_if_absent(
            make_notification(NEWER_EVENT, "user-a", now + timedelta(seconds=1))
        )
        repository.save_if_absent(
            make_notification(OTHER_USER_EVENT, "user-b", now + timedelta(seconds=2))
        )

        events = build_stream(repository).events("user-a", OLDER_EVENT, connected)
        frame = await anext(events)
        await events.aclose()

        assert f"id: {NEWER_EVENT}" in frame
        assert '"notificationId":"22222222-2222-4222-8222-222222222222"' in frame
        assert OTHER_USER_EVENT not in frame
        assert "recipientUserId" not in frame

    asyncio.run(scenario())


def test_unknown_last_event_id_requests_history_resynchronization():
    async def scenario():
        repository = InMemoryNotificationRepository()
        repository.save_if_absent(
            make_notification(NEWER_EVENT, "user-a", datetime(2026, 11, 7, tzinfo=UTC))
        )

        events = build_stream(repository).events("user-a", UNKNOWN_EVENT, connected)
        frame = await anext(events)
        await events.aclose()

        assert "event: resync" in frame
        assert '"reason":"last_event_id_not_available"' in frame
        assert '"historyUrl":"/v1/notifications"' in frame

    asyncio.run(scenario())


def test_new_persisted_event_is_delivered_without_coupling_the_writer():
    async def scenario():
        repository = InMemoryNotificationRepository()
        events = build_stream(repository).events("user-a", None, connected)
        pending_frame = asyncio.create_task(anext(events))
        await asyncio.sleep(0.01)

        repository.save_if_absent(
            make_notification(NEWER_EVENT, "user-a", datetime(2026, 11, 7, tzinfo=UTC))
        )
        frame = await asyncio.wait_for(pending_frame, timeout=1)
        await events.aclose()

        assert f"id: {NEWER_EVENT}" in frame
        assert "event: notification" in frame

    asyncio.run(scenario())


def test_disconnected_client_stops_without_waiting_for_an_event():
    async def scenario():
        async def disconnected() -> bool:
            return True

        events = build_stream(InMemoryNotificationRepository()).events(
            "user-a", None, disconnected
        )
        try:
            await anext(events)
        except StopAsyncIteration:
            pass
        else:
            raise AssertionError("disconnected stream should stop")

    asyncio.run(scenario())


def test_connection_duration_forces_periodic_reauthentication():
    async def scenario():
        stream = NotificationEventStream(
            repository=InMemoryNotificationRepository(),
            poll_interval_seconds=0.001,
            heartbeat_interval_seconds=60,
            batch_size=10,
            max_connection_duration_seconds=0.001,
        )
        events = stream.events("user-a", None, connected)
        try:
            await anext(events)
        except StopAsyncIteration:
            pass
        else:
            raise AssertionError("expired stream should require reconnection")

    asyncio.run(scenario())
