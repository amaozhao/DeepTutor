"""Tests for the mirrored registration-invite auth router."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(mu_isolated_root, monkeypatch) -> tuple[TestClient, str]:
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.api.security import reset_security_state
    from deeptutor.multi_user.identity import save_user
    from deeptutor.services import auth as auth_service

    reset_security_state()
    admin = save_user("admin", "$2b$12$placeholder", role="admin")
    monkeypatch.setattr(auth_router, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_router, "POCKETBASE_ENABLED", False)
    monkeypatch.setattr(auth_service, "AUTH_SECRET", "test-secret")
    monkeypatch.setattr(
        auth_router,
        "load_auth_settings",
        lambda: {"public_registration_enabled": False, "require_terms_acceptance": True},
    )

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1/auth")
    return TestClient(app), auth_service.create_token("admin", "admin", admin["id"])


def test_admin_invite_router_stays_mounted_under_auth(mu_isolated_root, monkeypatch):
    client, token = _client(mu_isolated_root, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/auth/invites",
        headers=headers,
        json={"email": "Learner@Example.com"},
    )
    assert created.status_code == 201
    assert created.json()["email"] == "learner@example.com"

    listed = client.get("/api/v1/auth/invites", headers=headers)
    assert listed.status_code == 200
    assert [item["code"] for item in listed.json()] == [created.json()["code"]]

    deleted = client.delete(
        f"/api/v1/auth/invites/{created.json()['code']}",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}

    assert client.get("/api/v1/auth/invites", headers=headers).json() == []


def test_invite_router_rejects_non_admin(mu_isolated_root, monkeypatch):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.api.security import reset_security_state
    from deeptutor.multi_user.identity import save_user
    from deeptutor.services import auth as auth_service
    from deeptutor.services.auth import TokenPayload

    reset_security_state()
    user = save_user("learner@example.com", "$2b$12$placeholder", role="user")
    monkeypatch.setattr(auth_router, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_router, "POCKETBASE_ENABLED", False)
    monkeypatch.setattr(auth_service, "AUTH_SECRET", "test-secret")
    monkeypatch.setattr(
        auth_router,
        "decode_token",
        lambda _token: TokenPayload(
            username="learner@example.com", role="user", user_id=user["id"]
        ),
    )

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1/auth")
    client = TestClient(app)
    token = auth_service.create_token("learner@example.com", "user", user["id"])

    response = client.post(
        "/api/v1/auth/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "next@example.com"},
    )

    assert response.status_code == 403
