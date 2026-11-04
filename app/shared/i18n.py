import json
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"


class Language(StrEnum):
    RU = "ru"
    EN = "en"
    IT = "it"


LANGUAGE_NAMES: dict[Language, str] = {
    Language.RU: "🇷🇺 Русский",
    Language.EN: "🇬🇧 English",
    Language.IT: "🇮🇹 Italiano",
}


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in data.items():
        full_key = f"{prefix}{key}"
        if isinstance(value, dict):
            result.update(_flatten(value, f"{full_key}."))
        else:
            result[full_key] = str(value)
    return result


@cache
def load_catalog(language: Language) -> dict[str, str]:
    path = LOCALES_DIR / f"{language.value}.json"
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


class Translator:
    """Tiny JSON-based translator: `t("booking.confirmed", time="10:00")`.

    Falls back to English, then to the key itself, so a missing translation
    never crashes a handler.
    """

    def __init__(self, language: Language | str | None, default: Language = Language.RU) -> None:
        try:
            self.language = Language(language) if language else default
        except ValueError:
            self.language = default

    def __call__(self, key: str, /, **kwargs: Any) -> str:
        template = load_catalog(self.language).get(key) or load_catalog(Language.EN).get(key) or key
        if not kwargs:
            return template
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template

    t = __call__


def resolve_language(code: str | None, default: Language = Language.RU) -> Language:
    """Map Telegram's `language_code` (e.g. 'it-IT', 'uk') to a supported language."""
    if not code:
        return default
    short = code.split("-")[0].lower()
    try:
        return Language(short)
    except ValueError:
        return Language.RU if short in {"uk", "be", "kk"} else Language.EN
