from typing import Any

from azure.storage.queue import QueueClient

from ms_notifications.application.ports import ReceivedQueueMessage


class AzureStorageQueue:
    def __init__(
        self,
        endpoint: str,
        queue_name: str,
        credential: Any,
    ) -> None:
        self._client = QueueClient(
            account_url=endpoint,
            queue_name=queue_name,
            credential=credential,
        )

    def receive_one(self, visibility_timeout: int) -> ReceivedQueueMessage | None:
        messages = self._client.receive_messages(
            messages_per_page=1,
            visibility_timeout=visibility_timeout,
        )
        message = next(iter(messages), None)
        if message is None:
            return None
        return ReceivedQueueMessage(
            message_id=message.id,
            pop_receipt=message.pop_receipt,
            content=message.content,
            dequeue_count=message.dequeue_count or 1,
        )

    def send(self, content: str) -> None:
        self._client.send_message(content)

    def delete(self, message: ReceivedQueueMessage) -> None:
        self._client.delete_message(message.message_id, message.pop_receipt)

    def close(self) -> None:
        self._client.close()
