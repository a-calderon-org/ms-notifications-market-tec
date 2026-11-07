from copy import deepcopy

import pytest

from ms_notifications.application.process_event import ProcessMessageSent
from ms_notifications.domain.errors import InvalidEventError
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
        (("schemaVersion",), "2.0"),
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


