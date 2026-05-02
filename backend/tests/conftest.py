from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from src.app import create_app
from src.core.container import ApplicationContainer, create_container
from src.core.settings import (
    DEFAULT_ALLOWED_ORIGINS,
    DEFAULT_MAX_FILE_SIZE_BYTES,
    DEFAULT_MAX_UPLOAD_SIZE_BYTES,
    DEFAULT_MAX_PROCESSING_ATTEMPTS,
    DEFAULT_PROCESSING_RECOVERY_INTERVAL_SECONDS,
    DEFAULT_PROCESSING_TIMEOUT_SECONDS,
    DEFAULT_DATABASE_POOL_MAX_OVERFLOW,
    DEFAULT_MAX_TITLE_LENGTH,
    DEFAULT_DATABASE_POOL_SIZE,
    DEFAULT_DASHBOARD_EVENTS_CHANNEL,
    DEFAULT_DASHBOARD_EVENTS_HEARTBEAT_SECONDS,
    DEFAULT_DASHBOARD_EVENTS_RETRY_TIMEOUT_MS,
    DEFAULT_DATABASE_POOL_RECYCLE_SECONDS,
    PDF_MIME_TYPES,
    SUSPICIOUS_EXTENSIONS,
    TEXT_MIME_PREFIX,
    Settings,
)
from src.core.storage import LocalFileStorage
from src.models import Base, ProcessingStatus, StoredFile
from src.services.events import InMemoryDashboardEventBus
from src.services.processing import FileProcessingService


@dataclass(slots=True)
class AppContext:
    app: object
    engine: AsyncEngine
    session_factory: async_sessionmaker
    processing_service: FileProcessingService
    processing_queue: "RecordingFileProcessingQueue"
    queued_ids: list[str]
    storage: LocalFileStorage
    settings: Settings
    event_bus: InMemoryDashboardEventBus
    container: ApplicationContainer


@dataclass(slots=True)
class RecordingFileProcessingQueue:
    queued_ids: list[str]
    fail_enqueue: bool = False

    def enqueue_file_processing(self, file_id: str) -> None:
        if self.fail_enqueue:
            raise RuntimeError("Queue is unavailable")
        self.queued_ids.append(file_id)


def build_test_settings(storage_dir: Path) -> Settings:
    return Settings(
        postgres_user="postgres",
        postgres_password="postgres",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="test",
        redis_url="redis://localhost:6379/0",
        storage_dir=storage_dir,
        allowed_origins=DEFAULT_ALLOWED_ORIGINS,
        suspicious_extensions=SUSPICIOUS_EXTENSIONS,
        pdf_mime_types=PDF_MIME_TYPES,
        text_mime_prefix=TEXT_MIME_PREFIX,
        max_file_size_bytes=DEFAULT_MAX_FILE_SIZE_BYTES,
        max_upload_size_bytes=DEFAULT_MAX_UPLOAD_SIZE_BYTES,
        max_title_length=DEFAULT_MAX_TITLE_LENGTH,
        processing_timeout_seconds=DEFAULT_PROCESSING_TIMEOUT_SECONDS,
        processing_recovery_interval_seconds=DEFAULT_PROCESSING_RECOVERY_INTERVAL_SECONDS,
        max_processing_attempts=DEFAULT_MAX_PROCESSING_ATTEMPTS,
        database_pool_size=DEFAULT_DATABASE_POOL_SIZE,
        database_pool_max_overflow=DEFAULT_DATABASE_POOL_MAX_OVERFLOW,
        database_pool_recycle_seconds=DEFAULT_DATABASE_POOL_RECYCLE_SECONDS,
        dashboard_events_channel=DEFAULT_DASHBOARD_EVENTS_CHANNEL,
        dashboard_events_heartbeat_seconds=DEFAULT_DASHBOARD_EVENTS_HEARTBEAT_SECONDS,
        dashboard_events_retry_timeout_ms=DEFAULT_DASHBOARD_EVENTS_RETRY_TIMEOUT_MS,
    )


@pytest_asyncio.fixture
async def test_context(tmp_path: Path) -> AppContext:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(database_url, future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    storage = LocalFileStorage(tmp_path / "storage")
    settings = build_test_settings(storage.root_dir)
    queued_ids: list[str] = []
    processing_queue = RecordingFileProcessingQueue(queued_ids=queued_ids)
    event_bus = InMemoryDashboardEventBus(
        heartbeat_seconds=1,
        retry_timeout_ms=settings.dashboard_events_retry_timeout_ms,
    )

    container = create_container(
        settings=settings,
        session_factory=session_factory,
        storage=storage,
        event_bus=event_bus,
        processing_queue=processing_queue,
    )
    processing_service = container.processing_service

    app = create_app(container=container)

    try:
        yield AppContext(
            app=app,
            engine=engine,
            session_factory=session_factory,
            processing_service=processing_service,
            processing_queue=processing_queue,
            queued_ids=queued_ids,
            storage=storage,
            settings=settings,
            event_bus=event_bus,
            container=container,
        )
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(test_context: AppContext) -> AsyncClient:
    transport = ASGITransport(app=test_context.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


async def mark_file_as_stuck(
    *,
    app_context: AppContext,
    file_id: str,
    attempts: int,
) -> None:
    async with app_context.session_factory() as session:
        file_item = await session.get(StoredFile, UUID(file_id))
        if not file_item:
            raise AssertionError(f"File {file_id} was not created")

        file_item.processing_status = ProcessingStatus.PROCESSING
        file_item.processing_started_at = datetime.now(timezone.utc) - timedelta(
            seconds=app_context.settings.processing_timeout_seconds + 5
        )
        file_item.processing_attempts = attempts
        await session.commit()


async def mark_file_as_stale_uploaded(
    *,
    app_context: AppContext,
    file_id: str,
    attempts: int = 0,
) -> None:
    async with app_context.session_factory() as session:
        file_item = await session.get(StoredFile, UUID(file_id))
        if not file_item:
            raise AssertionError(f"File {file_id} was not created")

        stale_timestamp = datetime.now(timezone.utc) - timedelta(
            seconds=app_context.settings.processing_timeout_seconds + 5
        )
        file_item.processing_status = ProcessingStatus.UPLOADED
        file_item.processing_started_at = None
        file_item.created_at = stale_timestamp
        file_item.updated_at = stale_timestamp
        file_item.processing_attempts = attempts
        await session.commit()
