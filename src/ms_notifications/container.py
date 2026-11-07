from ms_notifications.application.ports import NotificationRepository
from ms_notifications.config import Settings
from ms_notifications.infrastructure.repositories.memory import InMemoryNotificationRepository
from ms_notifications.infrastructure.repositories.mongo import MongoNotificationRepository


def build_repository(settings: Settings) -> NotificationRepository:
    if settings.notifications_repository == "mongo":
        return MongoNotificationRepository(
            uri=settings.mongodb_uri,
            database=settings.mongodb_database,
            collection=settings.mongodb_collection,
        )
    return InMemoryNotificationRepository()

