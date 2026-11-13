from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ms_notifications.domain.errors import InvalidEventError, UnsupportedEventVersionError

SUPPORTED_SCHEMA_VERSION = 1
MAX_EPOCH_SECONDS = 9_999_999_999


def _required_string(value: Any, field: str, max_length: int = 128) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidEventError(f"{field} must be a non-empty string")
    if len(value) > max_length:
        raise InvalidEventError(f"{field} exceeds {max_length} characters")
    return value.strip()


def _required_uuid(value: Any, field: str) -> str:
    text = _required_string(value, field)
    try:
        UUID(text)
    except ValueError as exc:
        raise InvalidEventError(f"{field} must be a UUID") from exc
    return text


def _epoch_seconds(value: Any, field: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 <= value <= MAX_EPOCH_SECONDS
    ):
        raise InvalidEventError(f"{field} must be an Epoch integer in seconds")
    return value


def _reject_extra_fields(raw: dict[str, Any], allowed: set[str], scope: str) -> None:
    extras = set(raw) - allowed
    if extras:
        names = ", ".join(sorted(extras))
        raise InvalidEventError(f"{scope} contains unsupported fields: {names}")


@dataclass(frozen=True, slots=True)
class MessageSentEvent:
    event_id: str
    event_type: str
    schema_version: int
    occurred_at: int
    producer: str
    correlation_id: str
    chat_id: str
    message_id: str
    sender_user_id: str
    recipient_user_id: str
    sent_at: int
    publication_id: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "MessageSentEvent":
        """Validate the shared contract `contracts/events/message-sent.v1.schema.json`."""
        if not isinstance(raw, dict):
            raise InvalidEventError("event must be an object")

        if raw.get("eventType") != "message.sent":
            raise InvalidEventError("eventType must be message.sent")
        # The version is checked before the v1 shape so a newer event is classified as
        # unsupported (kept in poison for replay) instead of being treated as malformed.
        schema_version = raw.get("schemaVersion")
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise InvalidEventError("schemaVersion must be an integer")
        if schema_version != SUPPORTED_SCHEMA_VERSION:
            raise UnsupportedEventVersionError(
                f"schemaVersion must be {SUPPORTED_SCHEMA_VERSION}"
            )

        _reject_extra_fields(
            raw,
            {
                "eventId",
                "eventType",
                "schemaVersion",
                "occurredAt",
                "producer",
                "correlationId",
                "payload",
            },
            "event",
        )

        event_id = _required_uuid(raw.get("eventId"), "eventId")
        if raw.get("producer") != "ms-catalog":
            raise InvalidEventError("producer must be ms-catalog")
        occurred_at = _epoch_seconds(raw.get("occurredAt"), "occurredAt")
        correlation_id = _required_uuid(raw.get("correlationId"), "correlationId")

        payload = raw.get("payload")
        if not isinstance(payload, dict):
            raise InvalidEventError("payload must be an object")
        _reject_extra_fields(
            payload,
            {
                "chatId",
                "messageId",
                "senderUserId",
                "recipientUserId",
                "sentAt",
                "publicationId",
                "messagePreview",
            },
            "payload",
        )

        sender_user_id = _required_string(
            payload.get("senderUserId"), "payload.senderUserId", max_length=64
        )
        recipient_user_id = _required_string(
            payload.get("recipientUserId"), "payload.recipientUserId", max_length=64
        )
        if sender_user_id == recipient_user_id:
            raise InvalidEventError("payload.senderUserId and recipientUserId must differ")

        preview = payload.get("messagePreview")
        if preview is not None and (not isinstance(preview, str) or len(preview) > 160):
            raise InvalidEventError("payload.messagePreview must be a string of 160 characters")

        return cls(
            event_id=event_id,
            event_type="message.sent",
            schema_version=SUPPORTED_SCHEMA_VERSION,
            occurred_at=occurred_at,
            producer="ms-catalog",
            correlation_id=correlation_id,
            chat_id=_required_string(payload.get("chatId"), "payload.chatId"),
            message_id=_required_string(payload.get("messageId"), "payload.messageId"),
            sender_user_id=sender_user_id,
            recipient_user_id=recipient_user_id,
            sent_at=_epoch_seconds(payload.get("sentAt"), "payload.sentAt"),
            publication_id=_required_string(payload.get("publicationId"), "payload.publicationId"),
        )


@dataclass(frozen=True, slots=True)
class Notification:
    event_id: str
    recipient_user_id: str
    sender_user_id: str
    chat_id: str
    message_id: str
    occurred_at: int
    correlation_id: str
    created_at: datetime
    is_read: bool = False

    @classmethod
    def from_event(cls, event: MessageSentEvent) -> "Notification":
        return cls(
            event_id=event.event_id,
            recipient_user_id=event.recipient_user_id,
            sender_user_id=event.sender_user_id,
            chat_id=event.chat_id,
            message_id=event.message_id,
            occurred_at=event.occurred_at,
            correlation_id=event.correlation_id,
            created_at=datetime.now(UTC),
        )

