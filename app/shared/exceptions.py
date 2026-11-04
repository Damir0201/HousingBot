"""Domain exceptions. They carry an i18n key so the bot can show a localized message
and the API can map them to HTTP status codes."""


class DomikError(Exception):
    """Base class for all expected (business) errors."""

    i18n_key: str = "errors.generic"
    http_status: int = 400

    def __init__(self, message: str | None = None, **context: object) -> None:
        self.context = context
        super().__init__(message or self.__class__.__name__)


class NotFoundError(DomikError):
    i18n_key = "errors.not_found"
    http_status = 404


class PermissionDeniedError(DomikError):
    i18n_key = "errors.permission_denied"
    http_status = 403


class ValidationError(DomikError):
    i18n_key = "errors.validation"
    http_status = 422


class PropertyUnavailableError(DomikError):
    i18n_key = "errors.property_unavailable"
    http_status = 409


class SlotUnavailableError(DomikError):
    i18n_key = "errors.slot_unavailable"
    http_status = 409


class BookingStateError(DomikError):
    i18n_key = "errors.booking_state"
    http_status = 409


class ExtensionConflictError(DomikError):
    i18n_key = "errors.extension_conflict"
    http_status = 409


class ExternalServiceError(DomikError):
    i18n_key = "errors.external_service"
    http_status = 502
