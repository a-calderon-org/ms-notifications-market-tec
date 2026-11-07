from datetime import UTC, datetime
from unittest.mock import Mock

from pymongo import DESCENDING, ReturnDocument

from ms_notifications.application.ports import NotificationCursor
from ms_notifications.infrastructure.repositories.mongo import MongoNotificationRepository


def mongo_document(event_id="11111111-1111-4111-8111-111111111111", is_read=False):
    return {
        "eventId": event_id,
        "recipientUserId": "user-a",
        "senderUserId": "sender",
        "chatId": "chat",
        "messageId": "message",
        "occurredAt": 1794000000,
        "correlationId": "correlation",
        "createdAt": datetime(2026, 11, 7, tzinfo=UTC),
        "isRead": is_read,
    }


def repository_with_collection(collection):
    repository = MongoNotificationRepository.__new__(MongoNotificationRepository)
    repository._collection = collection
    return repository


def test_list_by_recipient_builds_scoped_stable_query():
    collection = Mock()
    cursor_result = Mock()
    sorted_result = Mock()
    collection.find.return_value = cursor_result
    cursor_result.sort.return_value = sorted_result
    sorted_result.limit.return_value = [mongo_document()]
    repository = repository_with_collection(collection)
    after = NotificationCursor(
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
        event_id="22222222-2222-4222-8222-222222222222",
    )

    result = repository.list_by_recipient("user-a", limit=21, after=after)

    collection.find.assert_called_once_with(
        {
            "recipientUserId": "user-a",
            "$or": [
                {"createdAt": {"$lt": after.created_at}},
                {
                    "createdAt": after.created_at,
                    "eventId": {"$lt": after.event_id},
                },
            ],
        }
    )
    cursor_result.sort.assert_called_once_with(
        [("createdAt", DESCENDING), ("eventId", DESCENDING)]
    )
    sorted_result.limit.assert_called_once_with(21)
    assert [item.event_id for item in result] == [
        "11111111-1111-4111-8111-111111111111"
    ]


def test_mark_read_is_scoped_to_authenticated_recipient():
    collection = Mock()
    collection.find_one_and_update.return_value = mongo_document(is_read=True)
    repository = repository_with_collection(collection)

    result = repository.mark_read(
        "user-a",
        "11111111-1111-4111-8111-111111111111",
    )

    collection.find_one_and_update.assert_called_once_with(
        {
            "recipientUserId": "user-a",
            "eventId": "11111111-1111-4111-8111-111111111111",
        },
        {"$set": {"isRead": True}},
        return_document=ReturnDocument.AFTER,
    )
    assert result is not None
    assert result.is_read is True


def test_mark_read_returns_none_without_disclosing_another_owner():
    collection = Mock()
    collection.find_one_and_update.return_value = None
    repository = repository_with_collection(collection)

    assert repository.mark_read("user-a", "missing") is None
