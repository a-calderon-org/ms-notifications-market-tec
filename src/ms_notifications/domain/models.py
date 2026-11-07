from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ms_notifications.domain.errors import InvalidEventError, UnsupportedEventVersionError


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidEventError(f"{field} must be a non-empty string")
    return value.strip()


def _reject_extra_fields(raw: dict[str, Any], allowed: set[str], scope: str) -> None:
    extras = set(raw) - allowed
    if extras:
        names = ", ".join(sorted(extras))
        raise InvalidEventError(f"{scope} contains unsupported fields: {names}")


@dataclass(frozen=True, slots=True)
class MessageSentEvent:
    event_id: str
    event_type: str
    schema_version: str
    occurred_at: int
    producer: str
    correlation_id: str
    chat_id: str
    message_id: str
    sender_user_id: str
    recipient_user_id: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "MessageSentEvent":
        if not isinstance(raw, dict):
            raise InvalidEventError("event must be an object")

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

        event_id = _required_string(raw.get("eventId"), "eventId")
        try:
            UUID(event_id)
        except ValueError as exc:
            raise InvalidEventError("eventId must be a UUID") from exc

        if raw.get("eventType") != "message.sent":
            raise InvalidEventError("eventType must be message.sent")
        if raw.get("schemaVersion") != "1.0":
            raise UnsupportedEventVersionError("schemaVersion must be 1.0")
        if raw.get("producer") != "ms-catalog":
            raise InvalidEventError("producer must be ms-catalog")

        occurred_at = raw.get("occurredAt")
        if not isinstance(occurred_at, int) or isinstance(occurred_at, bool) or occurred_at < 0:
            raise InvalidEventError("occurredAt must be a positive Epoch integer")

        payload = raw.get("payload")
        if not isinstance(payload, dict):
            raise InvalidEventError("payload must be an object")
        _reject_extra_fields(
            payload,
            {"chatId", "messageId", "senderUserId", "recipientUserId"},
            "payload",
        )

        return cls(
            event_id=event_id,
            event_type="message.sent",
            schema_version="1.0",
            occurred_at=occurred_at,
            producer="ms-catalog",
            correlation_id=_required_string(raw.get("correlationId"), "correlationId"),
            chat_id=_required_string(payload.get("chatId"), "payload.chatId"),
            message_id=_required_string(payload.get("messageId"), "payload.messageId"),
            sender_user_id=_required_string(payload.get("senderUserId"), "payload.senderUserId"),
            recipient_user_id=_required_string(
                payload.get("recipientUserId"), "payload.recipientUserId"
            ),
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

