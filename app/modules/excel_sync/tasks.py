from app.config import get_settings
from app.infrastructure.database.session import task_session
from app.modules.excel_sync.service import ExcelSyncService
from app.modules.properties.workflows import dispatch_status_side_effects
from app.shared.logging import get_logger
from app.worker import celery_app, run_async

log = get_logger(__name__)


@celery_app.task(name="excel_sync.sync_file")
def sync_file() -> dict | None:
    """Beat: periodic two-way sync with the shared Excel file."""

    async def _run() -> dict | None:
        async with task_session() as session:
            report = await ExcelSyncService(session).sync_file(get_settings().excel_path)
            await session.commit()
        if report is None:
            return None
        for result in report.status_changes:
            dispatch_status_side_effects(result)
        return report.as_dict()

    return run_async(_run())
