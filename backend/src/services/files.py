from __future__ import annotations

import logging
from pathlib import Path
from typing import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.pagination import DEFAULT_PAGE_LIMIT
from src.core.settings import Settings
from src.core.storage import LocalFileStorage, UploadSizeLimitExceededError
from src.models import ProcessingStatus, StoredFile
from src.repositories.files import FileRepository
from src.schemas import DashboardPatchEvent
from src.services.events import build_dashboard_patch, publish_dashboard_change_safely
from src.services.queue import FileProcessingQueue


logger = logging.getLogger(__name__)


class FileService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: LocalFileStorage,
        settings: Settings,
        processing_queue: FileProcessingQueue | None = None,
        notify_dashboard_change: Callable[[DashboardPatchEvent], Awaitable[None]] | None = None,
        repository: FileRepository | None = None,
    ):
        self.session_factory = session_factory
        self.storage = storage
        self.settings = settings
        self.processing_queue = processing_queue
        self.notify_dashboard_change = notify_dashboard_change
        self.repository = repository or FileRepository()

    async def list_files(
        self,
        *,
        offset: int = 0,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> list[StoredFile]:
        async with self.session_factory() as session:
            return await self.repository.list(session, offset=offset, limit=limit)

    async def get_file(self, file_id: str | UUID) -> StoredFile:
        async with self.session_factory() as session:
            file_item = await self.repository.get(session, file_id)
            if not file_item:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
            return file_item

    async def create_file(self, title: str, upload_file: UploadFile) -> StoredFile:
        normalized_title = self._normalize_title(title)
        file_id = uuid4()
        try:
            stored_upload = await self.storage.save_upload(
                upload_file,
                str(file_id),
                max_size_bytes=self.settings.max_upload_size_bytes,
            )
        except UploadSizeLimitExceededError as exc:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds maximum upload size of {exc.max_size_bytes} bytes",
            ) from exc

        if stored_upload.size == 0:
            await self.storage.delete(stored_upload.stored_name)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")

        file_item = StoredFile(
            id=file_id,
            title=normalized_title,
            original_name=stored_upload.original_name,
            stored_name=stored_upload.stored_name,
            mime_type=stored_upload.mime_type,
            size=stored_upload.size,
            processing_status=ProcessingStatus.UPLOADED,
            scan_status=None,
            scan_details=None,
            metadata_json=None,
            requires_attention=False,
        )

        try:
            async with self.session_factory() as session:
                self.repository.add(session, file_item)
                await session.commit()
                await session.refresh(file_item)
        except Exception:
            await self.storage.delete(stored_upload.stored_name)
            raise

        self._dispatch_processing(file_item.id)
        await publish_dashboard_change_safely(
            self.notify_dashboard_change,
            build_dashboard_patch("file.created", file=file_item),
            source_logger=logger,
        )
        return file_item

    async def update_file(self, file_id: str | UUID, title: str) -> StoredFile:
        normalized_title = self._normalize_title(title)

        async with self.session_factory() as session:
            file_item = await self.repository.get(session, file_id)
            if not file_item:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

            file_item.title = normalized_title
            await session.commit()
            await session.refresh(file_item)
            patch = build_dashboard_patch("file.updated", file=file_item)

        await publish_dashboard_change_safely(
            self.notify_dashboard_change,
            patch,
            source_logger=logger,
        )
        return file_item

    async def delete_file(self, file_id: str | UUID) -> None:
        async with self.session_factory() as session:
            file_item = await self.repository.get(session, file_id)
            if not file_item:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

            stored_name = file_item.stored_name
            normalized_file_id = file_item.id
            staged_path = await self.storage.stage_for_deletion(stored_name)
            try:
                deleted = await self.repository.delete_existing(session, file_item)
                if not deleted:
                    await session.rollback()
                    if staged_path is not None:
                        await self.storage.restore_after_failed_delete(staged_path, stored_name)
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

                await session.commit()
            except HTTPException:
                raise
            except Exception:
                await session.rollback()
                if staged_path is not None:
                    await self.storage.restore_after_failed_delete(staged_path, stored_name)
                raise

        await self.storage.finalize_staged_delete(staged_path)
        await publish_dashboard_change_safely(
            self.notify_dashboard_change,
            build_dashboard_patch(
                "file.deleted",
                removed_file_id=str(normalized_file_id),
                removed_alerts_for_file_id=str(normalized_file_id),
            ),
            source_logger=logger,
        )

    async def get_file_path(self, file_id: str | UUID) -> tuple[StoredFile, Path]:
        file_item = await self.get_file(file_id)
        stored_path = self.storage.resolve(file_item.stored_name)
        if not await self.storage.exists(file_item.stored_name):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file not found")
        return file_item, stored_path

    def _dispatch_processing(self, file_id: str | UUID) -> None:
        if self.processing_queue is None:
            return

        try:
            self.processing_queue.enqueue_file_processing(str(file_id))
        except Exception:
            logger.exception("Failed to enqueue processing for file %s", file_id)

    def _normalize_title(self, title: str) -> str:
        normalized = title.strip()
        if not normalized:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Title must not be empty")
        if len(normalized) > self.settings.max_title_length:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Title must be at most {self.settings.max_title_length} characters",
            )
        return normalized
