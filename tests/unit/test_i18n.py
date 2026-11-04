import re

from app.bot.main import COMMANDS
from app.modules.bookings.models import BookingStatus
from app.modules.crm.models import LeadStatus, TicketCategory, TicketPriority, TicketStatus
from app.modules.properties.models import PropertyStatus, PropertyType
from app.shared.i18n import Language, Translator, load_catalog, resolve_language

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def test_all_locales_have_identical_keys_and_placeholders() -> None:
    ru = load_catalog(Language.RU)
    en = load_catalog(Language.EN)
    it = load_catalog(Language.IT)

    assert set(ru.keys()) == set(en.keys())
    assert set(ru.keys()) == set(it.keys())

    for key in ru:
        ru_vars = set(PLACEHOLDER_RE.findall(ru[key]))
        en_vars = set(PLACEHOLDER_RE.findall(en[key]))
        it_vars = set(PLACEHOLDER_RE.findall(it[key]))
        assert ru_vars == en_vars == it_vars, f"Placeholder mismatch in key '{key}'"


def test_dynamic_enum_and_command_keys_present() -> None:
    ru = load_catalog(Language.RU)
    for cmd in COMMANDS:
        assert f"commands.{cmd}" in ru
    for day in range(7):
        assert f"days.{day}" in ru
    for prefix, enum_cls in (
        ("property.status", PropertyStatus),
        ("property.type", PropertyType),
        ("booking.status", BookingStatus),
        ("ticket.status", TicketStatus),
        ("ticket.category", TicketCategory),
        ("ticket.priority", TicketPriority),
        ("lead.status", LeadStatus),
    ):
        for item in enum_cls:
            assert f"{prefix}.{item.value}" in ru


def test_translator_formatting_and_fallback() -> None:
    t_it = Translator(Language.IT)
    assert "Italiano" in t_it("start.language_set")
    assert t_it("non.existent.key") == "non.existent.key"


def test_resolve_language() -> None:
    assert resolve_language("it-IT") == Language.IT
    assert resolve_language("en-US") == Language.EN
    assert resolve_language("uk") == Language.RU
    assert resolve_language("fr") == Language.EN
    assert resolve_language(None) == Language.RU
