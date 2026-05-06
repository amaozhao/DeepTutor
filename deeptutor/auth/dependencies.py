from __future__ import annotations

from collections.abc import AsyncIterator
import os

from fastapi import HTTPException, Request, WebSocket, status

from deeptutor.auth.context import user_scope
from deeptutor.auth.models import AuthUser
from deeptutor.auth.store import get_auth_store

SESSION_COOKIE = "deeptutor_session"


def auth_cookie_secure() -> bool:
    return os.environ.get("AUTH_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"}


async def require_user_scope(request: Request) -> AsyncIterator[AuthUser]:
    token = request.cookies.get(SESSION_COOKIE, "")
    user = get_auth_store().get_user_by_session_token(token) if token else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    with user_scope(user.id):
        yield user


def authenticate_websocket_user(ws: WebSocket) -> AuthUser | None:
    token = ws.cookies.get(SESSION_COOKIE, "")
    return get_auth_store().get_user_by_session_token(token) if token else None
