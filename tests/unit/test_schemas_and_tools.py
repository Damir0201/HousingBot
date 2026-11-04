from decimal import Decimal

from app.modules.ai_assistant.tools import default_registry, inline_schema
from app.modules.properties.schemas import PropertySearchCriteria


def test_search_criteria_swaps_inverted_ranges() -> None:
    c = PropertySearchCriteria(
        budget_min=Decimal("1500"),
        budget_max=Decimal("800"),
        rooms_min=4,
        rooms_max=2,
    )
    assert c.budget_min == Decimal("800")
    assert c.budget_max == Decimal("1500")
    assert c.rooms_min == 2
    assert c.rooms_max == 4


def test_tool_definitions_have_inlined_json_schemas() -> None:
    registry = default_registry()
    names = [d.name for d in registry.definitions]
    assert names == [
        "search_properties",
        "get_property_details",
        "save_client_preferences",
        "search_faq",
        "handoff_to_operator",
    ]
    schema = inline_schema(PropertySearchCriteria)
    assert "$defs" not in schema
    assert "$ref" not in str(schema)
