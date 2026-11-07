from functools import lru_cache
from typing import Literal

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
    notifications_repository: Literal["memory"] = "memory"


@lru_cache
def get_settings() -> Settings:
    return Settings()

