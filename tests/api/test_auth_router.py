from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.api.routers import auth
from deeptutor.multi_user.context import get_current_user, reset_current_user, set_current_user
from deeptutor.multi_user.models import CurrentUser, UserScope
from deeptutor.services.auth import TokenPayload


def _current_user(user_id: str, role: str) -> CurrentUser:
    return CurrentUser(
        id=user_id,
        username=user_id,
        role=role,  # type: ignore[arg-type]
        scope=UserScope(kind="admin" if role == "admin" else "user", user_id=user_id, root=Path(".")),
    )


def test_require_auth_resets_request_local_user(monkeypatch: pytest.MonkeyPatch) -> None:
    previous = _current_user("admin-before", "admin")
    token = set_current_user(previous)
    try:
        monkeypatch.setattr(auth, "AUTH_ENABLED", True)
        monkeypatch.setattr(
            auth,
            "decode_token",
            lambda _token: TokenPayload(username="zhaoruoshui", role="user", user_id="child-1"),
        )

        dependency = auth.require_auth(authorization="Bearer token", dt_token=None)
        payload = next(dependency)

        assert payload is not None
        assert payload.username == "zhaoruoshui"
        assert get_current_user().id == "child-1"
        assert get_current_user().role == "user"

        with pytest.raises(StopIteration):
            next(dependency)

        assert get_current_user().id == "admin-before"
        assert get_current_user().role == "admin"
    finally:
        reset_current_user(token)
