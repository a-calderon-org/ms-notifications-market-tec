from typing import Any

import pytest


@pytest.fixture
def valid_event() -> dict[str, Any]:
    return {
        "eventId": "c4b10c16-63ec-407f-a15b-38d85f09ab36",
        "eventType": "message.sent",
        "schemaVersion": "1.0",
        "occurredAt": 1793836800,
        "producer": "ms-catalog",
        "correlationId": "corr-001",
        "payload": {
            "chatId": "chat-001",
            "messageId": "msg-001",
            "senderUserId": "user-sender",
            "recipientUserId": "user-recipient",
        },
    }

