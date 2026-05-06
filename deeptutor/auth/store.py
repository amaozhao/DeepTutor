from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import secrets
import sqlite3
import time
import uuid

from deeptutor.auth.models import AuthSession, AuthUser
from deeptutor.services.path_service import get_path_service

SESSION_TTL_SECONDS = 60 * 60 * 24 * 30


class UserAlreadyExists(ValueError):
    pass


@dataclass(frozen=True)
class _SessionToken:
    token: str
    token_hash: str


def _normalize_email(email: str) -> str:
    normalized = str(email or "").strip().lower()
    if "@" not in normalized:
        raise ValueError("valid email is required")
    return normalized


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_session_token() -> _SessionToken:
    token = secrets.token_urlsafe(48)
    return _SessionToken(token=token, token_hash=_token_hash(token))


def _user_from_row(row: sqlite3.Row | None) -> AuthUser | None:
    if row is None:
        return None
    return AuthUser(
        id=row["id"],
        email=row["email"],
        password_hash=row["password_hash"],
        display_name=row["display_name"] or "",
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
        disabled_at=row["disabled_at"],
    )


class AuthStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or get_path_service().get_auth_db()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    disabled_at REAL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked_at REAL,
                    user_agent TEXT DEFAULT '',
                    ip_address TEXT DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_auth_sessions_user
                    ON sessions(user_id, created_at DESC);
                """
            )
            conn.commit()

    def create_user(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str = "",
        user_id: str | None = None,
    ) -> AuthUser:
        now = time.time()
        normalized_email = _normalize_email(email)
        resolved_id = user_id or f"user_{uuid.uuid4().hex}"
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        id, email, password_hash, display_name, created_at, updated_at, disabled_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        resolved_id,
                        normalized_email,
                        password_hash,
                        str(display_name or "").strip(),
                        now,
                        now,
                    ),
                )
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise UserAlreadyExists(normalized_email) from exc
        user = self.get_user(resolved_id)
        if user is None:
            raise RuntimeError("created user could not be loaded")
        return user

    def count_users(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()
        return int(row["total"] if row else 0)

    def get_user(self, user_id: str) -> AuthUser | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _user_from_row(row)

    def get_user_by_email(self, email: str) -> AuthUser | None:
        normalized_email = _normalize_email(email)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?",
                (normalized_email,),
            ).fetchone()
        return _user_from_row(row)

    def create_session(
        self,
        user_id: str,
        *,
        expires_at: float | None = None,
        user_agent: str = "",
        ip_address: str = "",
    ) -> AuthSession:
        now = time.time()
        token = _new_session_token()
        session_id = f"sess_{uuid.uuid4().hex}"
        resolved_expires_at = expires_at if expires_at is not None else now + SESSION_TTL_SECONDS
        with self._connect() as conn:
            user = conn.execute(
                "SELECT id FROM users WHERE id = ? AND disabled_at IS NULL",
                (user_id,),
            ).fetchone()
            if user is None:
                raise ValueError("active user not found")
            conn.execute(
                """
                INSERT INTO sessions (
                    id, user_id, token_hash, created_at, expires_at, revoked_at, user_agent, ip_address
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    token.token_hash,
                    now,
                    resolved_expires_at,
                    user_agent,
                    ip_address,
                ),
            )
            conn.commit()
        return AuthSession(
            id=session_id,
            user_id=user_id,
            token=token.token,
            token_hash=token.token_hash,
            created_at=now,
            expires_at=resolved_expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    def get_user_by_session_token(self, token: str) -> AuthUser | None:
        token_hash = _token_hash(str(token or ""))
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.*
                FROM sessions s
                INNER JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ?
                  AND s.revoked_at IS NULL
                  AND s.expires_at > ?
                  AND u.disabled_at IS NULL
                """,
                (token_hash, now),
            ).fetchone()
        return _user_from_row(row)

    def revoke_session(self, token: str) -> bool:
        token_hash = _token_hash(str(token or ""))
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE sessions
                SET revoked_at = ?
                WHERE token_hash = ? AND revoked_at IS NULL
                """,
                (time.time(), token_hash),
            )
            conn.commit()
        return cur.rowcount > 0

    def disable_user(self, user_id: str) -> bool:
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE users
                SET disabled_at = ?, updated_at = ?
                WHERE id = ? AND disabled_at IS NULL
                """,
                (now, now, user_id),
            )
            conn.commit()
        return cur.rowcount > 0


_store_cache: dict[Path, AuthStore] = {}


def get_auth_store(db_path: Path | None = None) -> AuthStore:
    path = (db_path or get_path_service().get_auth_db()).resolve()
    store = _store_cache.get(path)
    if store is None:
        store = AuthStore(path)
        _store_cache[path] = store
    return store


def reset_auth_store() -> None:
    _store_cache.clear()


__all__ = [
    "AuthStore",
    "SESSION_TTL_SECONDS",
    "UserAlreadyExists",
    "get_auth_store",
    "reset_auth_store",
]
