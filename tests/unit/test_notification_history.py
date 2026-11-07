from datetime import UTC, datetime

import pytest

from ms_notifications.application.notification_history import (
    ListNotifications,
    MarkNotificationRead,
)
from ms_notifications.domain.errors import InvalidCursorError, NotificationNotFoundError
from ms_notifications.domain.models import Notification
from ms_notifications.infrastructure.repositories.memory import InMemoryNotificationRepository


def make_notification(event_id, recipient, created_at):
    return Notification(
        event_id=event_id,
        recipient_user_id=recipient,
        sender_user_id="sender",
        chat_id="chat",
        message_id="message",
        occurred_at=1,
        correlation_id="correlation",
        created_at=created_at,
    )


def test_cursor_preserves_order_when_created_at_is_equal():
    repository = InMemoryNotificationRepository()
    created_at = datetime(2026, 11, 7, tzinfo=UTC)
    identifiers = [
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
    ]
    for identifier in identifiers:
        repository.save_if_absent(make_notification(identifier, "user-a", created_at))

    use_case = ListNotifications(repository)
    first = use_case.execute("user-a", page_size=2, cursor=None)
    second = use_case.execute("user-a", page_size=2, cursor=first.next_cursor)

    result = [item.event_id for item in (*first.items, *second.items)]
    assert result == list(reversed(identifiers))
    assert len(set(result)) == 3
    assert second.next_cursor is None


@pytest.mark.parametrize("cursor", ["not-base64", "e30"])
def test_invalid_cursor_is_rejected(cursor):
    with pytest.raises(InvalidCursorError):
        ListNotifications(InMemoryNotificationRepository()).execute(
            "user-a", page_size=20, cursor=cursor
        )


def test_missing_notification_is_not_disclosed():
    with pytest.raises(NotificationNotFoundError):
        MarkNotificationRead(InMemoryNotificationRepository()).execute(
            "user-a", "11111111-1111-4111-8111-111111111111"
        )
