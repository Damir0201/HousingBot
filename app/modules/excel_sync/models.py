from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, str_enum


class SyncDirection(StrEnum):
    IMPORT = "import"
    EXPORT = "export"


class SyncRun(Base):
    """Audit log of Excel synchronizations; also stores file mtime to skip unchanged files."""

    __tablename__ = "excel_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    direction: Mapped[SyncDirection] = mapped_column(str_enum(SyncDirection, length=8), index=True)
    source: Mapped[str] = mapped_column(String(255), default="")
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    file_mtime: Mapped[float | None]
    success: Mapped[bool] = mapped_column(default=False)
    stats: Mapped[dict[str, Any]] = mapped_column(default=dict)
