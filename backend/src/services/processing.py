from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.settings import Settings
from src.core.storage import LocalFileStorage
from src.models import Alert, ProcessingStatus, ScanStatus, StoredFile
from src.repositories.alerts import AlertRepository
from src.repositories.files import FileRepository
from src.schemas import DashboardPatchEvent
from src.monitoring import add_active_processing, count_scanned_file, count_suspicious_file
from src.services.events import build_dashboard_patch, publish_dashboard_change_safely


logger = logging.getLogger(__name__)


class FileProcessingService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: LocalFileStorage,
        settings: Settings,
        file_repository: FileRepository | None = None,
        alert_repository: AlertRepository | None = None,
        notify_dashboard_change: Callable[[DashboardPatchEvent], Awaitable[None]] | None = None,
    ):
        self.session_factory = session_factory
        self.storage = storage
        self.settings = settings
        self.file_repository = file_repository or FileRepository()
        self.alert_repository = alert_repository or AlertRepository()
        self.notify_dashboard_change = notify_dashboard_change

    async def process_file(self, file_id: str | UUID) -> None:
        now = self._utcnow()
        stale_before = now - timedelta(seconds=self.settings.processing_timeout_seconds)
        started_patch: DashboardPatchEvent | None = None
        processing_started = False
        async with self.session_factory() as session:
            file_item = await self.file_repository.claim_for_processing(
                session,
                file_id=file_id,
                started_at=now,
                stale_before=stale_before,
            )
            if file_item is None:
                return

            await session.commit()
            await session.refresh(file_item)
            started_patch = build_dashboard_patch("file.processing.started", file=file_item)
            processing_started = True

        if started_patch is not None:
            await publish_dashboard_change_safely(
                self.notify_dashboard_change,
                started_patch,
                source_logger=logger,
            )

        if processing_started:
            add_active_processing(1)
        try:
            await self._process_file_pipeline(file_id)
        except Exception:
            logger.exception("Unexpected error while processing file %s", file_id)
            await self._mark_failed(file_id, "unexpected processing error")
        finally:
            if processing_started:
                add_active_processing(-1)

    async def _process_file_pipeline(self, file_id: str | UUID) -> None:
        completion_patch: DashboardPatchEvent | None = None
        async with self.session_factory() as session:
            file_item = await self.file_repository.get(session, file_id)
            if not file_item:
                return
            if file_item.processing_status != ProcessingStatus.PROCESSING:
                return

            reasons = self._collect_scan_reasons(file_item)

            if not await self.storage.exists(file_item.stored_name):
                await self._apply_failure(
                    session,
                    file_item,
                    "stored file not found during processing",
                )
                return

            metadata = await self.storage.collect_metadata(
                stored_name=file_item.stored_name,
                original_name=file_item.original_name,
                mime_type=file_item.mime_type,
                size=file_item.size,
            )

            file_item.metadata_json = metadata
            file_item.processing_status = ProcessingStatus.PROCESSED
            file_item.processing_started_at = None
            file_item.requires_attention = bool(reasons)
            file_item.scan_status = (
                ScanStatus.SUSPICIOUS if file_item.requires_attention else ScanStatus.CLEAN
            )
            file_item.scan_details = ", ".join(reasons) if file_item.requires_attention else "no threats found"

            alert = self._build_alert(file_item)
            self.alert_repository.add(session, alert)
            await session.commit()
            await session.refresh(file_item)
            await session.refresh(alert)
            completion_patch = build_dashboard_patch(
                "file.processing.completed",
                file=file_item,
                alert=alert,
            )
            count_scanned_file()
            if file_item.requires_attention:
                count_suspicious_file()

        if completion_patch is not None:
            await publish_dashboard_change_safely(
                self.notify_dashboard_change,
                completion_patch,
                source_logger=logger,
            )

    async def recover_stuck_files(self) -> list[str]:
        stale_before = self._utcnow() - timedelta(seconds=self.settings.processing_timeout_seconds)
        file_ids_to_retry: list[str] = []
        patches_to_publish: list[DashboardPatchEvent] = []

        async with self.session_factory() as session:
            recoverable_files = await self.file_repository.list_recoverable(
                session,
                stale_before=stale_before,
            )
            if not recoverable_files:
                return []

            failed_alerts: list[tuple[StoredFile, Alert]] = []

            for file_item in recoverable_files:
                if file_item.processing_attempts >= self.settings.max_processing_attempts:
                    self._apply_failure_state(
                        file_item,
                        "processing timed out and max retry count was reached",
                    )
                    alert = Alert(
                        file_id=file_item.id,
                        level="critical",
                        message="File processing failed after repeated recovery attempts",
                    )
                    self.alert_repository.add(session, alert)
                    failed_alerts.append((file_item, alert))
                    continue

                file_item.processing_status = ProcessingStatus.UPLOADED
                file_item.processing_started_at = None
                file_item.scan_status = None
                file_item.scan_details = None
                file_item.metadata_json = None
                file_item.requires_attention = False
                file_ids_to_retry.append(str(file_item.id))

            if failed_alerts:
                await session.flush()
            changed_file_ids = [file_item.id for file_item in recoverable_files]
            failed_alert_ids = [
                alert.id
                for _, alert in failed_alerts
                if alert.id is not None
            ]

            await session.commit()

            files_by_id = await self.file_repository.get_many(session, changed_file_ids)
            alerts_by_id = await self.alert_repository.get_many(session, failed_alert_ids)

            for original_file_item in recoverable_files:
                file_item = files_by_id.get(original_file_item.id, original_file_item)
                if file_item.processing_status == ProcessingStatus.UPLOADED:
                    patches_to_publish.append(
                        build_dashboard_patch("file.processing.requeued", file=file_item),
                    )

            for original_file_item, original_alert in failed_alerts:
                file_item = files_by_id.get(original_file_item.id, original_file_item)
                alert = alerts_by_id.get(original_alert.id, original_alert)
                patches_to_publish.append(
                    build_dashboard_patch(
                        "file.processing.failed",
                        file=file_item,
                        alert=alert,
                    ),
                )

        for patch in patches_to_publish:
            await publish_dashboard_change_safely(
                self.notify_dashboard_change,
                patch,
                source_logger=logger,
            )

        return file_ids_to_retry

    async def _mark_failed(self, file_id: str | UUID, reason: str) -> None:
        async with self.session_factory() as session:
            file_item = await self.file_repository.get(session, file_id)
            if not file_item:
                return
            await self._apply_failure(session, file_item, reason)

    async def _apply_failure(self, session: AsyncSession, file_item: StoredFile, reason: str) -> None:
        self._apply_failure_state(file_item, reason)
        alert = Alert(file_id=file_item.id, level="critical", message="File processing failed")
        self.alert_repository.add(session, alert)
        await session.commit()
        await session.refresh(file_item)
        await session.refresh(alert)
        await publish_dashboard_change_safely(
            self.notify_dashboard_change,
            build_dashboard_patch(
                "file.processing.failed",
                file=file_item,
                alert=alert,
            ),
            source_logger=logger,
        )

    @staticmethod
    def _apply_failure_state(file_item: StoredFile, reason: str) -> None:
        file_item.processing_status = ProcessingStatus.FAILED
        file_item.processing_started_at = None
        file_item.scan_status = ScanStatus.FAILED
        file_item.scan_details = reason
        file_item.requires_attention = True

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    def _collect_scan_reasons(self, file_item: StoredFile) -> list[str]:
        reasons: list[str] = []
        extension = Path(file_item.original_name).suffix.lower()

        if extension in self.settings.suspicious_extensions:
            reasons.append(f"suspicious extension {extension}")

        if file_item.size > self.settings.max_file_size_bytes:
            reasons.append(f"file is larger than {self.settings.max_file_size_bytes // (1024 * 1024)} MB")

        if extension == ".pdf" and file_item.mime_type not in self.settings.pdf_mime_types:
            reasons.append("pdf extension does not match mime type")

        return reasons

    @staticmethod
    def _build_alert(file_item: StoredFile) -> Alert:
        if file_item.requires_attention:
            return Alert(
                file_id=file_item.id,
                level="warning",
                message=f"File requires attention: {file_item.scan_details}",
            )

        return Alert(
            file_id=file_item.id,
            level="info",
            message="File processed successfully",
        )
