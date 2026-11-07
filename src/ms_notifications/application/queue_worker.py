import json
import logging
from threading import Event
from typing import Any

from ms_notifications.application.ports import MessageQueue, ReceivedQueueMessage
from ms_notifications.application.process_event import ProcessMessageSent
from ms_notifications.domain.errors import InvalidEventError, UnsupportedEventVersionError

logger = logging.getLogger(__name__)
MAX_QUEUE_MESSAGE_BYTES = 64 * 1024


class MessageTooLargeError(ValueError):
    """Raised when a received message exceeds the documented Queue limit."""


class NotificationQueueWorker:
    def __init__(
        self,
        source_queue: MessageQueue,
        poison_queue: MessageQueue,
        processor: ProcessMessageSent,
        visibility_timeout_seconds: int,
        max_dequeue_count: int,
        poll_interval_seconds: float,
    ) -> None:
        self._source_queue = source_queue
        self._poison_queue = poison_queue
        self._processor = processor
        self._visibility_timeout_seconds = visibility_timeout_seconds
        self._max_dequeue_count = max_dequeue_count
        self._poll_interval_seconds = poll_interval_seconds

    def process_once(self) -> bool:
        message = self._source_queue.receive_one(self._visibility_timeout_seconds)
        if message is None:
            return False

        correlation_id = "unavailable"
        try:
            if len(message.content.encode("utf-8")) > MAX_QUEUE_MESSAGE_BYTES:
                raise MessageTooLargeError("queue message exceeds 64 KiB")
            raw_event: Any = json.loads(message.content)
            correlation_id = self._extract_correlation_id(raw_event)
            result = self._processor.execute(raw_event)
        except json.JSONDecodeError as exc:
            self._handle_failure(message, exc, "invalid_json", correlation_id, permanent=True)
            return True
        except UnsupportedEventVersionError as exc:
            self._handle_failure(
                message,
                exc,
                "unsupported_version",
                correlation_id,
                permanent=True,
            )
            return True
        except (InvalidEventError, MessageTooLargeError) as exc:
            self._handle_failure(message, exc, "invalid_message", correlation_id, permanent=True)
            return True
        except Exception as exc:
            self._handle_failure(message, exc, "transient_processing", correlation_id)
            return True

        self._source_queue.delete(message)
        logger.info(
            "event=queue_message_processed event_id=%s correlation_id=%s created=%s "
            "dequeue_count=%s",
            result.event_id,
            result.correlation_id,
            result.created,
            message.dequeue_count,
        )
        return True

    @staticmethod
    def _extract_correlation_id(raw_event: Any) -> str:
        if not isinstance(raw_event, dict):
            return "unavailable"
        value = raw_event.get("correlationId")
        if not isinstance(value, str) or not value.strip():
            return "unavailable"
        return value.strip()

    def _handle_failure(
        self,
        message: ReceivedQueueMessage,
        error: Exception,
        category: str,
        correlation_id: str,
        permanent: bool = False,
    ) -> None:
        if permanent or message.dequeue_count >= self._max_dequeue_count:
            # Send first and delete second. If poison delivery fails, the source
            # message remains available for another attempt.
            self._poison_queue.send(message.content)
            self._source_queue.delete(message)
            logger.error(
                "event=queue_message_failed disposition=poison category=%s correlation_id=%s "
                "dequeue_count=%s error_type=%s",
                category,
                correlation_id,
                message.dequeue_count,
                type(error).__name__,
            )
            return

        logger.warning(
            "event=queue_message_failed disposition=retry category=%s correlation_id=%s "
            "dequeue_count=%s max_dequeue_count=%s error_type=%s",
            category,
            correlation_id,
            message.dequeue_count,
            self._max_dequeue_count,
            type(error).__name__,
        )

    def run(self, stop_event: Event) -> None:
        logger.info("event=queue_worker_started")
        while not stop_event.is_set():
            try:
                received = self.process_once()
            except Exception as exc:
                # Queue receive/send/delete failures are retried by the next loop.
                # A failed delete is safe because repository writes are idempotent.
                logger.exception(
                    "event=queue_worker_iteration_failed error_type=%s",
                    type(exc).__name__,
                )
                received = False
            if not received:
                stop_event.wait(self._poll_interval_seconds)
        logger.info("event=queue_worker_stopped")
