import hmac
from enum import StrEnum

from app.shared.exceptions import PermissionDeniedError


class UserRole(StrEnum):
    OWNER = "owner"
    AGENT = "agent"
    CLIENT = "client"


STAFF_ROLES: frozenset[UserRole] = frozenset({UserRole.OWNER, UserRole.AGENT})


def secure_compare(a: str | None, b: str | None) -> bool:
    """Constant-time string comparison (API keys, webhook secrets)."""
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode(), b.encode())


def is_staff(role: UserRole) -> bool:
    return role in STAFF_ROLES


def ensure_role(role: UserRole, *allowed: UserRole) -> None:
    if role not in allowed:
        raise PermissionDeniedError(f"Role {role} is not allowed", role=role)
