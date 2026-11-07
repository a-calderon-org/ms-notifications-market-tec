from dataclasses import dataclass
from typing import Any

from ms_notifications.application.ports import NotificationRepository
from ms_notifications.domain.models import MessageSentEvent, Notification


@dataclass(frozen=True, slots=True)
class ProcessEventResult:
    event_id: str
    created: bool


class ProcessMessageSent:
    def __init__(self, repository: NotificationRepository) -> None:
        self._repository = repository

    def execute(self, raw_event: Any) -> ProcessEventResult:
        event = MessageSentEvent.from_dict(raw_event)
        notification = Notification.from_event(event)
        created = self._repository.save_if_absent(notification)
        return ProcessEventResult(event_id=event.event_id, created=created)

