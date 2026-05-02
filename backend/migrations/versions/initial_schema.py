"""initial schema

Revision ID: initial_schema
Revises:
Create Date: 2026-05-03 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PROCESSING_STATUS_ENUM = postgresql.ENUM(
    "uploaded",
    "processing",
    "processed",
    "failed",
    name="processing_status_enum",
    create_type=False,
)
SCAN_STATUS_ENUM = postgresql.ENUM(
    "clean",
    "suspicious",
    "failed",
    name="scan_status_enum",
    create_type=False,
)


def upgrade() -> None:
    """Create the file exchange schema."""
    bind = op.get_bind()
    PROCESSING_STATUS_ENUM.create(bind, checkfirst=True)
    SCAN_STATUS_ENUM.create(bind, checkfirst=True)

    op.create_table(
        "files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("processing_status", PROCESSING_STATUS_ENUM, nullable=False),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_attempts", sa.Integer(), nullable=False),
        sa.Column("scan_status", SCAN_STATUS_ENUM, nullable=True),
        sa.Column("scan_details", sa.String(length=500), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("requires_attention", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_name"),
    )
    op.create_index("ix_files_created_at", "files", ["created_at"], unique=False)
    op.create_index(
        "ix_files_processing_watchdog",
        "files",
        ["processing_status", "processing_started_at"],
        unique=False,
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.String(length=50), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], name="alerts_file_id_fkey", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"], unique=False)
    op.create_index("ix_alerts_file_id", "alerts", ["file_id"], unique=False)


def downgrade() -> None:
    """Drop the file exchange schema."""
    op.drop_index("ix_alerts_file_id", table_name="alerts")
    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_table("alerts")

    op.drop_index("ix_files_processing_watchdog", table_name="files")
    op.drop_index("ix_files_created_at", table_name="files")
    op.drop_table("files")

    bind = op.get_bind()
    SCAN_STATUS_ENUM.drop(bind, checkfirst=True)
    PROCESSING_STATUS_ENUM.drop(bind, checkfirst=True)
