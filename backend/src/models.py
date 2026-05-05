from datetime import datetime
from enum import Enum as PythonEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


JSON_METADATA_TYPE = JSON().with_variant(JSONB(), "postgresql")


class ProcessingStatus(str, PythonEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class ScanStatus(str, PythonEnum):
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    FAILED = "failed"


def _enum_values(enum_class: type[PythonEnum]) -> list[str]:
    return [member.value for member in enum_class]


PROCESSING_STATUS_TYPE = SQLEnum(
    ProcessingStatus,
    values_callable=_enum_values,
    name="processing_status_enum",
    validate_strings=True,
    create_constraint=True,
)
SCAN_STATUS_TYPE = SQLEnum(
    ScanStatus,
    values_callable=_enum_values,
    name="scan_status_enum",
    validate_strings=True,
    create_constraint=True,
)


class Base(DeclarativeBase):
    pass


class StoredFile(Base):
    __tablename__ = "files"
    __table_args__ = (
        Index("ix_files_created_at", "created_at"),
        Index("ix_files_processing_watchdog", "processing_status", "processing_started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        PROCESSING_STATUS_TYPE,
        nullable=False,
        default=ProcessingStatus.UPLOADED,
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scan_status: Mapped[ScanStatus | None] = mapped_column(SCAN_STATUS_TYPE, nullable=True)
    scan_details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON_METADATA_TYPE, nullable=True)
    requires_attention: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_created_at", "created_at"),
        Index("ix_alerts_file_id", "file_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
