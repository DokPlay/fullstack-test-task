from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from starlette import status

from src.api.dependencies import AlertServiceDep, DashboardEventBusDep, FileServiceDep
from src.api.pagination import DEFAULT_PAGE_LIMIT, PageLimit, PageOffset
from src.schemas import AlertItem, FileItem, FileUpdate
from src.services.events import build_dashboard_snapshot


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/files", response_model=list[FileItem])
    async def list_files_view(
        file_service: FileServiceDep,
        offset: PageOffset = 0,
        limit: PageLimit = DEFAULT_PAGE_LIMIT,
    ):
        return await file_service.list_files(offset=offset, limit=limit)

    @router.get("/alerts", response_model=list[AlertItem])
    async def list_alerts_view(
        alert_service: AlertServiceDep,
        offset: PageOffset = 0,
        limit: PageLimit = DEFAULT_PAGE_LIMIT,
    ):
        return await alert_service.list_alerts(offset=offset, limit=limit)

    @router.get("/events")
    async def stream_dashboard_events(
        request: Request,
        file_service: FileServiceDep,
        alert_service: AlertServiceDep,
        event_bus: DashboardEventBusDep,
        offset: PageOffset = 0,
        limit: PageLimit = DEFAULT_PAGE_LIMIT,
    ):
        async def load_snapshot():
            files, alerts = await asyncio.gather(
                file_service.list_files(offset=offset, limit=limit),
                alert_service.list_alerts(offset=offset, limit=limit),
            )
            return build_dashboard_snapshot(files=files, alerts=alerts)

        async def event_stream():
            async for chunk in event_bus.subscribe(snapshot_factory=load_snapshot):
                yield chunk
                if await request.is_disconnected():
                    break

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/files", response_model=FileItem, status_code=status.HTTP_201_CREATED)
    async def create_file_view(
        file_service: FileServiceDep,
        title: str = Form(...),
        file: UploadFile = File(...),
    ):
        return await file_service.create_file(title=title, upload_file=file)

    @router.get("/files/{file_id}", response_model=FileItem)
    async def get_file_view(file_id: str, file_service: FileServiceDep):
        return await file_service.get_file(file_id)

    @router.patch("/files/{file_id}", response_model=FileItem)
    async def update_file_view(
        file_id: str,
        payload: FileUpdate,
        file_service: FileServiceDep,
    ):
        return await file_service.update_file(file_id=file_id, title=payload.title)

    @router.get("/files/{file_id}/download")
    async def download_file(file_id: str, file_service: FileServiceDep):
        file_item, stored_path = await file_service.get_file_path(file_id)
        return FileResponse(
            path=stored_path,
            media_type=file_item.mime_type,
            filename=file_item.original_name,
        )

    @router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_file_view(file_id: str, file_service: FileServiceDep):
        await file_service.delete_file(file_id)

    return router
