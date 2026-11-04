from collections.abc import Iterable, Sequence
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def normalize_header(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def read_rows(source: Path | BinaryIO, sheet: str | None = None) -> list[dict[str, Any]]:
    """Read the first (or named) sheet into a list of dicts keyed by normalized header."""
    wb = load_workbook(source, read_only=True, data_only=True)
    try:
        ws = wb[sheet] if sheet else wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            return []
        keys = [normalize_header(h) for h in header]
        result: list[dict[str, Any]] = []
        for raw in rows:
            if raw is None or all(cell in (None, "") for cell in raw):
                continue
            result.append({k: v for k, v in zip(keys, raw, strict=False) if k})
        return result
    finally:
        wb.close()


def build_workbook(headers: Sequence[str], rows: Iterable[Sequence[Any]], sheet: str = "properties") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(list(headers))
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="305496")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
    for row in rows:
        ws.append(list(row))
    for idx, header in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = max(12, min(40, len(header) + 4))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def write_atomic(path: Path, content: bytes) -> None:
    """Write via temp file + rename so readers never see a half-written workbook."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(path)


def file_mtime(path: Path) -> float | None:
    """Return file mtime if it exists, else None."""
    return path.stat().st_mtime if path.exists() else None
