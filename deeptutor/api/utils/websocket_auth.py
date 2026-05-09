"""WebSocket auth helpers backed by the upstream multi-user JWT context."""

from __future__ import annotations

from contextvars import Token

from fastapi import WebSocket

from deeptutor.multi_user.context import reset_current_user, set_current_user
from deeptutor.multi_user.models import CurrentUser
from deeptutor.multi_user.paths import local_admin_user
from deeptutor.services.auth import AUTH_ENABLED, decode_token


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1].strip()
        return token or None
    return None


def _websocket_token(ws: WebSocket) -> str | None:
    return (
        ws.query_params.get("token")
        or ws.cookies.get("dt_token")
        or _bearer_token(ws.headers.get("authorization"))
    )


async def set_websocket_current_user(ws: WebSocket) -> Token[CurrentUser | None] | None:
    """Set the current user for a WebSocket connection.

    Returns a context token that the caller must reset after the handler exits.
    If auth is enabled and no valid token is present, the socket is closed and
    ``None`` is returned.
    """
    if not AUTH_ENABLED:
        return set_current_user(local_admin_user())

    token = _websocket_token(ws)
    payload = decode_token(token) if token else None
    if not payload:
        await ws.close(code=4001)
        return None

    from deeptutor.multi_user.context import user_from_token_payload

    return set_current_user(user_from_token_payload(payload))


def reset_websocket_current_user(token: Token[CurrentUser | None]) -> None:
    reset_current_user(token)
