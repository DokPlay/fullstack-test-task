from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, delete as sa_delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.models import ProcessingStatus, StoredFile

FileId = UUID | str


class FileRepository:
    async def list(
        self,
        session: AsyncSession,
        *,
        offset: int,
        limit: int,
    ) -> list[StoredFile]:
        result = await session.execute(
            select(StoredFile)
            .order_by(StoredFile.created_at.desc(), StoredFile.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get(self, session: AsyncSession, file_id: FileId) -> StoredFile | None:
        normalized_file_id = self._normalize_file_id(file_id)
        if normalized_file_id is None:
            return None
        return await session.get(StoredFile, normalized_file_id)

    async def get_many(
        self,
        session: AsyncSession,
        file_ids: Iterable[FileId],
    ) -> dict[UUID, StoredFile]:
        normalized_file_ids = self._normalize_file_ids(file_ids)
        if not normalized_file_ids:
            return {}

        result = await session.execute(
            select(StoredFile)
            .where(StoredFile.id.in_(normalized_file_ids))
            .execution_options(populate_existing=True),
        )
        return {file_item.id: file_item for file_item in result.scalars().all()}

    async def list_stuck_processing(
        self,
        session: AsyncSession,
        *,
        stale_before: datetime,
    ) -> list[StoredFile]:
        result = await session.execute(
            select(StoredFile)
            .where(self._is_stuck_processing(stale_before))
            .order_by(StoredFile.processing_started_at.asc())
        )
        return list(result.scalars().all())

    async def list_recoverable(
        self,
        session: AsyncSession,
        *,
        stale_before: datetime,
    ) -> list[StoredFile]:
        result = await session.execute(
            select(StoredFile)
            .where(self._is_recoverable(stale_before))
            .order_by(StoredFile.created_at.asc())
        )
        return list(result.scalars().all())

    async def claim_for_processing(
        self,
        session: AsyncSession,
        *,
        file_id: FileId,
        started_at: datetime,
        stale_before: datetime,
    ) -> StoredFile | None:
        normalized_file_id = self._normalize_file_id(file_id)
        if normalized_file_id is None:
            return None

        result = await session.execute(
            update(StoredFile)
            .where(StoredFile.id == normalized_file_id)
            .where(self._is_claimable_for_processing(stale_before))
            .values(
                processing_status=ProcessingStatus.PROCESSING,
                processing_started_at=started_at,
                processing_attempts=StoredFile.processing_attempts + 1,
            )
            .returning(StoredFile)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    def add(self, session: AsyncSession, file_item: StoredFile) -> None:
        session.add(file_item)

    async def delete(self, session: AsyncSession, file_item: StoredFile) -> None:
        await session.delete(file_item)

    async def delete_existing(self, session: AsyncSession, file_item: StoredFile) -> bool:
        result = await session.execute(sa_delete(StoredFile).where(StoredFile.id == file_item.id))
        return result.rowcount == 1

    @classmethod
    def _is_recoverable(cls, stale_before: datetime) -> ColumnElement[bool]:
        return or_(
            cls._is_stuck_processing(stale_before),
            cls._is_stale_uploaded(stale_before),
        )

    @classmethod
    def _is_claimable_for_processing(cls, stale_before: datetime) -> ColumnElement[bool]:
        return or_(
            cls._has_status(ProcessingStatus.UPLOADED),
            cls._is_processing_claim_expired(stale_before),
        )

    @classmethod
    def _is_processing_claim_expired(cls, stale_before: datetime) -> ColumnElement[bool]:
        return and_(
            cls._has_status(ProcessingStatus.PROCESSING),
            or_(
                StoredFile.processing_started_at.is_(None),
                StoredFile.processing_started_at <= stale_before,
            ),
        )

    @classmethod
    def _is_stuck_processing(cls, stale_before: datetime) -> ColumnElement[bool]:
        return and_(
            cls._has_status(ProcessingStatus.PROCESSING),
            or_(
                StoredFile.processing_started_at.is_(None),
                StoredFile.processing_started_at <= stale_before,
            ),
        )

    @classmethod
    def _is_stale_uploaded(cls, stale_before: datetime) -> ColumnElement[bool]:
        return and_(
            cls._has_status(ProcessingStatus.UPLOADED),
            StoredFile.created_at <= stale_before,
        )

    @staticmethod
    def _has_status(status: ProcessingStatus) -> ColumnElement[bool]:
        return StoredFile.processing_status == status

    @staticmethod
    def _normalize_file_id(file_id: FileId) -> UUID | None:
        if isinstance(file_id, UUID):
            return file_id
        try:
            return UUID(file_id)
        except ValueError:
            return None

    @classmethod
    def _normalize_file_ids(cls, file_ids: Iterable[FileId]) -> list[UUID]:
        normalized_file_ids: list[UUID] = []
        seen_file_ids: set[UUID] = set()

        for file_id in file_ids:
            normalized_file_id = cls._normalize_file_id(file_id)
            if normalized_file_id is None or normalized_file_id in seen_file_ids:
                continue

            normalized_file_ids.append(normalized_file_id)
            seen_file_ids.add(normalized_file_id)

        return normalized_file_ids
