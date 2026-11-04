from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.excel.workbook import build_workbook, file_mtime, read_rows, write_atomic
from app.modules.excel_sync.mapping import COLUMNS, RowError, diff_fields, property_to_row, row_to_payload
from app.modules.excel_sync.models import SyncDirection, SyncRun
from app.modules.properties.models import Property
from app.modules.properties.repository import PropertyRepository
from app.modules.properties.workflows import StatusChangeResult, change_property_status
from app.shared.logging import get_logger
from app.shared.timeutils import utcnow

log = get_logger(__name__)

# Tolerance for timestamps that round-tripped through Excel
CLOCK_SKEW = timedelta(seconds=1)


@dataclass
class SyncReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    conflicts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status_changes: list[StatusChangeResult] = field(default_factory=list, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "conflicts": self.conflicts,
            "errors": self.errors[:50],
            "status_changes": [
                {"code": r.property.code, "old": r.old_status, "new": r.property.status}
                for r in self.status_changes
                if r.changed
            ],
        }


class ExcelSyncService:
    """Two-way sync. Conflict policy: a row is applied unless the property was modified
    in the CRM after the row's `updated_at` (i.e. after the last export) — then the CRM wins
    and the row is reported as a conflict."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PropertyRepository(session)

    # ------------------------------------------------------------- import
    async def import_rows(self, rows: list[dict[str, Any]]) -> SyncReport:
        report = SyncReport()
        codes = [str(r.get("code")).strip() for r in rows if r.get("code")]
        existing = await self.repo.get_by_codes(codes)
        seen: set[str] = set()

        for index, row in enumerate(rows, start=2):  # row 1 is the header
            try:
                payload, row_updated_at = row_to_payload(row)
            except RowError as exc:
                report.errors.append(f"row {index}: {exc}")
                continue
            if payload.code in seen:
                report.errors.append(f"row {index}: duplicate code {payload.code}")
                continue
            seen.add(payload.code)

            prop = existing.get(payload.code)
            if prop is None:
                self.session.add(Property(**payload.model_dump()))
                report.created += 1
                continue

            changes = diff_fields(prop, payload)
            status_changed = prop.status != payload.status
            if not changes and not status_changed:
                report.unchanged += 1
                continue
            if row_updated_at and prop.updated_at > row_updated_at + CLOCK_SKEW:
                report.conflicts.append(payload.code)
                continue

            for name, value in changes.items():
                setattr(prop, name, value)
            if status_changed:
                report.status_changes.append(
                    await change_property_status(self.session, prop.id, payload.status)
                )
            report.updated += 1

        await self.session.flush()
        return report

    async def import_file(self, source: Path | BinaryIO, source_name: str = "upload") -> SyncReport:
        run = SyncRun(direction=SyncDirection.IMPORT, source=source_name, started_at=utcnow())
        if isinstance(source, Path):
            run.file_mtime = file_mtime(source)
        rows = read_rows(source)
        report = await self.import_rows(rows)
        run.finished_at = utcnow()
        run.success = True
        run.stats = report.as_dict()
        self.session.add(run)
        await self.session.flush()
        log.info(
            "excel.imported", source=source_name, **{k: v for k, v in run.stats.items() if k != "errors"}
        )
        return report

    # ------------------------------------------------------------- export
    async def export_bytes(self) -> bytes:
        props = await self.repo.all()
        return build_workbook(COLUMNS, (property_to_row(p) for p in props))

    async def export_file(self, path: Path) -> None:
        started = utcnow()
        write_atomic(path, await self.export_bytes())
        self.session.add(
            SyncRun(
                direction=SyncDirection.EXPORT,
                source=str(path),
                started_at=started,
                finished_at=utcnow(),
                file_mtime=file_mtime(path),
                success=True,
            )
        )
        await self.session.flush()

    # ------------------------------------------------------------- periodic
    async def sync_file(self, path: Path) -> SyncReport | None:
        """Import if the file changed since our last import/export, then export if the CRM changed."""
        report: SyncReport | None = None
        last_import = await self._last_run(SyncDirection.IMPORT)
        last_export = await self._last_run(SyncDirection.EXPORT)
        known_mtime = max((r.file_mtime or 0 for r in (last_import, last_export) if r is not None), default=0)

        mtime = file_mtime(path)
        if mtime is not None:
            if mtime > known_mtime:
                report = await self.import_file(path, str(path))
            # don't overwrite edits that happened while we were importing
            if file_mtime(path) != mtime:
                return report

        last_export_at = last_export.finished_at if last_export else None
        crm_changed_at = await self.session.scalar(select(func.max(Property.updated_at)))
        if (
            mtime is None
            or report is not None
            or last_export_at is None
            or (crm_changed_at and crm_changed_at > last_export_at)
        ):
            await self.export_file(path)
        return report

    async def _last_run(self, direction: SyncDirection) -> SyncRun | None:
        stmt = (
            select(SyncRun)
            .where(SyncRun.direction == direction, SyncRun.success)
            .order_by(SyncRun.id.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)
