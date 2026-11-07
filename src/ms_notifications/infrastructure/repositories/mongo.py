from dataclasses import asdict

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from ms_notifications.domain.models import Notification


class MongoNotificationRepository:
    def __init__(self, uri: str, database: str, collection: str) -> None:
        if not uri:
            raise ValueError("MONGODB_URI is required when repository=mongo")

        self._client: MongoClient = MongoClient(
            uri,
            serverSelectionTimeoutMS=5_000,
        )
        self._collection: Collection = self._client[database][collection]
        self._create_indexes()

    def _create_indexes(self) -> None:
        self._collection.create_index(
            [("recipientUserId", ASCENDING), ("eventId", ASCENDING)],
            name="uq_recipient_event_id",
            unique=True,
        )
        self._collection.create_index(
            [
                ("recipientUserId", ASCENDING),
                ("createdAt", DESCENDING),
            ],
            name="ix_recipient_created",
        )

    def save_if_absent(self, notification: Notification) -> bool:
        document = asdict(notification)
        document.update(
            {
                "eventId": document.pop("event_id"),
                "recipientUserId": document.pop("recipient_user_id"),
                "senderUserId": document.pop("sender_user_id"),
                "chatId": document.pop("chat_id"),
                "messageId": document.pop("message_id"),
                "occurredAt": document.pop("occurred_at"),
                "correlationId": document.pop("correlation_id"),
                "createdAt": document.pop("created_at"),
                "isRead": document.pop("is_read"),
            }
        )
        try:
            self._collection.insert_one(document)
        except DuplicateKeyError:
            return False
        return True

    def ping(self) -> bool:
        self._client.admin.command("ping")
        return True

    def close(self) -> None:
        self._client.close()

