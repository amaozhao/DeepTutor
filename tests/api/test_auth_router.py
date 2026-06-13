from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
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


async def _request_user_payload() -> dict[str, str]:
    user = get_current_user()
    return {"user_id": user.id, "username": user.username, "role": user.role}


@pytest.mark.asyncio
async def test_require_auth_installs_request_local_user(monkeypatch: pytest.MonkeyPatch) -> None:
    previous = _current_user("admin-before", "admin")
    token = set_current_user(previous)
    try:
        monkeypatch.setattr(auth, "AUTH_ENABLED", True)
        monkeypatch.setattr(
            auth,
            "decode_token",
            lambda _token: TokenPayload(username="zhaoruoshui", role="user", user_id="child-1"),
        )

        payload = await auth.require_auth(authorization="Bearer token", dt_token=None)

        assert payload is not None
        assert payload.username == "zhaoruoshui"
        assert get_current_user().id == "child-1"
        assert get_current_user().role == "user"

        set_current_user(previous)
        assert get_current_user().id == "admin-before"
        assert get_current_user().role == "admin"
    finally:
        reset_current_user(token)


def test_router_dependency_context_is_visible_to_async_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(
        auth,
        "decode_token",
        lambda _token: TokenPayload(username="zhaoruoshui", role="user", user_id="child-1"),
    )
    app = FastAPI()
    app.add_api_route(
        "/current-user",
        _request_user_payload,
        dependencies=[Depends(auth.require_auth)],
    )

    response = TestClient(app).get(
        "/current-user",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "user_id": "child-1",
        "username": "zhaoruoshui",
        "role": "user",
    }
