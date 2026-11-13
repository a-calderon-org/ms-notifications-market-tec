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
    authentication_mode: Literal["reject_all", "jwt"] = "reject_all"
    jwt_issuer: str = ""
    jwt_audience: str = ""
    jwt_jwks_url: str = ""
    jwt_jwks_json: str = ""
    jwt_default_permissions: str = "notifications:read notifications:write"
    jwt_max_ttl_seconds: int = Field(default=240, ge=1, le=240)
    jwt_jwks_timeout_seconds: int = Field(default=5, ge=1, le=30)
    jwt_jwks_cache_seconds: int = Field(default=300, ge=1, le=3600)
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
    sse_poll_interval_seconds: float = Field(default=2, gt=0)
    sse_heartbeat_interval_seconds: float = Field(default=15, gt=0)
    sse_batch_size: int = Field(default=100, ge=1, le=500)
    sse_max_connections: int = Field(default=100, ge=1)
    sse_max_connections_per_user: int = Field(default=3, ge=1)
    sse_max_connection_duration_seconds: float = Field(default=300, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()

