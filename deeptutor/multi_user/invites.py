"""File-backed registration invitations for controlled beta signups."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import secrets
from typing import Any

from . import paths
from .identity import auth_store_write_lock


def _invite_file():
    return paths.SYSTEM_ROOT / "auth" / "invites.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read() -> dict[str, dict[str, Any]]:
    try:
        target = _invite_file()
        if not target.exists():
            return {}
        loaded = json.loads(target.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _write(invites: dict[str, dict[str, Any]]) -> None:
    paths.ensure_system_dirs()
    target = _invite_file()
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(invites, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)


def create_invite(*, email: str = "", created_by: str = "") -> dict[str, Any]:
    """Create a one-use invite code, optionally bound to a lower-cased email."""
    with auth_store_write_lock():
        invites = _read()
        code = secrets.token_urlsafe(18)
        while code in invites:
            code = secrets.token_urlsafe(18)
        record = {
            "code": code,
            "email": email.strip().lower(),
            "created_by": created_by,
            "created_at": _utc_now(),
            "used_by": "",
            "used_at": "",
        }
        invites[code] = record
        _write(invites)
    return record


def list_invites() -> list[dict[str, Any]]:
    invites = _read().values()
    return sorted(invites, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def delete_invite(code: str) -> bool:
    with auth_store_write_lock():
        invites = _read()
        if code not in invites:
            return False
        invites.pop(code, None)
        _write(invites)
    return True


def consume_invite(code: str, *, email: str) -> dict[str, Any] | None:
    """Mark an invite as used when it exists, is unused, and matches the email."""
    normalized_code = code.strip()
    normalized_email = email.strip().lower()
    if not normalized_code or not normalized_email:
        return None
    with auth_store_write_lock():
        invites = _read()
        record = invites.get(normalized_code)
        if not record or record.get("used_at"):
            return None
        bound_email = str(record.get("email") or "").strip().lower()
        if bound_email and bound_email != normalized_email:
            return None
        record["used_by"] = normalized_email
        record["used_at"] = _utc_now()
        invites[normalized_code] = record
        _write(invites)
    return record
