"""Audit log for resource access and admin actions in the multi-user layer."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import threading
from typing import Any

from . import paths
from .context import get_current_user

MAX_AUDIT_QUERY_LIMIT = 500
_AUDIT_WRITE_LOCK = threading.Lock()


def _audit_file():
    # Resolved per call so monkey-patched SYSTEM_ROOT (e.g. in tests) takes
    # effect without a module reload.
    return paths.SYSTEM_ROOT / "audit" / "usage.jsonl"


@contextmanager
def _audit_write_lock():
    paths.ensure_system_dirs()
    target = _audit_file()
    lock_path = target.with_suffix(".lock")
    with _AUDIT_WRITE_LOCK:
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl_module = None
            locked = False
            try:
                import fcntl as fcntl_module

                fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_EX)
                locked = True
            except (ImportError, OSError):
                pass
            try:
                yield target
            finally:
                if locked and fcntl_module is not None:
                    fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_UN)


def _write(payload: dict[str, Any]) -> None:
    try:
        with _audit_write_lock() as target:
            with target.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # Auditing must never break a request.
        return


def _read_events() -> list[dict[str, Any]]:
    try:
        paths.ensure_system_dirs()
        target = _audit_file()
        if not target.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in target.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
        return events
    except Exception:
        return []


def query_audit_events(
    *,
    action: str | None = None,
    actor_id: str | None = None,
    target_user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return newest matching audit events from the file-backed audit log."""
    limit = max(1, min(int(limit or 100), MAX_AUDIT_QUERY_LIMIT))
    events = reversed(_read_events())

    def matches(event: dict[str, Any]) -> bool:
        if action and str(event.get("action") or "") != action:
            return False
        if actor_id and str(event.get("actor_id") or "") != actor_id:
            return False
        if target_user_id and str(event.get("target_user_id") or "") != target_user_id:
            return False
        return True

    return [event for event in events if matches(event)][:limit]


def log_usage(
    resource_type: str,
    resource_id: str,
    action: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Record an ordinary user's access to an admin-curated resource.

    Admin self-access is intentionally not recorded here (admins constantly
    interact with their own workspace; logging every read would dilute the
    signal). Use :func:`log_admin_action` for admin-side write events.
    """
    user = get_current_user()
    if user.is_admin:
        return
    payload: dict[str, Any] = {
        "time": datetime.now(timezone.utc).isoformat(),
        "user_id": user.id,
        "username": user.username,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "action": action,
    }
    if extra:
        payload["extra"] = extra
    _write(payload)


def log_admin_action(
    action: str,
    target_user_id: str | None = None,
    summary: dict[str, Any] | None = None,
) -> None:
    """Record an admin-side write (grant change, user CRUD, etc.).

    The current user (the actor) is captured automatically; ``target_user_id``
    identifies which user the action affects (if any). ``summary`` may carry a
    short, non-secret payload describing what changed.
    """
    user = get_current_user()
    payload: dict[str, Any] = {
        "time": datetime.now(timezone.utc).isoformat(),
        "actor_id": user.id,
        "actor_username": user.username,
        "actor_role": user.role,
        "action": action,
    }
    if target_user_id:
        payload["target_user_id"] = target_user_id
    if summary:
        payload["summary"] = summary
    _write(payload)
