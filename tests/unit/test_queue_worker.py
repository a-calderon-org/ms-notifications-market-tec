import json
import logging
from threading import Event

import pytest

from ms_notifications.application.ports import ReceivedQueueMessage
from ms_notifications.application.process_event import ProcessMessageSent
from ms_notifications.application.queue_worker import NotificationQueueWorker
from ms_notifications.infrastructure.repositories.memory import InMemoryNotificationRepository


class FakeQueue:
    def __init__(self, messages=None, send_error=None, delete_error=None):
        self.messages = list(messages or [])
        self.sent = []
        self.deleted = []
        self.receive_calls = 0
        self.send_error = send_error
        self.delete_error = delete_error

    def receive_one(self, visibility_timeout):
        del visibility_timeout
        self.receive_calls += 1
        return self.messages.pop(0) if self.messages else None

    def send(self, content):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(content)

    def delete(self, message):
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted.append(message)


class FailingRepository:
    def save_if_absent(self, notification):
        del notification
        raise RuntimeError("temporary database failure")

    def ping(self):
        return True


def build_worker(messages, repository=None, poison=None, max_dequeue_count=5):
    source = FakeQueue(messages)
    poison = poison or FakeQueue()
    repository = repository or InMemoryNotificationRepository()
    worker = NotificationQueueWorker(
        source_queue=source,
        poison_queue=poison,
        processor=ProcessMessageSent(repository),
        visibility_timeout_seconds=30,
        max_dequeue_count=max_dequeue_count,
        poll_interval_seconds=0.01,
    )
    return worker, source, poison, repository


def queue_message(content, dequeue_count=1, suffix="1"):
    return ReceivedQueueMessage(
        message_id=f"queue-message-{suffix}",
        pop_receipt=f"receipt-{suffix}",
        content=content,
        dequeue_count=dequeue_count,
    )


def test_valid_message_is_saved_deleted_and_correlated(valid_event, caplog):
    message = queue_message(json.dumps(valid_event))
    worker, source, poison, repository = build_worker([message])

    with caplog.at_level(logging.INFO):
        assert worker.process_once() is True

    assert repository.count() == 1
    assert source.deleted == [message]
    assert poison.sent == []
    assert "correlation_id=5f0b7a52-3c1e-4c55-9d8e-2b6f3f1a9c10" in caplog.text
    assert "event=queue_message_processed" in caplog.text


def test_duplicate_delivery_is_idempotent(valid_event):
    content = json.dumps(valid_event)
    first = queue_message(content, suffix="1")
    duplicate = queue_message(content, suffix="2")
    worker, source, poison, repository = build_worker([first, duplicate])

    assert worker.process_once() is True
    assert worker.process_once() is True

    assert repository.count() == 1
    assert source.deleted == [first, duplicate]
    assert poison.sent == []


def test_restart_reprocessing_remains_idempotent(valid_event):
    repository = InMemoryNotificationRepository()
    content = json.dumps(valid_event)
    first_worker, first_source, _, _ = build_worker(
        [queue_message(content, suffix="before-restart")], repository=repository
    )
    second_worker, second_source, _, _ = build_worker(
        [queue_message(content, dequeue_count=2, suffix="after-restart")],
        repository=repository,
    )

    assert first_worker.process_once() is True
    assert second_worker.process_once() is True

    assert repository.count() == 1
    assert len(first_source.deleted) == 1
    assert len(second_source.deleted) == 1


def test_transient_failure_remains_for_retry_before_limit(valid_event):
    message = queue_message(json.dumps(valid_event), dequeue_count=4)
    worker, source, poison, _ = build_worker([message], repository=FailingRepository())

    assert worker.process_once() is True

    assert source.deleted == []
    assert poison.sent == []


def test_transient_failure_moves_to_poison_at_limit(valid_event):
    content = json.dumps(valid_event)
    message = queue_message(content, dequeue_count=5)
    worker, source, poison, _ = build_worker([message], repository=FailingRepository())

    assert worker.process_once() is True

    assert poison.sent == [content]
    assert source.deleted == [message]


@pytest.mark.parametrize(
    ("content", "category"),
    [
        ("not-json", "invalid_json"),
        (json.dumps({"eventType": "message.sent", "schemaVersion": 1}), "invalid_message"),
    ],
)
def test_permanent_failure_moves_immediately_to_poison(content, category, caplog):
    message = queue_message(content, dequeue_count=1)
    worker, source, poison, repository = build_worker([message])

    with caplog.at_level(logging.ERROR):
        assert worker.process_once() is True

    assert repository.count() == 0
    assert poison.sent == [content]
    assert source.deleted == [message]
    assert f"category={category}" in caplog.text


def test_unsupported_version_is_distinguished(valid_event, caplog):
    valid_event["schemaVersion"] = 2
    content = json.dumps(valid_event)
    message = queue_message(content)
    worker, source, poison, _ = build_worker([message])

    with caplog.at_level(logging.ERROR):
        assert worker.process_once() is True

    assert poison.sent == [content]
    assert source.deleted == [message]
    assert "category=unsupported_version" in caplog.text
    assert "correlation_id=5f0b7a52-3c1e-4c55-9d8e-2b6f3f1a9c10" in caplog.text


def test_oversized_message_is_rejected_without_logging_payload(caplog):
    content = "x" * (64 * 1024 + 1)
    message = queue_message(content)
    worker, source, poison, _ = build_worker([message])

    with caplog.at_level(logging.ERROR):
        assert worker.process_once() is True

    assert poison.sent == [content]
    assert source.deleted == [message]
    assert content not in caplog.text
    assert "category=invalid_message" in caplog.text


def test_poison_delivery_failure_does_not_delete_source_message():
    message = queue_message("not-json")
    poison = FakeQueue(send_error=RuntimeError("queue unavailable"))
    worker, source, _, _ = build_worker([message], poison=poison)

    with pytest.raises(RuntimeError, match="queue unavailable"):
        worker.process_once()

    assert source.deleted == []


def test_empty_queue_returns_false():
    worker, source, poison, repository = build_worker([])

    assert worker.process_once() is False

    assert repository.count() == 0
    assert poison.sent == []
    assert source.receive_calls == 1


def test_worker_stops_cleanly_when_shutdown_is_already_requested(caplog):
    worker, source, _, _ = build_worker([])
    stop_event = Event()
    stop_event.set()

    with caplog.at_level(logging.INFO):
        worker.run(stop_event)

    assert source.receive_calls == 0
    assert "event=queue_worker_started" in caplog.text
    assert "event=queue_worker_stopped" in caplog.text
