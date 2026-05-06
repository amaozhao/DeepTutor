from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from deeptutor.auth.models import AuthUser
from deeptutor.auth.store import get_auth_store


def _auth_file() -> Path:
    configured = os.environ.get("DEEPTUTOR_AUTH_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".deeptutor" / "auth.json"


def save_cli_session(*, token: str, user: AuthUser) -> Path:
    path = _auth_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "token": token,
        "user_id": user.id,
        "email": user.email,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def load_cli_token() -> str:
    path = _auth_file()
    if not path.exists():
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle) or {}
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("token") or "")


def get_cli_user() -> AuthUser | None:
    token = load_cli_token()
    return get_auth_store().get_user_by_session_token(token) if token else None


def clear_cli_session() -> bool:
    path = _auth_file()
    token = load_cli_token()
    if token:
        get_auth_store().revoke_session(token)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def require_cli_user() -> AuthUser:
    user = get_cli_user()
    if user is None:
        raise RuntimeError("Authentication required. Run `deeptutor auth login` first.")
    return user


__all__ = [
    "clear_cli_session",
    "get_cli_user",
    "load_cli_token",
    "require_cli_user",
    "save_cli_session",
]
