from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import Enum as SQLEnum, Uuid
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from src.models import Alert, ProcessingStatus, ScanStatus, StoredFile
from src.repositories.files import FileRepository
from tests.conftest import AppContext, mark_file_as_stale_uploaded, mark_file_as_stuck


def test_file_identifiers_use_uuid_columns() -> None:
    assert isinstance(StoredFile.__table__.c.id.type, Uuid)
    assert isinstance(Alert.__table__.c.file_id.type, Uuid)


def test_file_metadata_uses_jsonb_on_postgresql() -> None:
    metadata_type = StoredFile.__table__.c.metadata_json.type
    assert isinstance(metadata_type.dialect_impl(postgresql.dialect()), JSONB)


def test_file_statuses_use_sqlalchemy_enums() -> None:
    processing_type = StoredFile.__table__.c.processing_status.type
    scan_type = StoredFile.__table__.c.scan_status.type

    assert isinstance(processing_type, SQLEnum)
    assert isinstance(scan_type, SQLEnum)
    assert processing_type.enums == [status.value for status in ProcessingStatus]
    assert scan_type.enums == [status.value for status in ScanStatus]


@pytest.mark.asyncio
async def test_upload_process_and_alert_flow(client: AsyncClient, test_context: AppContext) -> None:
    response = await client.post(
        "/files",
        data={"title": "  Project notes  "},
        files={"file": ("notes.txt", b"first line\nsecond line\n", "text/plain")},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["title"] == "Project notes"
    assert created["processing_status"] == "uploaded"
    assert created["scan_status"] is None
    assert test_context.queued_ids == [created["id"]]

    await test_context.processing_service.process_file(created["id"])

    file_response = await client.get(f"/files/{created['id']}")
    assert file_response.status_code == 200
    file_payload = file_response.json()
    assert file_payload["processing_status"] == "processed"
    assert file_payload["scan_status"] == "clean"
    assert file_payload["metadata_json"]["line_count"] == 2
    assert file_payload["metadata_json"]["char_count"] == 23

    alerts_response = await client.get("/alerts")
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()
    assert len(alerts) == 1
    assert alerts[0]["level"] == "info"


@pytest.mark.asyncio
async def test_suspicious_files_remain_downloadable(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    payload = b"#!/bin/sh\necho suspicious but retained\n"
    response = await client.post(
        "/files",
        data={"title": "Script upload"},
        files={"file": ("deploy.sh", payload, "text/x-shellscript")},
    )
    assert response.status_code == 201
    created = response.json()

    await test_context.processing_service.process_file(created["id"])

    file_response = await client.get(f"/files/{created['id']}")
    assert file_response.status_code == 200
    file_payload = file_response.json()
    assert file_payload["scan_status"] == "suspicious"
    assert file_payload["requires_attention"] is True

    download_response = await client.get(f"/files/{created['id']}/download")
    assert download_response.status_code == 200
    assert download_response.content == payload


@pytest.mark.asyncio
async def test_upload_rejects_files_over_upload_limit(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    test_context.container.file_service.settings = replace(
        test_context.settings,
        max_file_size_bytes=4,
        max_upload_size_bytes=4,
    )

    response = await client.post(
        "/files",
        data={"title": "Too large"},
        files={"file": ("too-large.txt", b"12345", "text/plain")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "File exceeds maximum upload size of 4 bytes"
    assert test_context.queued_ids == []
    assert list(test_context.storage.root_dir.iterdir()) == []

    files_response = await client.get("/files")
    assert files_response.status_code == 200
    assert files_response.json() == []


@pytest.mark.asyncio
async def test_list_files_is_paginated(client: AsyncClient) -> None:
    for index in range(3):
        response = await client.post(
            "/files",
            data={"title": f"Paginated file {index}"},
            files={"file": (f"page-{index}.txt", f"payload {index}".encode(), "text/plain")},
        )
        assert response.status_code == 201

    full_response = await client.get("/files")
    assert full_response.status_code == 200
    full_payload = full_response.json()
    assert len(full_payload) == 3

    page_response = await client.get("/files", params={"offset": 1, "limit": 1})
    assert page_response.status_code == 200
    assert page_response.json() == [full_payload[1]]

    invalid_response = await client.get("/files", params={"limit": 0})
    assert invalid_response.status_code == 422


@pytest.mark.asyncio
async def test_list_alerts_is_paginated(client: AsyncClient, test_context: AppContext) -> None:
    for index in range(3):
        response = await client.post(
            "/files",
            data={"title": f"Alert page {index}"},
            files={"file": (f"alert-page-{index}.txt", f"payload {index}".encode(), "text/plain")},
        )
        assert response.status_code == 201
        await test_context.processing_service.process_file(response.json()["id"])

    full_response = await client.get("/alerts")
    assert full_response.status_code == 200
    full_payload = full_response.json()
    assert len(full_payload) == 3

    page_response = await client.get("/alerts", params={"offset": 1, "limit": 1})
    assert page_response.status_code == 200
    assert page_response.json() == [full_payload[1]]

    invalid_response = await client.get("/alerts", params={"limit": 0})
    assert invalid_response.status_code == 422


@pytest.mark.asyncio
async def test_delete_after_processing_removes_alerts_and_binary(client: AsyncClient, test_context: AppContext) -> None:
    response = await client.post(
        "/files",
        data={"title": "Deploy script"},
        files={"file": ("deploy.sh", b"#!/bin/sh\necho hello\n", "text/plain")},
    )
    created = response.json()

    await test_context.processing_service.process_file(created["id"])

    actual_path = test_context.storage.resolve(f"{created['id']}.sh")
    assert actual_path.exists()

    delete_response = await client.delete(f"/files/{created['id']}")
    assert delete_response.status_code == 204
    assert not actual_path.exists()

    file_response = await client.get(f"/files/{created['id']}")
    assert file_response.status_code == 404

    alerts_response = await client.get("/alerts")
    assert alerts_response.status_code == 200
    assert alerts_response.json() == []


@pytest.mark.asyncio
async def test_delete_existing_reports_when_row_was_already_removed(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    response = await client.post(
        "/files",
        data={"title": "Delete rowcount"},
        files={"file": ("rowcount.txt", b"rowcount", "text/plain")},
    )
    created = response.json()
    repository = test_context.container.file_repository

    async with test_context.session_factory() as stale_session:
        stale_file_item = await repository.get(stale_session, created["id"])
        assert stale_file_item is not None
        await stale_session.commit()

        async with test_context.session_factory() as delete_session:
            live_file_item = await repository.get(delete_session, created["id"])
            assert live_file_item is not None
            assert await repository.delete_existing(delete_session, live_file_item) is True
            await delete_session.commit()

        assert await repository.delete_existing(stale_session, stale_file_item) is False


@pytest.mark.asyncio
async def test_delete_file_does_not_publish_duplicate_event_when_row_disappears(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    response = await client.post(
        "/files",
        data={"title": "Delete race"},
        files={"file": ("race.txt", b"race", "text/plain")},
    )
    created = response.json()
    file_service = test_context.container.file_service
    original_repository = file_service.repository
    published_event_types: list[str] = []

    async def record_dashboard_change(event):
        published_event_types.append(event.event_type)

    class AlreadyDeletedRepository(FileRepository):
        async def get(self, session, file_id):
            return await original_repository.get(session, file_id)

        async def delete_existing(self, session, file_item):
            return False

    file_service.repository = AlreadyDeletedRepository()
    file_service.notify_dashboard_change = record_dashboard_change

    try:
        with pytest.raises(HTTPException) as exc_info:
            await file_service.delete_file(created["id"])

        assert exc_info.value.status_code == 404
        assert "file.deleted" not in published_event_types
        assert await test_context.storage.exists(f"{created['id']}.txt")
    finally:
        file_service.repository = original_repository
        file_service.notify_dashboard_change = test_context.event_bus.publish


@pytest.mark.asyncio
async def test_rejects_blank_title(client: AsyncClient) -> None:
    response = await client.post(
        "/files",
        data={"title": "   "},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recover_stuck_file_requeues_it(client: AsyncClient, test_context: AppContext) -> None:
    response = await client.post(
        "/files",
        data={"title": "Watchdog retry"},
        files={"file": ("retry.txt", b"watchdog", "text/plain")},
    )
    created = response.json()

    await mark_file_as_stuck(
        app_context=test_context,
        file_id=created["id"],
        attempts=1,
    )

    recovered_ids = await test_context.processing_service.recover_stuck_files()

    assert recovered_ids == [created["id"]]

    async with test_context.session_factory() as session:
        file_item = await session.get(StoredFile, UUID(created["id"]))
        assert file_item is not None
        assert file_item.processing_status == "uploaded"
        assert file_item.processing_started_at is None
        assert file_item.processing_attempts == 1

    await test_context.processing_service.process_file(created["id"])

    file_response = await client.get(f"/files/{created['id']}")
    assert file_response.status_code == 200
    assert file_response.json()["processing_status"] == "processed"


@pytest.mark.asyncio
async def test_recover_processing_file_with_missing_started_at(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    response = await client.post(
        "/files",
        data={"title": "Watchdog null started"},
        files={"file": ("null-started.txt", b"legacy processing row", "text/plain")},
    )
    assert response.status_code == 201
    created = response.json()
    test_context.queued_ids.clear()

    async with test_context.session_factory() as session:
        file_item = await session.get(StoredFile, UUID(created["id"]))
        assert file_item is not None
        file_item.processing_status = ProcessingStatus.PROCESSING
        file_item.processing_started_at = None
        file_item.processing_attempts = 1
        await session.commit()

    recovered_ids = await test_context.processing_service.recover_stuck_files()

    assert recovered_ids == [created["id"]]

    async with test_context.session_factory() as session:
        file_item = await session.get(StoredFile, UUID(created["id"]))
        assert file_item is not None
        assert file_item.processing_status == "uploaded"
        assert file_item.processing_started_at is None
        assert file_item.processing_attempts == 1


@pytest.mark.asyncio
async def test_recover_stale_uploaded_file_after_enqueue_failure(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    test_context.processing_queue.fail_enqueue = True
    response = await client.post(
        "/files",
        data={"title": "Queue recovery"},
        files={"file": ("queue.txt", b"queue failure", "text/plain")},
    )
    assert response.status_code == 201
    created = response.json()
    assert test_context.queued_ids == []

    await mark_file_as_stale_uploaded(
        app_context=test_context,
        file_id=created["id"],
    )

    recovered_ids = await test_context.processing_service.recover_stuck_files()

    assert recovered_ids == [created["id"]]


@pytest.mark.asyncio
async def test_processing_claim_scope_allows_uploaded_and_stale_processing_only(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    response = await client.post(
        "/files",
        data={"title": "Claim scope"},
        files={"file": ("claim.txt", b"claim payload", "text/plain")},
    )
    assert response.status_code == 201
    created = response.json()
    repository = test_context.container.file_repository
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(seconds=1)

    async with test_context.session_factory() as session:
        first_claim = await repository.claim_for_processing(
            session,
            file_id=created["id"],
            started_at=now,
            stale_before=stale_before,
        )
        assert first_claim is not None
        assert first_claim.processing_status == ProcessingStatus.PROCESSING
        assert first_claim.processing_attempts == 1
        await session.commit()

    async with test_context.session_factory() as session:
        fresh_claim = await repository.claim_for_processing(
            session,
            file_id=created["id"],
            started_at=now + timedelta(seconds=1),
            stale_before=stale_before,
        )
        assert fresh_claim is None

    async with test_context.session_factory() as session:
        file_item = await session.get(StoredFile, UUID(created["id"]))
        assert file_item is not None
        file_item.processing_started_at = stale_before - timedelta(seconds=1)
        await session.commit()

    async with test_context.session_factory() as session:
        stale_claim = await repository.claim_for_processing(
            session,
            file_id=created["id"],
            started_at=now + timedelta(seconds=2),
            stale_before=stale_before,
        )
        assert stale_claim is not None
        assert stale_claim.processing_status == ProcessingStatus.PROCESSING
        assert stale_claim.processing_attempts == 2


@pytest.mark.asyncio
async def test_recover_stuck_file_marks_it_failed_after_max_attempts(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    response = await client.post(
        "/files",
        data={"title": "Watchdog fail"},
        files={"file": ("failed.txt", b"still here", "text/plain")},
    )
    created = response.json()

    await mark_file_as_stuck(
        app_context=test_context,
        file_id=created["id"],
        attempts=test_context.settings.max_processing_attempts,
    )

    recovered_ids = await test_context.processing_service.recover_stuck_files()

    assert recovered_ids == []

    file_response = await client.get(f"/files/{created['id']}")
    assert file_response.status_code == 200
    file_payload = file_response.json()
    assert file_payload["processing_status"] == "failed"
    assert file_payload["scan_status"] == "failed"
    assert file_payload["requires_attention"] is True

    alerts_response = await client.get("/alerts")
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()
    assert len(alerts) == 1
    assert alerts[0]["level"] == "critical"


@pytest.mark.asyncio
async def test_duplicate_processing_delivery_is_idempotent(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    response = await client.post(
        "/files",
        data={"title": "Duplicate delivery"},
        files={"file": ("duplicate.txt", b"same payload", "text/plain")},
    )
    assert response.status_code == 201
    created = response.json()

    await asyncio.gather(
        test_context.processing_service.process_file(created["id"]),
        test_context.processing_service.process_file(created["id"]),
    )

    file_response = await client.get(f"/files/{created['id']}")
    assert file_response.status_code == 200
    file_payload = file_response.json()
    assert file_payload["processing_status"] == "processed"

    async with test_context.session_factory() as session:
        file_item = await session.get(StoredFile, UUID(created["id"]))
        assert file_item is not None
        assert file_item.processing_attempts == 1

    alerts_response = await client.get("/alerts")
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()
    assert len(alerts) == 1
    assert alerts[0]["file_id"] == created["id"]


@pytest.mark.asyncio
async def test_dashboard_events_snapshot_respects_pagination_params(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    for index in range(3):
        response = await client.post(
            "/files",
            data={"title": f"Events page {index}"},
            files={"file": (f"events-page-{index}.txt", f"payload {index}".encode(), "text/plain")},
        )
        assert response.status_code == 201
        await test_context.processing_service.process_file(response.json()["id"])

    expected_files_response = await client.get("/files", params={"offset": 1, "limit": 1})
    expected_alerts_response = await client.get("/alerts", params={"offset": 1, "limit": 1})
    assert expected_files_response.status_code == 200
    assert expected_alerts_response.status_code == 200

    stream = await _open_asgi_stream(test_context.app, "/events?offset=1&limit=1")
    try:
        response_start = await stream.read_message("http.response.start")
        assert response_start["status"] == 200

        snapshot_event_name, snapshot_payload = await stream.read_sse_event()
        assert snapshot_event_name == "dashboard-snapshot"
        snapshot = json.loads(snapshot_payload)
        assert snapshot["files"] == expected_files_response.json()
        assert snapshot["alerts"] == expected_alerts_response.json()
    finally:
        await stream.close()


@pytest.mark.asyncio
async def test_dashboard_events_stream_emits_snapshot_and_patch(
    client: AsyncClient,
    test_context: AppContext,
) -> None:
    stream = await _open_asgi_stream(test_context.app, "/events")
    try:
        response_start = await stream.read_message("http.response.start")
        assert response_start["status"] == 200
        headers = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in response_start["headers"]
        }
        assert headers["content-type"].startswith("text/event-stream")

        snapshot_event_name, snapshot_payload = await stream.read_sse_event()
        assert snapshot_event_name == "dashboard-snapshot"
        snapshot = json.loads(snapshot_payload)
        assert snapshot["kind"] == "snapshot"
        assert snapshot["files"] == []
        assert snapshot["alerts"] == []

        create_response = await client.post(
            "/files",
            data={"title": "Realtime stream"},
            files={"file": ("stream.txt", b"stream payload", "text/plain")},
        )
        assert create_response.status_code == 201
        created = create_response.json()

        patch_event_name, patch_payload = await stream.read_sse_event()
        assert patch_event_name == "dashboard-update"
        patch = json.loads(patch_payload)
        assert patch["kind"] == "patch"
        assert patch["event_type"] == "file.created"
        assert patch["event_id"]
        assert patch["file"]["id"] == created["id"]
        assert patch["alert"] is None
        assert patch["removed_file_id"] is None
        assert patch["removed_alerts_for_file_id"] is None
    finally:
        await stream.close()


class AsgiStream:
    def __init__(self, task, receive_queue, send_queue):
        self.task = task
        self.receive_queue = receive_queue
        self.send_queue = send_queue

    async def read_message(self, message_type: str) -> dict[str, object]:
        while True:
            message = await asyncio.wait_for(self.send_queue.get(), timeout=2)
            if message["type"] == message_type:
                return message

    async def read_sse_event(self) -> tuple[str, str]:
        while True:
            message = await self.read_message("http.response.body")
            chunk = message.get("body", b"")
            if not chunk:
                continue
            event_name, payload = _parse_sse_chunk(chunk.decode("utf-8"))
            if payload:
                return event_name, payload

    async def close(self) -> None:
        await self.receive_queue.put({"type": "http.disconnect"})
        try:
            await asyncio.wait_for(self.task, timeout=2)
        except (asyncio.CancelledError, TimeoutError):
            self.task.cancel()


async def _open_asgi_stream(app, path: str) -> AsgiStream:
    parsed_path = urlsplit(path)
    receive_queue = asyncio.Queue()
    send_queue = asyncio.Queue()
    await receive_queue.put({"type": "http.request", "body": b"", "more_body": False})

    async def receive() -> dict[str, object]:
        return await receive_queue.get()

    async def send(message: dict[str, object]) -> None:
        await send_queue.put(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": parsed_path.path,
        "raw_path": parsed_path.path.encode("ascii"),
        "query_string": parsed_path.query.encode("ascii"),
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    task = asyncio.create_task(app(scope, receive, send))
    return AsgiStream(task, receive_queue, send_queue)


def _parse_sse_chunk(chunk: str) -> tuple[str, str]:
    event_name = "message"
    data_lines: list[str] = []

    for line in chunk.splitlines():
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
            continue

        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())

    return event_name, "\n".join(data_lines)
