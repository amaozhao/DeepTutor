from __future__ import annotations

import asyncio
from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest
from starlette.responses import Response

from deeptutor.auth.context import current_user_id
from deeptutor.auth.dependencies import (
    SESSION_COOKIE,
    authenticate_websocket_user,
    require_user_scope,
)
from deeptutor.auth.router import LoginRequest, RegisterRequest, login, logout, me, register
from deeptutor.auth.store import reset_auth_store
from deeptutor.services.path_service import PathService


def _fake_request(*, token: str = ""):
    return SimpleNamespace(
        cookies={SESSION_COOKIE: token} if token else {},
        headers={"user-agent": "pytest"},
        client=SimpleNamespace(host="127.0.0.1"),
    )


def _cookie_value(response: Response) -> str:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie[SESSION_COOKIE].value


async def _resolve_required_user(token: str):
    dep = require_user_scope(_fake_request(token=token))
    user = await anext(dep)
    try:
        assert current_user_id() == user.id
        return user
    finally:
        await dep.aclose()


def test_register_sets_http_only_cookie_and_authenticates_request(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir
    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"
        reset_auth_store()

        response = Response()
        payload = asyncio.run(
            register(
                RegisterRequest(
                    email=" Alice@Example.COM ",
                    password="123456",
                    display_name="Alice",
                ),
                response,
                _fake_request(),
            )
        )

        assert payload["user"]["email"] == "alice@example.com"
        assert "httponly" in response.headers["set-cookie"].lower()
        token = _cookie_value(response)

        user = asyncio.run(_resolve_required_user(token))
        assert user.email == "alice@example.com"
        assert authenticate_websocket_user(_fake_request(token=token)).id == user.id

        me_payload = asyncio.run(me(user))
        assert me_payload["user"]["email"] == "alice@example.com"
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
        reset_auth_store()


def test_login_rejects_wrong_password_and_logout_revokes_cookie(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir
    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"
        reset_auth_store()

        register_response = Response()
        asyncio.run(
            register(
                RegisterRequest(email="alice@example.com", password="secret-password"),
                register_response,
                _fake_request(),
            )
        )

        with pytest.raises(HTTPException) as wrong:
            asyncio.run(
                login(
                    LoginRequest(email="alice@example.com", password="wrong-password"),
                    Response(),
                    _fake_request(),
                )
            )
        assert wrong.value.status_code == 401

        login_response = Response()
        asyncio.run(
            login(
                LoginRequest(email="alice@example.com", password="secret-password"),
                login_response,
                _fake_request(),
            )
        )
        token = _cookie_value(login_response)
        assert asyncio.run(_resolve_required_user(token)).email == "alice@example.com"

        logout_response = Response()
        asyncio.run(logout(_fake_request(token=token), logout_response))
        with pytest.raises(HTTPException) as revoked:
            asyncio.run(_resolve_required_user(token))
        assert revoked.value.status_code == 401
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
        reset_auth_store()
