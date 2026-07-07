"""Shared fixtures for the multi_user test suite.

These fixtures isolate each test under ``tmp_path`` so we never read or write
the developer's real ``data/`` or ``multi-user/`` directories. They also
provide a context manager that pushes a ``CurrentUser`` onto the contextvar
for tests that need to call user-scoped code without going through HTTP.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from deeptutor.multi_user.context import reset_current_user, set_current_user
from deeptutor.multi_user.models import CurrentUser, UserScope


@pytest.fixture
def make_user(mu_isolated_root):
    """Build a ``CurrentUser`` rooted under the isolated tmp_path."""

    def _make(uid: str, *, role: str = "user", username: str | None = None) -> CurrentUser:
        from deeptutor.multi_user.paths import admin_scope

        if role == "admin":
            scope = admin_scope()
        else:
            scope = UserScope(
                kind="user",
                user_id=uid,
                root=(mu_isolated_root / "data" / "users" / uid).resolve(),
            )
        return CurrentUser(
            id=uid,
            username=username or uid,
            role=role,
            scope=scope,
        )

    return _make


@pytest.fixture
def as_user(make_user):
    """Context manager that pushes a CurrentUser onto the contextvar.

    Usage:
        with as_user("u_alice", role="user"):
            ...
    """

    @contextmanager
    def _scope(uid: str, *, role: str = "user", username: str | None = None):
        token = set_current_user(make_user(uid, role=role, username=username))
        try:
            yield
        finally:
            reset_current_user(token)

    return _scope


@pytest.fixture
def seed_user(mu_isolated_root):
    """Create a user record on disk and return the resulting record dict."""

    def _seed(username: str, password: str = "password1234", role: str = "user") -> dict:
        from deeptutor.multi_user.identity import save_user
        from deeptutor.services.auth import hash_password

        return save_user(username, hash_password(password), role=role)  # type: ignore[arg-type]

    return _seed
