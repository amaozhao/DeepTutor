from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import time

import pytest

from deeptutor.auth.passwords import hash_password
from deeptutor.auth.store import AuthStore, UserAlreadyExists


def test_auth_store_creates_users_with_normalized_unique_email(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.db")

    user = store.create_user(
        email=" Alice@Example.COM ",
        password_hash=hash_password("secret-password"),
        display_name="Alice",
    )

    assert user.id.startswith("user_")
    assert user.email == "alice@example.com"
    assert user.display_name == "Alice"
    assert user.role == "admin"
    assert user.disabled_at is None
    assert store.get_user_by_email("alice@example.com") == user

    with pytest.raises(UserAlreadyExists):
        store.create_user(
            email="alice@example.com",
            password_hash=hash_password("another-secret"),
        )


def test_auth_store_marks_first_user_admin_and_later_users_standard(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.db")

    first = store.create_user(
        email="first@example.com",
        password_hash=hash_password("secret-password"),
    )
    second = store.create_user(
        email="second@example.com",
        password_hash=hash_password("secret-password"),
    )

    assert first.role == "admin"
    assert second.role == "user"
    assert store.is_user_admin(first.id) is True
    assert store.is_user_admin(second.id) is False


def test_auth_store_migrates_existing_db_and_promotes_earliest_user(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.db"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                disabled_at REAL
            );
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                revoked_at REAL,
                user_agent TEXT DEFAULT '',
                ip_address TEXT DEFAULT ''
            );
            """
        )
        conn.execute(
            """
            INSERT INTO users (id, email, password_hash, display_name, created_at, updated_at, disabled_at)
            VALUES ('user_old_2', 'later@example.com', 'hash', '', 20, 20, NULL)
            """
        )
        conn.execute(
            """
            INSERT INTO users (id, email, password_hash, display_name, created_at, updated_at, disabled_at)
            VALUES ('user_old_1', 'first@example.com', 'hash', '', 10, 10, NULL)
            """
        )
        conn.commit()

    store = AuthStore(db_path)

    assert store.get_user("user_old_1").role == "admin"
    assert store.get_user("user_old_2").role == "user"


def test_session_token_resolves_active_user_and_can_be_revoked(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.db")
    user = store.create_user(
        email="alice@example.com",
        password_hash=hash_password("secret-password"),
    )

    session = store.create_session(user.id, user_agent="pytest", ip_address="127.0.0.1")

    assert session.token
    assert session.token_hash != session.token
    assert store.get_user_by_session_token(session.token) == user

    assert store.revoke_session(session.token) is True
    assert store.get_user_by_session_token(session.token) is None


def test_expired_or_disabled_sessions_do_not_authenticate(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.db")
    user = store.create_user(
        email="alice@example.com",
        password_hash=hash_password("secret-password"),
    )

    expired = store.create_session(user.id, expires_at=time.time() - 1)
    assert store.get_user_by_session_token(expired.token) is None

    active = store.create_session(user.id, expires_at=time.time() + 3600)
    assert store.get_user_by_session_token(active.token) == user

    assert store.disable_user(user.id) is True
    assert store.get_user_by_session_token(active.token) is None
