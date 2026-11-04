from datetime import time
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "Domik CRM"
    environment: Literal["local", "production", "test"] = "local"
    log_level: str = "INFO"
    timezone: str = "Europe/Rome"
    default_language: Literal["ru", "en", "it"] = "ru"

    # --- Telegram ---
    bot_token: SecretStr
    bot_mode: Literal["polling", "webhook"] = "polling"
    webhook_base_url: str | None = None
    webhook_path: str = "/webhook/telegram"
    webhook_secret: SecretStr = SecretStr("change-me")
    owner_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, validation_alias=AliasChoices("OWNER_IDS", "ADMIN_IDS")
    )

    # --- REST API ---
    api_key: SecretStr = SecretStr("change-me")

    # --- Storage ---
    database_url: str = "postgresql+asyncpg://domik:domik@localhost:5432/domik"
    database_echo: bool = False
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # --- LLM ---
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.3
    llm_timeout: float = 30.0
    llm_max_tool_iterations: int = 5
    llm_history_limit: int = 20

    # --- Excel ---
    excel_path: Path = Path("data/properties.xlsx")
    excel_sync_interval_seconds: int = 300

    # --- Bookings ---
    booking_slot_minutes: int = 30
    booking_buffer_minutes: int = 15
    booking_work_start: time = time(9, 0)
    booking_work_end: time = time(20, 0)
    booking_days_ahead: int = 14
    reminder_minutes_before: int = 15
    late_extension_minutes: int = 15

    @field_validator("owner_ids", mode="before")
    @classmethod
    def _parse_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.replace(";", ",").split(",") if part.strip()]
        if isinstance(value, int):
            return [value]
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key.get_secret_value())

    @property
    def webhook_url(self) -> str | None:
        if not self.webhook_base_url:
            return None
        return self.webhook_base_url.rstrip("/") + self.webhook_path

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
