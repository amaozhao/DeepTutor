from __future__ import annotations

import time

import pytest

from deeptutor.auth.dependencies import SESSION_COOKIE
from deeptutor.auth.models import AuthUser


@pytest.fixture(autouse=True)
def authenticated_api_testclient(monkeypatch: pytest.MonkeyPatch):
    """Give legacy API router tests a default authenticated user.

    Production routers now require cookies for private resources. Most tests in
    this package are pre-auth unit tests that build a tiny app around one
    router, so attaching a deterministic cookie keeps them focused on the
    router behavior under test.
    """
    token = "api-test-session"
    user = AuthUser(
        id="api_test_user",
        email="api-test@example.com",
        password_hash="hash",
        display_name="API Test User",
        created_at=time.time(),
        updated_at=time.time(),
        role="admin",
    )

    class FakeAuthStore:
        def get_user_by_session_token(self, value: str):
            return user if value == token else None

    monkeypatch.setattr(
        "deeptutor.auth.dependencies.get_auth_store",
        lambda: FakeAuthStore(),
    )

    from starlette.testclient import TestClient

    original_init = TestClient.__init__

    def init_with_auth_cookie(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.cookies.set(SESSION_COOKIE, token)

    monkeypatch.setattr(TestClient, "__init__", init_with_auth_cookie)
    yield
