import json
from copy import deepcopy

import pytest

from ms_notifications.application.process_event import ProcessMessageSent
from ms_notifications.domain.errors import InvalidEventError, UnsupportedEventVersionError
from ms_notifications.infrastructure.repositories.memory import InMemoryNotificationRepository


def test_valid_event_creates_one_notification(valid_event):
    repository = InMemoryNotificationRepository()
    use_case = ProcessMessageSent(repository)

    result = use_case.execute(valid_event)

    assert result.created is True
    assert result.event_id == valid_event["eventId"]
    assert repository.count() == 1


def test_duplicate_event_does_not_duplicate_notification(valid_event):
    repository = InMemoryNotificationRepository()
    use_case = ProcessMessageSent(repository)

    first = use_case.execute(valid_event)
    second = use_case.execute(valid_event)

    assert first.created is True
    assert second.created is False
    assert repository.count() == 1


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("eventType",), "other.event"),
        (("schemaVersion",), 2),
        (("schemaVersion",), "1.0"),
        (("eventId",), "not-a-uuid"),
        (("payload", "recipientUserId"), ""),
    ],
)
def test_invalid_event_is_rejected(valid_event, path, value):
    raw = deepcopy(valid_event)
    target = raw
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    with pytest.raises(InvalidEventError):
        ProcessMessageSent(InMemoryNotificationRepository()).execute(raw)


def test_unknown_contract_field_is_rejected(valid_event):
    valid_event["unexpected"] = "value"

    with pytest.raises(InvalidEventError, match="unsupported fields"):
        ProcessMessageSent(InMemoryNotificationRepository()).execute(valid_event)




def test_event_published_by_ms_catalog_is_accepted():
    # Exact shape emitted by ms-catalog AzureQueueEventPublisher (market_tec main).
    raw = json.loads(
        '{"eventId":"0b8f2c61-6f0e-4f43-9a51-6a5d0c1f2e77","eventType":"message.sent",'
        '"schemaVersion":1,"occurredAt":1793836800,"producer":"ms-catalog",'
        '"correlationId":"7d3f0a8e-2b9c-4d1e-8f6a-5c4b3a291807","payload":{"chatId":"chat-9",'
        '"messageId":"msg-9","senderUserId":"usr-a","recipientUserId":"usr-b",'
        '"sentAt":1793836800,"publicationId":"pub-9"}}'
    )
    repository = InMemoryNotificationRepository()

    result = ProcessMessageSent(repository).execute(raw)

    assert result.created is True
    assert result.correlation_id == "7d3f0a8e-2b9c-4d1e-8f6a-5c4b3a291807"


def test_optional_message_preview_is_accepted_but_not_persisted(valid_event):
    valid_event["payload"]["messagePreview"] = "Hola, ¿sigue disponible?"
    repository = InMemoryNotificationRepository()

    ProcessMessageSent(repository).execute(valid_event)

    stored = repository.list_by_recipient("user-recipient", limit=1)[0]
    assert not hasattr(stored, "message_preview")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("correlationId",), "corr-001"),
        (("occurredAt",), 1793836800000),
        (("payload", "sentAt"), 1793836800000),
        (("payload", "publicationId"), ""),
        (("payload", "senderUserId"), "user-recipient"),
        (("payload", "recipientUserId"), "u" * 65),
        (("payload", "messagePreview"), "x" * 161),
        (("schemaVersion",), True),
    ],
)
def test_shared_contract_rules_are_enforced(valid_event, path, value):
    raw = deepcopy(valid_event)
    target = raw
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    with pytest.raises(InvalidEventError):
        ProcessMessageSent(InMemoryNotificationRepository()).execute(raw)


def test_newer_version_is_unsupported_even_with_new_fields(valid_event):
    valid_event["schemaVersion"] = 2
    valid_event["payload"]["newField"] = "v2"

    with pytest.raises(UnsupportedEventVersionError):
        ProcessMessageSent(InMemoryNotificationRepository()).execute(valid_event)
