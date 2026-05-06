from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_current_user_id: ContextVar[str | None] = ContextVar("deeptutor_current_user_id", default=None)


def current_user_id() -> str | None:
    return _current_user_id.get()


def validate_user_id(user_id: str) -> str:
    normalized = str(user_id or "").strip()
    if not normalized:
        raise ValueError("user_id is required")
    if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise ValueError("user_id contains invalid path characters")
    return normalized


@contextmanager
def user_scope(user_id: str) -> Iterator[None]:
    token = _current_user_id.set(validate_user_id(user_id))
    try:
        yield
    finally:
        _current_user_id.reset(token)
