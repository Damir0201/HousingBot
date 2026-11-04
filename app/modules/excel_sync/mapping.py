"""Column mapping between the Excel sheet and `Property`. Pure functions -> unit tested."""

from datetime import UTC, date, datetime, tzinfo
from decimal import Decimal
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.modules.properties.models import Property
from app.modules.properties.schemas import PropertyCreate

# Order defines the column order in exported files.
COLUMNS: list[str] = [
    "code",
    "title",
    "property_type",
    "status",
    "city",
    "district",
    "address",
    "rooms",
    "area_m2",
    "floor",
    "price_month",
    "deposit",
    "min_term_months",
    "max_term_months",
    "available_from",
    "furnished",
    "pets_allowed",
    "utilities_included",
    "description",
    "photos",
    "updated_at",  # informational: used for conflict detection, edits are ignored
]
SYNC_FIELDS = [c for c in COLUMNS if c not in ("code", "status", "updated_at")]

TRUE_VALUES = {"1", "true", "yes", "y", "да", "si", "sì", "x", "+"}
FALSE_VALUES = {"0", "false", "no", "n", "нет", "", "-"}


class RowError(ValueError):
    pass


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, int | float):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise RowError(f"cannot parse boolean from {value!r}")


def parse_datetime(value: Any, default_tz: tzinfo = UTC) -> datetime | None:
    """Parse the `updated_at` marker; naive values are interpreted in `default_tz`."""
    if value in (None, ""):
        return None
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value).strip())
        except ValueError:
            return None
    return value if value.tzinfo else value.replace(tzinfo=default_tz)


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def row_to_payload(row: dict[str, Any]) -> tuple[PropertyCreate, datetime | None]:
    """Validate one sheet row. Returns the payload and the row's `updated_at` marker."""
    data: dict[str, Any] = {k: _clean(row.get(k)) for k in COLUMNS if k != "updated_at"}
    if not data.get("code"):
        raise RowError("empty code")
    data["code"] = str(data["code"]).strip()
    for flag in ("furnished", "pets_allowed", "utilities_included"):
        data[flag] = parse_bool(data.get(flag))
    if isinstance(data.get("available_from"), datetime):
        data["available_from"] = data["available_from"].date()
    photos = data.get("photos")
    data["photos"] = [p.strip() for p in str(photos).split(",") if p.strip()] if photos else []
    for key in ("property_type", "status"):
        if data.get(key):
            data[key] = str(data[key]).strip().lower()
    payload = {k: v for k, v in data.items() if v is not None}
    try:
        return PropertyCreate.model_validate(payload), parse_datetime(row.get("updated_at"))
    except PydanticValidationError as exc:
        fields = ", ".join(".".join(map(str, e["loc"])) for e in exc.errors())
        raise RowError(f"invalid fields: {fields}") from exc


def _cell(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value
    if isinstance(value, list):
        return ", ".join(value)
    if hasattr(value, "value"):  # enums
        return value.value
    return value


def property_to_row(prop: Property) -> list[Any]:
    return [_cell(getattr(prop, column)) for column in COLUMNS]


def diff_fields(prop: Property, payload: PropertyCreate) -> dict[str, Any]:
    """Fields whose Excel value differs from the DB (status handled separately)."""
    changes: dict[str, Any] = {}
    for name in SYNC_FIELDS:
        new = getattr(payload, name)
        if getattr(prop, name) != new:
            changes[name] = new
    return changes
