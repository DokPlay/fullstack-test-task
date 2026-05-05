from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models import ProcessingStatus, ScanStatus


MAX_TITLE_LENGTH = 255


class FileItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID
    title: str
    original_name: str
    mime_type: str
    size: int
    processing_status: ProcessingStatus
    scan_status: ScanStatus | None
    scan_details: str | None
    metadata_json: dict | None
    requires_attention: bool
    created_at: datetime
    updated_at: datetime


class FileUpdate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=MAX_TITLE_LENGTH)]

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Title must not be empty")
        return normalized


class AlertItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: UUID
    level: str
    message: str
    created_at: datetime


class DashboardSnapshotEvent(BaseModel):
    kind: Literal["snapshot"] = "snapshot"
    occurred_at: datetime
    files: list[FileItem]
    alerts: list[AlertItem]


class DashboardPatchEvent(BaseModel):
    kind: Literal["patch"] = "patch"
    event_id: str
    event_type: str
    occurred_at: datetime
    file: FileItem | None = None
    alert: AlertItem | None = None
    removed_file_id: str | None = None
    removed_alerts_for_file_id: str | None = None
