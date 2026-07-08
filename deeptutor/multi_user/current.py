"""Low-level current-user ContextVar."""

from __future__ import annotations

from contextvars import ContextVar, Token

from .models import CurrentUser

_current_user: ContextVar[CurrentUser | None] = ContextVar("deeptutor_current_user", default=None)


def set_current_user(user: CurrentUser) -> Token[CurrentUser | None]:
    return _current_user.set(user)


def reset_current_user(token: Token[CurrentUser | None]) -> None:
    _current_user.reset(token)


def get_current_user_or_none() -> CurrentUser | None:
    return _current_user.get()
