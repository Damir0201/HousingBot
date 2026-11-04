import zipfile
from io import BytesIO
from typing import Any

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response
from openpyxl.utils.exceptions import InvalidFileException

from app.api.dependencies import ApiKeyAuth, DbSession
from app.modules.excel_sync.service import ExcelSyncService
from app.modules.properties.workflows import dispatch_status_side_effects
from app.shared.exceptions import ValidationError
from app.shared.timeutils import utcnow

router = APIRouter(prefix="/excel", tags=["excel"], dependencies=[ApiKeyAuth])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/export")
async def export_excel(session: DbSession) -> Response:
    content = await ExcelSyncService(session).export_bytes()
    filename = f"domik_properties_{utcnow():%Y%m%d_%H%M}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_excel(
    session: DbSession,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise ValidationError("Only .xlsx files are supported")
    raw = await file.read()
    try:
        report = await ExcelSyncService(session).import_file(BytesIO(raw), file.filename or "api_upload")
    except (InvalidFileException, zipfile.BadZipFile, KeyError, StopIteration) as exc:
        raise ValidationError("Invalid .xlsx workbook") from exc
    await session.commit()
    for result in report.status_changes:
        dispatch_status_side_effects(result)
    return report.as_dict()
