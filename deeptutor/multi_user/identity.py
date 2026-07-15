"""Canonical identity store for the optional multi-user layer."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import secrets
import threading
from typing import Any
from uuid import uuid4

try:
    import fcntl as fcntl_module
except ImportError:  # pragma: no cover - Windows
    fcntl_module = None

from . import shared_state
from .models import Role
from .paths import PROJECT_ROOT, SYSTEM_ROOT, migrate_legacy_multi_user_tree

logger = logging.getLogger(__name__)

# Serialises writes inside one process; auth_store_write_lock adds best-effort
# local process locking. Postgres shared_state handles multi-replica users.
_USERS_WRITE_LOCK = threading.Lock()

AUTH_DIR = SYSTEM_ROOT / "auth"
USERS_FILE = AUTH_DIR / "users.json"
SECRET_FILE = AUTH_DIR / "auth_secret"
LEGACY_USERS_FILE = PROJECT_ROOT / "data" / "user" / "auth_users.json"
LEGACY_SECRET_FILE = PROJECT_ROOT / "data" / "user" / "auth_secret"


def new_user_id() -> str:
    return f"u_{uuid4().hex}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token_version(value: Any) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def _canonical_record(
    username: str,
    value: Any,
    *,
    default_role: Role = "user",
) -> dict[str, Any] | None:
    if isinstance(value, str):
        return {
            "id": new_user_id(),
            "hash": value,
            "role": default_role,
            "created_at": utc_now(),
            "disabled": False,
            "disabled_reason": "",
            "avatar": "",
            "token_version": 1,
            "terms_accepted": False,
            "terms_accepted_at": "",
            "terms_version": "",
            "privacy_version": "",
        }
    if not isinstance(value, dict):
        return None
    hashed = str(value.get("hash") or value.get("password_hash") or "")
    if not hashed:
        return None
    role = str(value.get("role") or default_role)
    if role not in {"admin", "user"}:
        role = default_role
    return {
        "id": str(value.get("id") or new_user_id()),
        "hash": hashed,
        "role": role,
        "created_at": str(value.get("created_at") or utc_now()),
        "disabled": bool(value.get("disabled", False)),
        "disabled_reason": str(value.get("disabled_reason") or ""),
        "avatar": str(value.get("avatar") or ""),
        "token_version": _token_version(value.get("token_version")),
        "terms_accepted": bool(value.get("terms_accepted", False)),
        "terms_accepted_at": str(value.get("terms_accepted_at") or ""),
        "terms_version": str(value.get("terms_version") or ""),
        "privacy_version": str(value.get("privacy_version") or ""),
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return {}


@contextmanager
def auth_store_write_lock() -> Iterator[None]:
    """Lock local auth writes across worker processes on one host."""
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_path = USERS_FILE.parent / "users.lock"
    with _USERS_WRITE_LOCK:
        with lock_path.open("a+", encoding="utf-8") as handle:
            locked = False
            try:
                if fcntl_module is not None:
                    fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_EX)
                    locked = True
            except OSError as exc:
                logger.warning("Auth store write lock unavailable for %s: %s", lock_path, exc)
            try:
                yield
            finally:
                if locked and fcntl_module is not None:
                    fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_UN)


def _write_users(users: dict[str, dict[str, Any]]) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = USERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(USERS_FILE)


def _migrate_legacy_users() -> dict[str, dict[str, Any]] | None:
    if USERS_FILE.exists() or not LEGACY_USERS_FILE.exists():
        return None
    legacy = _read_json(LEGACY_USERS_FILE)
    users: dict[str, dict[str, Any]] = {}
    for username, value in legacy.items():
        role: Role = "admin" if not users else "user"
        if isinstance(value, dict) and str(value.get("role") or "") in {"admin", "user"}:
            role = str(value.get("role"))  # type: ignore[assignment]
        record = _canonical_record(username, value, default_role=role)
        if record is not None:
            users[str(username)] = record
    if users:
        _write_users(users)
        logger.info("Migrated auth users from %s to %s", LEGACY_USERS_FILE, USERS_FILE)
        return users
    return None


def _migrate_secret() -> None:
    if SECRET_FILE.exists() or not LEGACY_SECRET_FILE.exists():
        return
    try:
        secret = LEGACY_SECRET_FILE.read_text(encoding="utf-8").strip()
        if secret:
            SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
            _write_auth_secret(secret)
            try:
                SECRET_FILE.chmod(0o600)
            except OSError as exc:
                logger.warning(
                    "Failed to restrict auth secret permissions at %s: %s", SECRET_FILE, exc
                )
            logger.info("Migrated auth secret from %s to %s", LEGACY_SECRET_FILE, SECRET_FILE)
    except Exception as exc:
        logger.warning("Failed to migrate legacy auth secret: %s", exc)


def load_users(  # nosec B107 - empty defaults mean "no env fallback supplied".
    env_username: str = "",
    env_password_hash: str = "",
) -> dict[str, dict[str, Any]]:
    """Load canonical users, migrating legacy records and env fallback in memory."""
    if _postgres_enabled():
        return _postgres_load_users(env_username, env_password_hash)
    if not USERS_FILE.exists() and LEGACY_USERS_FILE.exists():
        with auth_store_write_lock():
            return _load_users_unlocked(env_username, env_password_hash)
    users, needs_write_back = _load_users_result(env_username, env_password_hash)
    if needs_write_back:
        with auth_store_write_lock():
            return _load_users_unlocked(env_username, env_password_hash)
    return users


def _load_users_result(
    env_username: str = "",
    env_password_hash: str = "",
) -> tuple[dict[str, dict[str, Any]], bool]:
    migrate_legacy_multi_user_tree()
    users: dict[str, dict[str, Any]] | None = None
    if USERS_FILE.exists():
        users = _read_json(USERS_FILE)
    else:
        users = _migrate_legacy_users()

    if users is None:
        users = {}

    canonical: dict[str, dict[str, Any]] = {}
    changed = False
    for index, (username, value) in enumerate(users.items()):
        role: Role = "admin" if index == 0 else "user"
        if isinstance(value, dict) and str(value.get("role") or "") in {"admin", "user"}:
            role = str(value.get("role"))  # type: ignore[assignment]
        record = _canonical_record(str(username), value, default_role=role)
        if record is None:
            changed = True
            continue
        canonical[str(username)] = record
        changed = changed or record != value

    if canonical:
        return canonical, changed

    if env_username and env_password_hash:
        return {
            env_username: {
                "id": "env-admin",
                "hash": env_password_hash,
                "role": "admin",
                "created_at": "",
                "disabled": False,
                "disabled_reason": "",
                "avatar": "",
                "token_version": 1,
                "terms_accepted": False,
                "terms_accepted_at": "",
                "terms_version": "",
                "privacy_version": "",
            }
        }, False

    return {}, changed


def _load_users_unlocked(
    env_username: str = "",
    env_password_hash: str = "",
) -> dict[str, dict[str, Any]]:
    users, needs_write_back = _load_users_result(env_username, env_password_hash)
    if needs_write_back and USERS_FILE.exists():
        _write_users(users)
    return users


def _postgres_enabled() -> bool:

    return shared_state.postgres_enabled()


def _postgres_load_users(
    env_username: str = "",
    env_password_hash: str = "",
) -> dict[str, dict[str, Any]]:

    users = shared_state.load_users()
    if not users and USERS_FILE.exists():
        users, _needs_write_back = _load_users_result("", "")
        if users:
            shared_state.save_users(users)
    canonical: dict[str, dict[str, Any]] = {}
    changed = False
    for index, (username, value) in enumerate(users.items()):
        role: Role = "admin" if index == 0 else "user"
        if isinstance(value, dict) and str(value.get("role") or "") in {"admin", "user"}:
            role = str(value.get("role"))  # type: ignore[assignment]
        record = _canonical_record(str(username), value, default_role=role)
        if record is None:
            changed = True
            continue
        canonical[str(username)] = record
        changed = changed or record != value
    if canonical:
        if changed:
            shared_state.save_users(canonical)
        return canonical
    if env_username and env_password_hash:
        return {
            env_username: {
                "id": "env-admin",
                "hash": env_password_hash,
                "role": "admin",
                "created_at": "",
                "disabled": False,
                "disabled_reason": "",
                "avatar": "",
                "token_version": 1,
                "terms_accepted": False,
                "terms_accepted_at": "",
                "terms_version": "",
                "privacy_version": "",
            }
        }
    return {}


def _postgres_save_users(users: dict[str, dict[str, Any]]) -> None:

    shared_state.save_users(users)


def save_user(username: str, hashed_password: str, role: Role = "user") -> dict[str, Any]:
    if _postgres_enabled():

        def mutate(users: dict[str, dict[str, Any]]) -> dict[str, Any]:
            effective_role: Role = "admin" if not users else role
            existing = users.get(username) or {}
            record = {
                "id": str(existing.get("id") or new_user_id()),
                "hash": hashed_password,
                "role": effective_role,
                "created_at": str(existing.get("created_at") or utc_now()),
                "disabled": bool(existing.get("disabled", False)),
                "disabled_reason": str(existing.get("disabled_reason") or ""),
                "avatar": str(existing.get("avatar") or ""),
                "token_version": _token_version(existing.get("token_version")),
                "terms_accepted": bool(existing.get("terms_accepted", False)),
                "terms_accepted_at": str(existing.get("terms_accepted_at") or ""),
                "terms_version": str(existing.get("terms_version") or ""),
                "privacy_version": str(existing.get("privacy_version") or ""),
            }
            users[username] = record
            return record

        return shared_state.update_users(mutate)
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Read-modify-write must be atomic so concurrent first-time registrations
    # cannot each see an empty store and each promote themselves to admin.
    with auth_store_write_lock():
        users = _load_users_unlocked()
        effective_role: Role = "admin" if not users else role
        existing = users.get(username) or {}
        record = {
            "id": str(existing.get("id") or new_user_id()),
            "hash": hashed_password,
            "role": effective_role,
            "created_at": str(existing.get("created_at") or utc_now()),
            "disabled": bool(existing.get("disabled", False)),
            "disabled_reason": str(existing.get("disabled_reason") or ""),
            "avatar": str(existing.get("avatar") or ""),
            "token_version": _token_version(existing.get("token_version")),
            "terms_accepted": bool(existing.get("terms_accepted", False)),
            "terms_accepted_at": str(existing.get("terms_accepted_at") or ""),
            "terms_version": str(existing.get("terms_version") or ""),
            "privacy_version": str(existing.get("privacy_version") or ""),
        }
        users[username] = record
        _write_users(users)
    return record


def create_user(username: str, hashed_password: str, role: Role = "user") -> dict[str, Any] | None:
    """Create a user only when the username is still free."""
    if _postgres_enabled():

        def mutate(users: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
            if username in users:
                return None
            effective_role: Role = "admin" if not users else role
            record = {
                "id": new_user_id(),
                "hash": hashed_password,
                "role": effective_role,
                "created_at": utc_now(),
                "disabled": False,
                "disabled_reason": "",
                "avatar": "",
                "token_version": 1,
                "terms_accepted": False,
                "terms_accepted_at": "",
                "terms_version": "",
                "privacy_version": "",
            }
            users[username] = record
            return record

        return shared_state.update_users(mutate)
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with auth_store_write_lock():
        users = _load_users_unlocked()
        if username in users:
            return None
        effective_role: Role = "admin" if not users else role
        record = {
            "id": new_user_id(),
            "hash": hashed_password,
            "role": effective_role,
            "created_at": utc_now(),
            "disabled": False,
            "disabled_reason": "",
            "avatar": "",
            "token_version": 1,
            "terms_accepted": False,
            "terms_accepted_at": "",
            "terms_version": "",
            "privacy_version": "",
        }
        users[username] = record
        _write_users(users)
        return record


def record_terms_acceptance(
    username: str,
    *,
    terms_version: str = "",
    privacy_version: str = "",
) -> bool:
    if _postgres_enabled():

        def mutate(users: dict[str, dict[str, Any]]) -> bool:
            if username not in users:
                return False
            users[username]["terms_accepted"] = True
            users[username]["terms_accepted_at"] = utc_now()
            users[username]["terms_version"] = terms_version
            users[username]["privacy_version"] = privacy_version
            return True

        return bool(shared_state.update_users(mutate))
    if not USERS_FILE.exists():
        return False
    with auth_store_write_lock():
        users = _load_users_unlocked()
        if username not in users:
            return False
        users[username]["terms_accepted"] = True
        users[username]["terms_accepted_at"] = utc_now()
        users[username]["terms_version"] = terms_version
        users[username]["privacy_version"] = privacy_version
        _write_users(users)
    return True


def list_user_info(  # nosec B107 - empty defaults mean "no env fallback supplied".
    env_username: str = "",
    env_password_hash: str = "",
) -> list[dict[str, Any]]:
    return [
        {
            "id": record.get("id", ""),
            "username": username,
            "role": record.get("role", "user"),
            "created_at": record.get("created_at", ""),
            "disabled": bool(record.get("disabled", False)),
            "disabled_reason": str(record.get("disabled_reason") or ""),
            "avatar": str(record.get("avatar") or ""),
        }
        for username, record in load_users(env_username, env_password_hash).items()
    ]


def get_user(username: str) -> dict[str, Any] | None:
    return load_users().get(username)


def get_user_by_id(user_id: str) -> tuple[str, dict[str, Any]] | None:
    for username, record in load_users().items():
        if str(record.get("id") or "") == user_id:
            return username, record
    return None


def delete_user(username: str) -> bool:
    if _postgres_enabled():

        def mutate(users: dict[str, dict[str, Any]]) -> bool:
            if username not in users:
                return False
            users.pop(username, None)
            return True

        return bool(shared_state.update_users(mutate))
    if not USERS_FILE.exists():
        return False
    with auth_store_write_lock():
        users = _load_users_unlocked()
        if username not in users:
            return False
        users.pop(username, None)
        _write_users(users)
    return True


def _bump_token_version(record: dict[str, Any]) -> None:
    record["token_version"] = _token_version(record.get("token_version")) + 1


def update_password(username: str, hashed_password: str) -> bool:
    """Replace a user's password hash and invalidate existing JWTs."""
    if _postgres_enabled():

        def mutate(users: dict[str, dict[str, Any]]) -> bool:
            if username not in users:
                return False
            users[username]["hash"] = hashed_password
            _bump_token_version(users[username])
            return True

        return bool(shared_state.update_users(mutate))
    if not USERS_FILE.exists():
        return False
    with auth_store_write_lock():
        users = _load_users_unlocked()
        if username not in users:
            return False
        users[username]["hash"] = hashed_password
        _bump_token_version(users[username])
        _write_users(users)
    return True


def set_disabled(username: str, disabled: bool, reason: str = "") -> bool:
    """Enable or disable a user and invalidate existing JWTs."""
    if _postgres_enabled():

        def mutate(users: dict[str, dict[str, Any]]) -> bool:
            if username not in users:
                return False
            if bool(users[username].get("disabled", False)) != disabled:
                users[username]["disabled"] = disabled
                _bump_token_version(users[username])
            next_reason = reason.strip()[:500] if disabled else ""
            users[username]["disabled_reason"] = next_reason
            return True

        return bool(shared_state.update_users(mutate))
    if not USERS_FILE.exists():
        return False
    with auth_store_write_lock():
        users = _load_users_unlocked()
        if username not in users:
            return False
        changed = False
        if bool(users[username].get("disabled", False)) != disabled:
            users[username]["disabled"] = disabled
            _bump_token_version(users[username])
            changed = True
        next_reason = reason.strip()[:500] if disabled else ""
        if str(users[username].get("disabled_reason") or "") != next_reason:
            users[username]["disabled_reason"] = next_reason
            changed = True
        if changed:
            _write_users(users)
    return True


def revoke_sessions(username: str) -> bool:
    """Invalidate existing JWTs without changing account fields."""
    if _postgres_enabled():

        def mutate(users: dict[str, dict[str, Any]]) -> bool:
            if username not in users:
                return False
            _bump_token_version(users[username])
            return True

        return bool(shared_state.update_users(mutate))
    if not USERS_FILE.exists():
        return False
    with auth_store_write_lock():
        users = _load_users_unlocked()
        if username not in users:
            return False
        _bump_token_version(users[username])
        _write_users(users)
    return True


def set_avatar(username: str, avatar: str) -> bool:
    """Update the avatar marker for an existing user. Returns True on success."""
    if _postgres_enabled():

        def mutate(users: dict[str, dict[str, Any]]) -> bool:
            if username not in users:
                return False
            users[username]["avatar"] = avatar
            return True

        return bool(shared_state.update_users(mutate))
    if not USERS_FILE.exists():
        return False
    with auth_store_write_lock():
        users = _load_users_unlocked()
        if username not in users:
            return False
        users[username]["avatar"] = avatar
        _write_users(users)
    return True


# ---------------------------------------------------------------------------
# Avatar image files — stored next to the user store, keyed by user id
# ---------------------------------------------------------------------------

# Extensions are derived from server-side content sniffing, never from the
# uploaded filename, so this list is also the full set of files we may serve.
AVATAR_EXTENSIONS = ("png", "jpg", "webp")


def _avatar_dir() -> Path:
    # Resolved lazily so tests that monkeypatch AUTH_DIR keep avatars isolated.
    return AUTH_DIR / "avatars"


def get_avatar_file(user_id: str) -> Path | None:
    """Return the stored avatar image for ``user_id``, or None."""
    for ext in AVATAR_EXTENSIONS:
        candidate = _avatar_dir() / f"{user_id}.{ext}"
        if candidate.is_file():
            return candidate
    return None


def save_avatar_file(user_id: str, data: bytes, ext: str) -> Path:
    """Atomically persist an avatar image, replacing any previous one."""
    if ext not in AVATAR_EXTENSIONS:
        raise ValueError(f"Unsupported avatar extension: {ext!r}")
    directory = _avatar_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{user_id}.{ext}"
    tmp = directory / f"{user_id}.{ext}.tmp"
    tmp.write_bytes(data)
    tmp.replace(target)
    # A re-upload may change the extension; drop stale siblings.
    for other in AVATAR_EXTENSIONS:
        if other != ext:
            (directory / f"{user_id}.{other}").unlink(missing_ok=True)
    return target


def delete_avatar_file(user_id: str) -> None:
    for ext in AVATAR_EXTENSIONS:
        (_avatar_dir() / f"{user_id}.{ext}").unlink(missing_ok=True)


def set_role(username: str, role: Role) -> bool:
    if role not in {"admin", "user"}:
        raise ValueError("role must be 'admin' or 'user'")
    if _postgres_enabled():

        def mutate(users: dict[str, dict[str, Any]]) -> bool:
            if username not in users:
                return False
            users[username]["role"] = role
            _bump_token_version(users[username])
            return True

        return bool(shared_state.update_users(mutate))
    if not USERS_FILE.exists():
        return False
    with auth_store_write_lock():
        users = _load_users_unlocked()
        if username not in users:
            return False
        users[username]["role"] = role
        _bump_token_version(users[username])
        _write_users(users)
    return True


def load_or_create_auth_secret() -> str:
    if _postgres_enabled():
        seed = ""
        try:
            if SECRET_FILE.exists():
                seed = SECRET_FILE.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.warning("Failed to read local auth secret seed at %s: %s", SECRET_FILE, exc)
            seed = ""
        return shared_state.load_or_create_auth_secret(seed)
    migrate_legacy_multi_user_tree()
    try:
        if SECRET_FILE.exists():
            existing = SECRET_FILE.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        with auth_store_write_lock():
            _migrate_secret()
            if SECRET_FILE.exists():
                existing = SECRET_FILE.read_text(encoding="utf-8").strip()
                if existing:
                    return existing
            generated = secrets.token_hex(32)
            _write_auth_secret(generated)
            try:
                SECRET_FILE.chmod(0o600)
            except OSError as exc:
                logger.warning(
                    "Failed to restrict auth secret permissions at %s: %s", SECRET_FILE, exc
                )
            logger.warning(
                "Auth is enabled and no auth_secret file exists. Generated a stable local secret at %s.",
                SECRET_FILE,
            )
            return generated
    except Exception as exc:
        logger.warning("Failed to load/create auth secret at %s: %s", SECRET_FILE, exc)
        return secrets.token_hex(32)


def _write_auth_secret(secret: str) -> None:
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SECRET_FILE.with_suffix(".tmp")
    tmp.write_text(secret, encoding="utf-8")
    tmp.replace(SECRET_FILE)
