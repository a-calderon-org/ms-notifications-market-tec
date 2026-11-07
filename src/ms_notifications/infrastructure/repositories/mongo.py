from dataclasses import asdict
from datetime import UTC

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from ms_notifications.application.ports import NotificationCursor
from ms_notifications.domain.models import Notification


class MongoNotificationRepository:
    def __init__(self, uri: str, database: str, collection: str) -> None:
        if not uri:
            raise ValueError("MONGODB_URI is required when repository=mongo")

        self._client: MongoClient = MongoClient(
            uri,
            serverSelectionTimeoutMS=5_000,
            tz_aware=True,
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
                ("eventId", DESCENDING),
            ],
            name="ix_recipient_created_event",
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

    @staticmethod
    def _to_notification(document: dict) -> Notification:
        created_at = document["createdAt"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return Notification(
            event_id=document["eventId"],
            recipient_user_id=document["recipientUserId"],
            sender_user_id=document["senderUserId"],
            chat_id=document["chatId"],
            message_id=document["messageId"],
            occurred_at=document["occurredAt"],
            correlation_id=document["correlationId"],
            created_at=created_at,
            is_read=document.get("isRead", False),
        )

    def list_by_recipient(
        self,
        recipient_user_id: str,
        limit: int,
        after: NotificationCursor | None = None,
    ) -> list[Notification]:
        query: dict = {"recipientUserId": recipient_user_id}
        if after is not None:
            query["$or"] = [
                {"createdAt": {"$lt": after.created_at}},
                {"createdAt": after.created_at, "eventId": {"$lt": after.event_id}},
            ]
        documents = (
            self._collection.find(query)
            .sort([("createdAt", DESCENDING), ("eventId", DESCENDING)])
            .limit(limit)
        )
        return [self._to_notification(document) for document in documents]

    def mark_read(self, recipient_user_id: str, event_id: str) -> Notification | None:
        document = self._collection.find_one_and_update(
            {"recipientUserId": recipient_user_id, "eventId": event_id},
            {"$set": {"isRead": True}},
            return_document=ReturnDocument.AFTER,
        )
        return self._to_notification(document) if document is not None else None

    def ping(self) -> bool:
        self._client.admin.command("ping")
        return True

    def close(self) -> None:
        self._client.close()

