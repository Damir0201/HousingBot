from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO

import pytest

from app.infrastructure.excel.workbook import build_workbook, read_rows
from app.modules.excel_sync.mapping import (
    COLUMNS,
    RowError,
    diff_fields,
    parse_bool,
    property_to_row,
    row_to_payload,
)
from app.modules.properties.models import Property, PropertyStatus, PropertyType


def test_parse_bool_multilingual() -> None:
    for val in ("да", "yes", "sì", "true", "1", "+", True, 1):
        assert parse_bool(val) is True
    for val in ("нет", "no", "false", "0", "", "-", None, False, 0):
        assert parse_bool(val) is False
    with pytest.raises(RowError):
        parse_bool("maybe")


def test_workbook_roundtrip_and_diff() -> None:
    ts = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    prop = Property(
        id=1,
        code="ROM-101",
        title="Sunny Trastevere Apartment",
        property_type=PropertyType.APARTMENT,
        status=PropertyStatus.AVAILABLE,
        city="Rome",
        district="Trastevere",
        address="Via della Lungaretta 10",
        rooms=2,
        area_m2=Decimal("65.00"),
        floor=3,
        price_month=Decimal("1200.00"),
        deposit=Decimal("2400.00"),
        min_term_months=6,
        max_term_months=24,
        available_from=date(2026, 12, 1),
        furnished=True,
        pets_allowed=False,
        utilities_included=True,
        description="Bright two-room flat",
        features={},
        photos=["https://example.com/1.jpg", "https://example.com/2.jpg"],
        version=1,
        created_at=ts,
        updated_at=ts,
    )

    raw_bytes = build_workbook(COLUMNS, [property_to_row(prop)])
    rows = read_rows(BytesIO(raw_bytes))
    assert len(rows) == 1

    payload, parsed_updated_at = row_to_payload(rows[0])
    assert payload.code == "ROM-101"
    assert payload.price_month == Decimal("1200")
    assert payload.furnished is True
    assert payload.pets_allowed is False
    assert payload.photos == ["https://example.com/1.jpg", "https://example.com/2.jpg"]
    assert parsed_updated_at == ts
    assert diff_fields(prop, payload) == {}

    # Modify price in Excel row and verify diff detection
    rows[0]["price_month"] = 1350
    updated_payload, _ = row_to_payload(rows[0])
    assert diff_fields(prop, updated_payload) == {"price_month": Decimal("1350")}
