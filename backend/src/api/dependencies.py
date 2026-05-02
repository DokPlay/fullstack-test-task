from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from src.core.container import ApplicationContainer
from src.services.alerts import AlertService
from src.services.events import DashboardEventStream
from src.services.files import FileService


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container


def get_file_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> FileService:
    return container.file_service


def get_alert_service(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> AlertService:
    return container.alert_service


def get_event_bus(
    container: Annotated[ApplicationContainer, Depends(get_container)],
) -> DashboardEventStream:
    return container.event_bus


FileServiceDep = Annotated[FileService, Depends(get_file_service)]
AlertServiceDep = Annotated[AlertService, Depends(get_alert_service)]
DashboardEventBusDep = Annotated[DashboardEventStream, Depends(get_event_bus)]
