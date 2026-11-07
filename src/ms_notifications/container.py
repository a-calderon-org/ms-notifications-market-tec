from ms_notifications.application.ports import NotificationRepository
from ms_notifications.config import Settings
from ms_notifications.infrastructure.repositories.memory import InMemoryNotificationRepository


def build_repository(settings: Settings) -> NotificationRepository:
    del settings
    return InMemoryNotificationRepository()

