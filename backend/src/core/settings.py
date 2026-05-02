from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)
SUSPICIOUS_EXTENSIONS = frozenset({".exe", ".bat", ".cmd", ".sh", ".js"})
TEXT_MIME_PREFIX = "text/"
PDF_MIME_TYPES = frozenset({"application/pdf", "application/octet-stream"})
DEFAULT_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_TITLE_LENGTH = 255
DEFAULT_PROCESSING_TIMEOUT_SECONDS = 120
DEFAULT_PROCESSING_RECOVERY_INTERVAL_SECONDS = 30
DEFAULT_MAX_PROCESSING_ATTEMPTS = 3
DEFAULT_DATABASE_POOL_SIZE = 10
DEFAULT_DATABASE_POOL_MAX_OVERFLOW = 10
DEFAULT_DATABASE_POOL_RECYCLE_SECONDS = 1800
DEFAULT_DASHBOARD_EVENTS_CHANNEL = "dashboard-events"
DEFAULT_DASHBOARD_EVENTS_HEARTBEAT_SECONDS = 15
DEFAULT_DASHBOARD_EVENTS_RETRY_TIMEOUT_MS = 3000


@dataclass(frozen=True, slots=True)
class Settings:
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    postgres_db: str
    redis_url: str
    storage_dir: Path
    allowed_origins: tuple[str, ...]
    suspicious_extensions: frozenset[str]
    pdf_mime_types: frozenset[str]
    text_mime_prefix: str
    max_file_size_bytes: int
    max_upload_size_bytes: int
    max_title_length: int
    processing_timeout_seconds: int
    processing_recovery_interval_seconds: int
    max_processing_attempts: int
    database_pool_size: int
    database_pool_max_overflow: int
    database_pool_recycle_seconds: int
    dashboard_events_channel: str
    dashboard_events_heartbeat_seconds: int
    dashboard_events_retry_timeout_ms: int

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def __post_init__(self) -> None:
        if self.max_file_size_bytes <= 0:
            raise ValueError("max_file_size_bytes must be greater than zero")
        if self.max_upload_size_bytes <= 0:
            raise ValueError("max_upload_size_bytes must be greater than zero")
        if self.max_upload_size_bytes < self.max_file_size_bytes:
            raise ValueError(
                "max_upload_size_bytes must be greater than or equal to max_file_size_bytes"
            )
        if self.database_pool_size <= 0:
            raise ValueError("database_pool_size must be greater than zero")
        if self.database_pool_max_overflow < 0:
            raise ValueError("database_pool_max_overflow must not be negative")
        if self.database_pool_recycle_seconds <= 0:
            raise ValueError("database_pool_recycle_seconds must be greater than zero")


def _parse_allowed_origins(raw_value: str | None) -> tuple[str, ...]:
    if not raw_value:
        return DEFAULT_ALLOWED_ORIGINS
    origins = [value.strip() for value in raw_value.split(",") if value.strip()]
    return tuple(origins) or DEFAULT_ALLOWED_ORIGINS


def _parse_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    value = int(raw_value)
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _parse_non_negative_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    value = int(raw_value)
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    backend_dir = Path(__file__).resolve().parents[2]
    storage_dir = backend_dir / "storage" / "files"

    postgres_port = int(os.getenv("POSTGRES_PORT", os.getenv("PGPORT", "5432")))
    redis_url = os.getenv("REDIS_URL", os.getenv("CELERY_BROKER_URL", "redis://backend-redis:6379/0"))

    return Settings(
        postgres_user=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        postgres_host=os.getenv("POSTGRES_HOST", "backend-db"),
        postgres_port=postgres_port,
        postgres_db=os.getenv("POSTGRES_DB", "test"),
        redis_url=redis_url,
        storage_dir=storage_dir,
        allowed_origins=_parse_allowed_origins(os.getenv("ALLOWED_ORIGINS")),
        suspicious_extensions=SUSPICIOUS_EXTENSIONS,
        pdf_mime_types=PDF_MIME_TYPES,
        text_mime_prefix=TEXT_MIME_PREFIX,
        max_file_size_bytes=_parse_positive_int(
            "MAX_FILE_SIZE_BYTES",
            DEFAULT_MAX_FILE_SIZE_BYTES,
        ),
        max_upload_size_bytes=_parse_positive_int(
            "MAX_UPLOAD_SIZE_BYTES",
            DEFAULT_MAX_UPLOAD_SIZE_BYTES,
        ),
        max_title_length=DEFAULT_MAX_TITLE_LENGTH,
        processing_timeout_seconds=int(
            os.getenv("PROCESSING_TIMEOUT_SECONDS", str(DEFAULT_PROCESSING_TIMEOUT_SECONDS))
        ),
        processing_recovery_interval_seconds=int(
            os.getenv(
                "PROCESSING_RECOVERY_INTERVAL_SECONDS",
                str(DEFAULT_PROCESSING_RECOVERY_INTERVAL_SECONDS),
            )
        ),
        max_processing_attempts=int(
            os.getenv("MAX_PROCESSING_ATTEMPTS", str(DEFAULT_MAX_PROCESSING_ATTEMPTS))
        ),
        database_pool_size=_parse_positive_int(
            "DATABASE_POOL_SIZE",
            DEFAULT_DATABASE_POOL_SIZE,
        ),
        database_pool_max_overflow=_parse_non_negative_int(
            "DATABASE_POOL_MAX_OVERFLOW",
            DEFAULT_DATABASE_POOL_MAX_OVERFLOW,
        ),
        database_pool_recycle_seconds=_parse_positive_int(
            "DATABASE_POOL_RECYCLE_SECONDS",
            DEFAULT_DATABASE_POOL_RECYCLE_SECONDS,
        ),
        dashboard_events_channel=os.getenv(
            "DASHBOARD_EVENTS_CHANNEL",
            DEFAULT_DASHBOARD_EVENTS_CHANNEL,
        ),
        dashboard_events_heartbeat_seconds=int(
            os.getenv(
                "DASHBOARD_EVENTS_HEARTBEAT_SECONDS",
                str(DEFAULT_DASHBOARD_EVENTS_HEARTBEAT_SECONDS),
            )
        ),
        dashboard_events_retry_timeout_ms=int(
            os.getenv(
                "DASHBOARD_EVENTS_RETRY_TIMEOUT_MS",
                str(DEFAULT_DASHBOARD_EVENTS_RETRY_TIMEOUT_MS),
            )
        ),
    )
