from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.database import Database, create_database
from src.core.settings import Settings, get_settings
from src.core.storage import LocalFileStorage
from src.repositories.alerts import AlertRepository
from src.repositories.files import FileRepository
from src.services.alerts import AlertService
from src.services.events import DashboardEventBus, DashboardEventStream
from src.services.files import FileService
from src.services.processing import FileProcessingService
from src.services.queue import FileProcessingQueue


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    settings: Settings
    database: Database | None
    session_factory: async_sessionmaker[AsyncSession]
    storage: LocalFileStorage
    file_repository: FileRepository
    alert_repository: AlertRepository
    event_bus: DashboardEventStream
    file_service: FileService
    alert_service: AlertService
    processing_service: FileProcessingService

    async def aclose(self) -> None:
        await self.event_bus.aclose()
        if self.database is not None:
            await self.database.aclose()


def create_container(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    storage: LocalFileStorage | None = None,
    file_repository: FileRepository | None = None,
    alert_repository: AlertRepository | None = None,
    event_bus: DashboardEventStream | None = None,
    processing_queue: FileProcessingQueue | None = None,
) -> ApplicationContainer:
    resolved_settings = settings or get_settings()
    resolved_database = database
    if session_factory is None:
        resolved_database = resolved_database or create_database(
            resolved_settings.database_url,
            pool_size=resolved_settings.database_pool_size,
            pool_max_overflow=resolved_settings.database_pool_max_overflow,
            pool_recycle_seconds=resolved_settings.database_pool_recycle_seconds,
        )
        resolved_session_factory = resolved_database.session_factory
    else:
        resolved_session_factory = session_factory
    resolved_storage = storage or LocalFileStorage(resolved_settings.storage_dir)
    resolved_file_repository = file_repository or FileRepository()
    resolved_alert_repository = alert_repository or AlertRepository()
    resolved_event_bus = event_bus or DashboardEventBus(resolved_settings)

    file_service = FileService(
        session_factory=resolved_session_factory,
        storage=resolved_storage,
        settings=resolved_settings,
        processing_queue=processing_queue,
        notify_dashboard_change=resolved_event_bus.publish,
        repository=resolved_file_repository,
    )
    alert_service = AlertService(
        session_factory=resolved_session_factory,
        repository=resolved_alert_repository,
    )
    processing_service = FileProcessingService(
        session_factory=resolved_session_factory,
        storage=resolved_storage,
        settings=resolved_settings,
        file_repository=resolved_file_repository,
        alert_repository=resolved_alert_repository,
        notify_dashboard_change=resolved_event_bus.publish,
    )

    return ApplicationContainer(
        settings=resolved_settings,
        database=resolved_database,
        session_factory=resolved_session_factory,
        storage=resolved_storage,
        file_repository=resolved_file_repository,
        alert_repository=resolved_alert_repository,
        event_bus=resolved_event_bus,
        file_service=file_service,
        alert_service=alert_service,
        processing_service=processing_service,
    )
