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
    if _postgres_enabled():
        from .shared_state import load_invites

        return load_invites()
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
    if _postgres_enabled():
        from .shared_state import update_invites

        def mutate(invites: dict[str, dict[str, Any]]) -> dict[str, Any]:
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
            return record

        return update_invites(mutate)
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
    if _postgres_enabled():
        from .shared_state import update_invites

        def mutate(invites: dict[str, dict[str, Any]]) -> bool:
            if code not in invites:
                return False
            invites.pop(code, None)
            return True

        return bool(update_invites(mutate))
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
    if _postgres_enabled():
        from .shared_state import update_invites

        def mutate(invites: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
            record = invites.get(normalized_code)
            if not record or record.get("used_at"):
                return None
            bound_email = str(record.get("email") or "").strip().lower()
            if bound_email and bound_email != normalized_email:
                return None
            record["used_by"] = normalized_email
            record["used_at"] = _utc_now()
            invites[normalized_code] = record
            return record

        return update_invites(mutate)
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


def unconsume_invite(code: str, *, email: str) -> bool:
    """Clear a just-consumed invite when downstream registration fails."""
    normalized_code = code.strip()
    normalized_email = email.strip().lower()
    if not normalized_code or not normalized_email:
        return False
    if _postgres_enabled():
        from .shared_state import update_invites

        def mutate(invites: dict[str, dict[str, Any]]) -> bool:
            record = invites.get(normalized_code)
            if not record or str(record.get("used_by") or "").strip().lower() != normalized_email:
                return False
            record["used_by"] = ""
            record["used_at"] = ""
            invites[normalized_code] = record
            return True

        return bool(update_invites(mutate))
    with auth_store_write_lock():
        invites = _read()
        record = invites.get(normalized_code)
        if not record or str(record.get("used_by") or "").strip().lower() != normalized_email:
            return False
        record["used_by"] = ""
        record["used_at"] = ""
        invites[normalized_code] = record
        _write(invites)
    return True


def _postgres_enabled() -> bool:
    from .shared_state import postgres_enabled

    return postgres_enabled()
