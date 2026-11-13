from typing import Any

import pytest


@pytest.fixture
def valid_event() -> dict[str, Any]:
    return {
        "eventId": "c4b10c16-63ec-407f-a15b-38d85f09ab36",
        "eventType": "message.sent",
        "schemaVersion": 1,
        "occurredAt": 1793836800,
        "producer": "ms-catalog",
        "correlationId": "5f0b7a52-3c1e-4c55-9d8e-2b6f3f1a9c10",
        "payload": {
            "chatId": "chat-001",
            "messageId": "msg-001",
            "senderUserId": "user-sender",
            "recipientUserId": "user-recipient",
            "sentAt": 1793836800,
            "publicationId": "pub-001",
        },
    }

