import logging
import signal
from threading import Event

from azure.identity import DefaultAzureCredential

from ms_notifications.application.process_event import ProcessMessageSent
from ms_notifications.application.queue_worker import NotificationQueueWorker
from ms_notifications.config import Settings
from ms_notifications.container import build_repository
from ms_notifications.infrastructure.azure_queue import AzureStorageQueue


def main() -> None:
    settings = Settings()
    if not settings.azure_storage_queue_endpoint:
        raise SystemExit("AZURE_STORAGE_QUEUE_ENDPOINT is required to start the worker")

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)

    credential = DefaultAzureCredential()
    repository = build_repository(settings)
    source_queue = AzureStorageQueue(
        settings.azure_storage_queue_endpoint,
        settings.azure_queue_name,
        credential,
    )
    poison_queue = AzureStorageQueue(
        settings.azure_storage_queue_endpoint,
        settings.azure_poison_queue_name,
        credential,
    )
    worker = NotificationQueueWorker(
        source_queue=source_queue,
        poison_queue=poison_queue,
        processor=ProcessMessageSent(repository),
        visibility_timeout_seconds=settings.queue_visibility_timeout_seconds,
        max_dequeue_count=settings.queue_max_dequeue_count,
        poll_interval_seconds=settings.queue_poll_interval_seconds,
    )
    stop_event = Event()

    def request_shutdown(signum, _frame) -> None:
        logging.getLogger(__name__).info(
            "event=queue_worker_shutdown_requested signal=%s", signum
        )
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    try:
        worker.run(stop_event)
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        source_queue.close()
        poison_queue.close()
        close_repository = getattr(repository, "close", None)
        if close_repository is not None:
            close_repository()
        credential.close()


if __name__ == "__main__":
    main()
