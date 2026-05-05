from __future__ import annotations

import asyncio
import errno
from datetime import datetime, timezone
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.models import Alert, ProcessingStatus, ScanStatus, StoredFile
from tests.conftest import AppContext


@pytest.mark.asyncio
async def test_parallel_delete_is_idempotent(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    response = await client.post(
        "/files",
        data={"title": "Parallel delete"},
        files={"file": ("parallel.txt", b"delete once", "text/plain")},
    )
    assert response.status_code == 201
    created = response.json()
    file_service = test_context.container.file_service
    original_publisher = file_service.notify_dashboard_change
    published_delete_events: list[str] = []

    async def record_dashboard_change(event) -> None:
        if event.event_type == "file.deleted":
            published_delete_events.append(event.event_type)

    file_service.notify_dashboard_change = record_dashboard_change

    try:
        first_response, second_response = await asyncio.gather(
            client.delete(f"/files/{created['id']}"),
            client.delete(f"/files/{created['id']}"),
        )

        assert sorted([first_response.status_code, second_response.status_code]) == [204, 404]
        assert published_delete_events == ["file.deleted"]
        assert not await test_context.storage.exists(f"{created['id']}.txt")

        file_response = await client.get(f"/files/{created['id']}")
        assert file_response.status_code == 404
    finally:
        file_service.notify_dashboard_change = original_publisher


@pytest.mark.asyncio
async def test_redis_publish_failure_does_not_break_file_flow(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    async def fail_publish(_event) -> None:
        raise ConnectionError("Redis connection dropped")

    file_service = test_context.container.file_service
    processing_service = test_context.container.processing_service
    original_file_publisher = file_service.notify_dashboard_change
    original_processing_publisher = processing_service.notify_dashboard_change
    file_service.notify_dashboard_change = fail_publish
    processing_service.notify_dashboard_change = fail_publish

    try:
        response = await client.post(
            "/files",
            data={"title": "Redis failure"},
            files={"file": ("redis.txt", b"redis can be down", "text/plain")},
        )
        assert response.status_code == 201
        created = response.json()
        assert test_context.queued_ids == [created["id"]]

        await processing_service.process_file(created["id"])

        file_response = await client.get(f"/files/{created['id']}")
        assert file_response.status_code == 200
        file_payload = file_response.json()
        assert file_payload["processing_status"] == "processed"
        assert file_payload["scan_status"] == "clean"
    finally:
        file_service.notify_dashboard_change = original_file_publisher
        processing_service.notify_dashboard_change = original_processing_publisher


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "storage_error",
    [
        OSError(errno.ENOSPC, "No space left on device"),
        PermissionError(errno.EACCES, "Permission denied"),
    ],
)
async def test_storage_save_errors_do_not_create_database_rows_or_queue_jobs(
    client: AsyncClient,
    test_context: AppContext,
    monkeypatch: pytest.MonkeyPatch,
    storage_error: OSError,
) -> None:
    async def fail_save_upload(*_args, **_kwargs):
        raise storage_error

    monkeypatch.setattr(test_context.storage, "save_upload", fail_save_upload)

    with pytest.raises(type(storage_error)):
        await client.post(
            "/files",
            data={"title": "Storage failure"},
            files={"file": ("storage.txt", b"cannot persist", "text/plain")},
        )

    assert test_context.queued_ids == []

    files_response = await client.get("/files")
    assert files_response.status_code == 200
    assert files_response.json() == []
    assert not test_context.storage.root_dir.exists()


@pytest.mark.asyncio
async def test_process_file_pipeline_rolls_back_uncommitted_changes_on_error(
    client: AsyncClient,
    test_context: AppContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await client.post(
        "/files",
        data={"title": "Rollback pipeline"},
        files={"file": ("rollback.txt", b"rollback payload", "text/plain")},
    )
    assert response.status_code == 201
    created = response.json()
    file_id = UUID(created["id"])

    async with test_context.session_factory() as session:
        file_item = await session.get(StoredFile, file_id)
        assert file_item is not None
        file_item.processing_status = ProcessingStatus.PROCESSING
        file_item.processing_started_at = datetime.now(timezone.utc)
        file_item.processing_attempts = 1
        await session.commit()

    def fail_alert_add(_session, _alert) -> None:
        raise RuntimeError("alert insert failed")

    monkeypatch.setattr(test_context.processing_service.alert_repository, "add", fail_alert_add)

    with pytest.raises(RuntimeError, match="alert insert failed"):
        await test_context.processing_service._process_file_pipeline(created["id"])

    async with test_context.session_factory() as session:
        file_item = await session.get(StoredFile, file_id)
        assert file_item is not None
        assert file_item.processing_status == ProcessingStatus.PROCESSING
        assert file_item.processing_started_at is not None
        assert file_item.processing_attempts == 1
        assert file_item.metadata_json is None
        assert file_item.requires_attention is False
        assert file_item.scan_status is None
        assert file_item.scan_details is None

        alerts = (await session.execute(select(Alert))).scalars().all()
        assert alerts == []
