"""Logical resource grants for non-admin users."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import logging
from pathlib import Path
import threading
from typing import Any

try:
    import fcntl as fcntl_module
except ImportError:  # pragma: no cover - Windows
    fcntl_module = None

from . import shared_state
from .identity import get_user_by_id
from .paths import SYSTEM_ROOT, ensure_system_dirs
from .quota import empty_quota, normalize_quota

GRANTS_DIR = SYSTEM_ROOT / "grants"
_GRANTS_WRITE_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


def empty_grant(user_id: str) -> dict[str, Any]:
    return {
        "version": 2,
        "user_id": user_id,
        "models": {"llm": []},
        "knowledge_bases": [],
        "skills": [],
        # Partners an admin has assigned to this user. Partners stay
        # admin-managed (the /api/v1/partners CRUD router is admin-gated); a
        # grant only lets the user *see and consult* the named partners — same
        # shape as ``skills`` (``[{"partner_id": ...}]``).
        "partners": [],
        # Tool whitelists share the partner-config semantics for built-ins:
        # ``enabled_tools=None`` means "default" (every tool in the pool),
        # ``[]`` means none, a list is an explicit whitelist. MCP tools can
        # proxy host-side capabilities, so non-admin runtime access treats
        # ``mcp_tools=None`` as deny-by-default until an admin grants explicit
        # names. ``exec_enabled`` is a tri-state override on top of the
        # deployment exec policy: ``None`` follows the policy, ``False`` always
        # denies, ``True`` is only honored where the sandbox can actually
        # isolate users (SYSTEM isolation).
        "enabled_tools": None,
        "mcp_tools": None,
        "exec_enabled": None,
        # Per-user LLM usage caps. Zero means unlimited.
        "quota": empty_quota(),
    }


def _normalize_tool_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    return [str(item).strip() for item in value if str(item).strip()]


def grant_path(user_id: str) -> Path:
    ensure_system_dirs()
    return GRANTS_DIR / f"{user_id}.json"


@contextmanager
def _grant_write_lock(user_id: str):
    path = grant_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with _GRANTS_WRITE_LOCK:
        with lock_path.open("a+", encoding="utf-8") as handle:
            locked = False
            try:
                if fcntl_module is not None:
                    fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_EX)
                    locked = True
            except OSError as exc:
                logger.warning("Grant write lock unavailable for %s: %s", lock_path, exc)
            try:
                yield path
            finally:
                if locked and fcntl_module is not None:
                    fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_UN)


def normalize_grant(user_id: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    """Coerce any stored/submitted grant payload into the v2 shape.

    v1 grants normalize losslessly for everything that was ever enforced:
    ``models.embedding`` / ``models.search`` / ``spaces`` had no runtime
    consumers and are dropped; absent v2 fields default to unrestricted.
    """
    base = empty_grant(user_id)
    if not isinstance(payload, dict):
        return base
    base["user_id"] = user_id
    models = payload.get("models") if isinstance(payload.get("models"), dict) else {}
    items = models.get("llm") if isinstance(models, dict) else []
    if not isinstance(items, list):
        items = []
    base["models"]["llm"] = [dict(item) for item in items if isinstance(item, dict)]
    for key in ("knowledge_bases", "skills", "partners"):
        values = payload.get(key) if isinstance(payload.get(key), list) else []
        base[key] = [dict(item) for item in values if isinstance(item, dict)]
    for key in ("enabled_tools", "mcp_tools"):
        base[key] = _normalize_tool_list(payload.get(key))
    exec_enabled = payload.get("exec_enabled")
    base["exec_enabled"] = bool(exec_enabled) if isinstance(exec_enabled, bool) else None
    base["quota"] = normalize_quota(payload.get("quota"))
    return base


def load_grant(user_id: str) -> dict[str, Any]:
    if _postgres_enabled():
        payload = shared_state.load_grant(user_id)
        return normalize_grant(user_id, payload)
    path = grant_path(user_id)
    if not path.exists():
        return empty_grant(user_id)
    try:
        return normalize_grant(user_id, json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        logger.warning("Failed to load grant for user %s from %s: %s", user_id, path, exc)
        return empty_grant(user_id)


def save_grant(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    user_record = get_user_by_id(user_id)
    if user_record is None:
        raise ValueError(f"Unknown user id: {user_id}")
    _username, record = user_record
    if str(record.get("role") or "user") == "admin":
        raise ValueError("Admin users use the main workspace and cannot receive assignments.")
    grant = normalize_grant(user_id, payload)
    validate_grant(grant)
    if _postgres_enabled():
        shared_state.save_grant(user_id, grant)
        return grant
    with _grant_write_lock(user_id) as path:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(grant, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    return grant


def delete_grant(user_id: str) -> None:
    if _postgres_enabled():
        shared_state.delete_grant(user_id)
        return
    with _grant_write_lock(user_id) as path:
        path.unlink(missing_ok=True)


def _postgres_enabled() -> bool:

    return shared_state.postgres_enabled()


def validate_grant(grant: dict[str, Any]) -> None:
    """Reject accidental secret/path material in grants.

    Grants carry logical ids only. Runtime resolution happens server-side.
    """
    forbidden = {"api_key", "secret", "password", "token", "path", "base_url"}

    def walk(value: Any, trail: str = "grant") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key).lower()
                if lowered in forbidden or lowered.endswith("_key"):
                    raise ValueError(f"Grants must not contain secret/path field: {trail}.{key}")
                walk(child, f"{trail}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{trail}[{index}]")

    walk(grant)


def public_grant(user_id: str) -> dict[str, Any]:
    return deepcopy(load_grant(user_id))
