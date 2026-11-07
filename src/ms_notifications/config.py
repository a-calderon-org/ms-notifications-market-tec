from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ms-notifications"
    app_env: str = "development"
    log_level: str = "INFO"
    notifications_repository: Literal["memory", "mongo"] = "memory"
    mongodb_uri: str = ""
    mongodb_database: str = "market_tec_notifications"
    mongodb_collection: str = "notifications"
    azure_storage_queue_endpoint: str = ""
    azure_queue_name: str = "message-sent-v1"
    azure_poison_queue_name: str = "message-sent-v1-poison"
    queue_visibility_timeout_seconds: int = Field(default=30, ge=1, le=604800)
    queue_max_dequeue_count: int = Field(default=5, ge=1)
    queue_poll_interval_seconds: float = Field(default=5, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()

