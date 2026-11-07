from types import SimpleNamespace
from unittest.mock import Mock, patch

from ms_notifications.application.ports import ReceivedQueueMessage
from ms_notifications.infrastructure.azure_queue import AzureStorageQueue


def test_azure_queue_adapter_maps_receive_send_delete_and_close():
    sdk_message = SimpleNamespace(
        id="message-id",
        pop_receipt="pop-receipt",
        content='{"eventId":"event-id"}',
        dequeue_count=2,
    )
    client = Mock()
    client.receive_messages.return_value = iter([sdk_message])
    credential = object()

    with patch(
        "ms_notifications.infrastructure.azure_queue.QueueClient", return_value=client
    ) as queue_client:
        queue = AzureStorageQueue(
            endpoint="https://storage.queue.core.windows.net",
            queue_name="message-sent-v1",
            credential=credential,
        )

    queue_client.assert_called_once_with(
        account_url="https://storage.queue.core.windows.net",
        queue_name="message-sent-v1",
        credential=credential,
    )

    received = queue.receive_one(visibility_timeout=30)

    assert received == ReceivedQueueMessage(
        message_id="message-id",
        pop_receipt="pop-receipt",
        content='{"eventId":"event-id"}',
        dequeue_count=2,
    )
    client.receive_messages.assert_called_once_with(
        messages_per_page=1,
        visibility_timeout=30,
    )

    queue.send("poison-content")
    queue.delete(received)
    queue.close()

    client.send_message.assert_called_once_with("poison-content")
    client.delete_message.assert_called_once_with("message-id", "pop-receipt")
    client.close.assert_called_once_with()


def test_azure_queue_adapter_returns_none_when_queue_is_empty():
    client = Mock()
    client.receive_messages.return_value = iter([])

    with patch("ms_notifications.infrastructure.azure_queue.QueueClient", return_value=client):
        queue = AzureStorageQueue(
            endpoint="https://storage.queue.core.windows.net",
            queue_name="message-sent-v1",
            credential=object(),
        )

    assert queue.receive_one(visibility_timeout=30) is None
