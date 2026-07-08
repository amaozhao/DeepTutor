"""Request-local current user context."""

from __future__ import annotations

from typing import Any

from .current import get_current_user_or_none, reset_current_user, set_current_user
from .models import CurrentUser
from .paths import local_admin_user, scope_for_user

__all__ = [
    "get_current_user",
    "get_current_user_or_none",
    "reset_current_user",
    "set_current_user",
    "user_from_token_payload",
]


def get_current_user() -> CurrentUser:
    return get_current_user_or_none() or local_admin_user()


def user_from_token_payload(payload: Any | None) -> CurrentUser:
    if payload is None:
        return local_admin_user()
    user_id = str(getattr(payload, "user_id", "") or "")
    username = str(getattr(payload, "username", "") or "local")
    role = str(getattr(payload, "role", "user") or "user")
    if role not in {"admin", "user"}:
        role = "user"
    if not user_id:
        user_id = "local-admin" if role == "admin" and username == "local" else username
    return CurrentUser(
        id=user_id,
        username=username,
        role=role,  # type: ignore[arg-type]
        scope=scope_for_user(user_id, is_admin=role == "admin"),
    )
