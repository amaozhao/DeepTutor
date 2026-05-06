from __future__ import annotations

from pathlib import Path
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
    assert user.disabled_at is None
    assert store.get_user_by_email("alice@example.com") == user

    with pytest.raises(UserAlreadyExists):
        store.create_user(
            email="alice@example.com",
            password_hash=hash_password("another-secret"),
        )


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
