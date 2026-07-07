from __future__ import annotations

import csv
import hashlib
from io import StringIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


def _proof_for_registration(auth_router, email: str) -> str:
    token = auth_router._new_registration_challenge(email)
    nonce = next(
        str(i)
        for i in range(100_000)
        if hashlib.sha256(f"{token}:{i}".encode("utf-8")).hexdigest().startswith(
            "0" * auth_router._REGISTER_CHALLENGE_DIFFICULTY
        )
    )
    return f"{token}:{nonce}"


def test_disabled_user_cannot_authenticate(mu_isolated_root, seed_user, monkeypatch):
    from deeptutor.services import auth as auth_service
    from deeptutor.services.auth import set_disabled

    monkeypatch.setattr(auth_service, "AUTH_ENABLED", True)
    seed_user("bob", password="password1234")

    assert auth_service.authenticate("bob", "password1234") is not None
    assert set_disabled("bob", True) is True
    assert auth_service.authenticate("bob", "password1234") is None


def test_role_change_invalidates_existing_token(mu_isolated_root, seed_user, monkeypatch):
    from deeptutor.services import auth as auth_service
    from deeptutor.services.auth import create_token, decode_token, set_role

    monkeypatch.setattr(auth_service, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_service, "AUTH_SECRET", "test-secret")
    record = seed_user("alice", role="admin")

    token = create_token("alice", "admin", record["id"])
    assert decode_token(token).role == "admin"  # type: ignore[union-attr]

    assert set_role("alice", "user") is True
    assert decode_token(token) is None


def test_password_update_invalidates_existing_token_and_old_password(
    mu_isolated_root, seed_user, monkeypatch
):
    from deeptutor.services import auth as auth_service
    from deeptutor.services.auth import create_token, decode_token, update_password

    monkeypatch.setattr(auth_service, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_service, "AUTH_SECRET", "test-secret")
    record = seed_user("bob", password="old-password")

    token = create_token("bob", "admin", record["id"])
    assert decode_token(token) is not None

    assert update_password("bob", "new-password") is True
    assert decode_token(token) is None
    assert auth_service.authenticate("bob", "old-password") is None
    assert auth_service.authenticate("bob", "new-password") is not None


def test_profile_password_change_audits_and_invalidates_token(
    mu_isolated_root, seed_user, monkeypatch
):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.multi_user.audit import query_audit_events
    from deeptutor.services import auth as auth_service
    from deeptutor.services.auth import create_token, decode_token

    monkeypatch.setattr(auth_router, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_router, "POCKETBASE_ENABLED", False)
    monkeypatch.setattr(auth_service, "AUTH_SECRET", "test-secret")
    record = seed_user("bob", password="old-password")
    token = create_token("bob", "user", record["id"])

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1/auth")
    response = TestClient(app).put(
        "/api/v1/auth/profile/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "old-password", "new_password": "new-password"},
    )

    assert response.status_code == 200
    assert decode_token(token) is None
    assert "dt_token=" in response.headers.get("set-cookie", "")
    assert "Max-Age=0" in response.headers.get("set-cookie", "")
    event = query_audit_events(action="user_self_password_change")[0]
    assert event["target_user_id"] == record["id"]


def test_revoke_sessions_invalidates_existing_token(mu_isolated_root, seed_user, monkeypatch):
    from deeptutor.services import auth as auth_service
    from deeptutor.services.auth import create_token, decode_token, revoke_sessions

    monkeypatch.setattr(auth_service, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_service, "AUTH_SECRET", "test-secret")
    record = seed_user("bob", password="password1234")

    token = create_token("bob", "user", record["id"])
    assert decode_token(token) is not None

    assert revoke_sessions("bob") is True
    assert decode_token(token) is None


def test_profile_revoke_sessions_invalidates_current_token(mu_isolated_root, seed_user, monkeypatch):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.services import auth as auth_service
    from deeptutor.services.auth import create_token, decode_token

    monkeypatch.setattr(auth_router, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_router, "POCKETBASE_ENABLED", False)
    monkeypatch.setattr(auth_service, "AUTH_SECRET", "test-secret")
    record = seed_user("bob", password="password1234")
    token = create_token("bob", "user", record["id"])

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1/auth")
    response = TestClient(app).post(
        "/api/v1/auth/profile/revoke-sessions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert decode_token(token) is None


@pytest.fixture
def registration_client(mu_isolated_root, monkeypatch):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.api.security import reset_security_state
    from deeptutor.multi_user.identity import save_user

    reset_security_state()
    save_user("admin", "$2b$12$placeholder", role="admin")
    monkeypatch.setattr(auth_router, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_router, "POCKETBASE_ENABLED", False)
    monkeypatch.setattr(
        auth_router,
        "load_auth_settings",
        lambda: {
            "public_registration_enabled": True,
            "require_terms_acceptance": True,
            "terms_version": "terms-2026-06",
            "privacy_version": "privacy-2026-06",
        },
    )

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1/auth")
    return TestClient(app)


def test_public_registration_creates_regular_email_user(registration_client):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.multi_user.identity import get_user

    response = registration_client.post(
        "/api/v1/auth/register",
        json={
            "username": "learner@example.com",
            "password": "password1234",
            "terms_accepted": True,
            "captcha_token": _proof_for_registration(auth_router, "learner@example.com"),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "user"
    assert body["is_admin"] is False
    assert body["is_first_user"] is False
    assert body["requires_review"] is False
    record = get_user("learner@example.com")
    assert record is not None
    assert record["terms_accepted"] is True
    assert record["terms_accepted_at"]
    assert record["terms_version"] == "terms-2026-06"
    assert record["privacy_version"] == "privacy-2026-06"


def test_first_admin_registration_requires_challenge(mu_isolated_root, monkeypatch):
    import deeptutor.api.routers.auth as auth_router

    monkeypatch.setattr(auth_router, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_router, "POCKETBASE_ENABLED", False)

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1/auth")
    client = TestClient(app)

    missing = client.post(
        "/api/v1/auth/register",
        json={"username": "admin@example.com", "password": "password1234"},
    )
    assert missing.status_code == 400

    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "admin@example.com",
            "password": "password1234",
            "captcha_token": _proof_for_registration(auth_router, "admin@example.com"),
        },
    )
    assert response.status_code == 201
    assert response.json()["is_admin"] is True


def test_public_registration_requires_challenge(registration_client):
    response = registration_client.post(
        "/api/v1/auth/register",
        json={
            "username": "blocked@example.com",
            "password": "password1234",
            "terms_accepted": True,
        },
    )

    assert response.status_code == 400
    assert "challenge" in response.json()["detail"].lower()


def test_registration_challenge_uses_email_and_accepts_valid_proof(registration_client):
    from deeptutor.multi_user.identity import get_user

    challenge = registration_client.get(
        "/api/v1/auth/register/challenge",
        params={"email": "proof@example.com"},
    )
    assert challenge.status_code == 200
    token = challenge.json()["token"]
    difficulty = int(challenge.json()["difficulty"])
    nonce = next(
        str(i)
        for i in range(100_000)
        if hashlib.sha256(f"{token}:{i}".encode("utf-8")).hexdigest().startswith(
            "0" * difficulty
        )
    )

    response = registration_client.post(
        "/api/v1/auth/register",
        json={
            "username": "proof@example.com",
            "password": "password1234",
            "terms_accepted": True,
            "captcha_token": f"{token}:{nonce}",
        },
    )

    assert response.status_code == 201
    assert get_user("proof@example.com") is not None


def test_public_registration_review_creates_disabled_user(registration_client, monkeypatch):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.multi_user.identity import get_user
    from deeptutor.services import auth as auth_service
    from deeptutor.services.auth import authenticate

    monkeypatch.setattr(auth_service, "AUTH_ENABLED", True)
    monkeypatch.setattr(
        auth_router,
        "load_auth_settings",
        lambda: {
            "public_registration_enabled": True,
            "registration_review_required": True,
            "require_terms_acceptance": True,
        },
    )

    response = registration_client.post(
        "/api/v1/auth/register",
        json={
            "username": "review@example.com",
            "password": "password1234",
            "terms_accepted": True,
            "captcha_token": _proof_for_registration(auth_router, "review@example.com"),
        },
    )

    assert response.status_code == 201
    assert response.json()["requires_review"] is True
    record = get_user("review@example.com")
    assert record is not None
    assert record["disabled"] is True
    assert record["disabled_reason"] == "pending registration review"
    assert authenticate("review@example.com", "password1234") is None


def test_public_registration_requires_email_and_terms(registration_client):
    no_terms = registration_client.post(
        "/api/v1/auth/register",
        json={"username": "learner@example.com", "password": "password1234"},
    )
    assert no_terms.status_code == 400

    plain_username = registration_client.post(
        "/api/v1/auth/register",
        json={
            "username": "learner",
            "password": "password1234",
            "terms_accepted": True,
        },
    )
    assert plain_username.status_code == 422


def test_public_registration_does_not_invent_terms_acceptance(registration_client, monkeypatch):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.multi_user.identity import get_user

    monkeypatch.setattr(
        auth_router,
        "load_auth_settings",
        lambda: {
            "public_registration_enabled": True,
            "require_terms_acceptance": False,
        },
    )

    response = registration_client.post(
        "/api/v1/auth/register",
        json={
            "username": "no-terms@example.com",
            "password": "password1234",
            "captcha_token": _proof_for_registration(auth_router, "no-terms@example.com"),
        },
    )

    assert response.status_code == 201
    record = get_user("no-terms@example.com")
    assert record is not None
    assert record["terms_accepted"] is False
    assert record["terms_accepted_at"] == ""
    assert record["terms_version"] == ""
    assert record["privacy_version"] == ""


def test_public_registration_respects_max_users(registration_client, monkeypatch):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.multi_user.identity import get_user

    monkeypatch.setattr(
        auth_router,
        "load_auth_settings",
        lambda: {
            "public_registration_enabled": True,
            "require_terms_acceptance": True,
            "max_users": 1,
        },
    )

    response = registration_client.post(
        "/api/v1/auth/register",
        json={
            "username": "full@example.com",
            "password": "password1234",
            "terms_accepted": True,
            "captcha_token": _proof_for_registration(auth_router, "full@example.com"),
        },
    )

    assert response.status_code == 409
    assert "seat limit" in response.json()["detail"]
    assert get_user("full@example.com") is None


@pytest.fixture
def invite_registration_client(mu_isolated_root, monkeypatch):
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
        lambda: {
            "public_registration_enabled": False,
            "require_terms_acceptance": True,
        },
    )

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1/auth")
    return TestClient(app), auth_service.create_token("admin", "admin", admin["id"])


def test_admin_disable_user_records_and_clears_reason(invite_registration_client):
    from deeptutor.multi_user.identity import get_user, save_user

    client, token = invite_registration_client
    save_user("bob@example.com", "$2b$12$placeholder", role="user")
    headers = {"Authorization": f"Bearer {token}"}

    disabled = client.put(
        "/api/v1/auth/users/bob@example.com/disabled",
        headers=headers,
        json={"disabled": True, "reason": "chargeback risk"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["disabled_reason"] == "chargeback risk"
    assert get_user("bob@example.com")["disabled_reason"] == "chargeback risk"  # type: ignore[index]

    users = client.get("/api/v1/auth/users", headers=headers)
    bob = next(item for item in users.json() if item["username"] == "bob@example.com")
    assert bob["disabled"] is True
    assert bob["disabled_reason"] == "chargeback risk"

    enabled = client.put(
        "/api/v1/auth/users/bob@example.com/disabled",
        headers=headers,
        json={"disabled": False, "reason": "ignored"},
    )
    assert enabled.status_code == 200
    assert enabled.json()["disabled_reason"] == ""
    assert get_user("bob@example.com")["disabled_reason"] == ""  # type: ignore[index]


def test_admin_exports_users_csv_without_password_data(invite_registration_client):
    from deeptutor.multi_user.identity import save_user
    from deeptutor.services.auth import set_disabled

    client, token = invite_registration_client
    save_user("learner@example.com", "$2b$12$placeholder", role="user")
    assert set_disabled("learner@example.com", True, reason="policy review")

    response = client.get(
        "/api/v1/auth/users/export.csv",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "password" not in response.text.lower()
    assert "hash" not in response.text.lower()
    rows = list(csv.DictReader(StringIO(response.text)))
    learner = next(row for row in rows if row["email"] == "learner@example.com")
    assert learner["role"] == "user"
    assert learner["disabled"] == "true"
    assert learner["disabled_reason"] == "policy review"


def test_admin_imports_email_password_csv_as_regular_users(invite_registration_client):
    from deeptutor.multi_user.identity import get_user

    client, token = invite_registration_client
    csv_body = (
        "email,password,disabled,disabled_reason\n"
        "new@example.com,password1234,false,\n"
        "blocked@example.com,password5678,true,manual review\n"
    )

    response = client.post(
        "/api/v1/auth/users/import.csv",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("users.csv", csv_body, "text/csv")},
    )

    assert response.status_code == 200
    assert response.json()["created"] == 2
    assert get_user("new@example.com")["role"] == "user"  # type: ignore[index]
    blocked = get_user("blocked@example.com")
    assert blocked is not None
    assert blocked["role"] == "user"
    assert blocked["disabled"] is True
    assert blocked["disabled_reason"] == "manual review"


def test_admin_import_rejects_non_email_accounts_without_partial_create(
    invite_registration_client,
):
    from deeptutor.multi_user.identity import get_user

    client, token = invite_registration_client
    csv_body = "email,password\nvalid@example.com,password1234\n15555550123,password1234\n"

    response = client.post(
        "/api/v1/auth/users/import.csv",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("users.csv", csv_body, "text/csv")},
    )

    assert response.status_code == 422
    assert "valid email address" in response.json()["detail"]
    assert get_user("valid@example.com") is None
    assert get_user("15555550123") is None


def test_admin_import_respects_remaining_seats_without_partial_create(
    invite_registration_client,
    monkeypatch,
):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.multi_user.identity import get_user

    monkeypatch.setattr(
        auth_router,
        "load_auth_settings",
        lambda: {
            "public_registration_enabled": False,
            "require_terms_acceptance": True,
            "max_users": 2,
        },
    )
    client, token = invite_registration_client
    csv_body = "email,password\na@example.com,password1234\nb@example.com,password1234\n"

    response = client.post(
        "/api/v1/auth/users/import.csv",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("users.csv", csv_body, "text/csv")},
    )

    assert response.status_code == 409
    assert "seat limit" in response.json()["detail"]
    assert get_user("a@example.com") is None
    assert get_user("b@example.com") is None


def test_closed_registration_accepts_one_use_email_invite(invite_registration_client):
    from deeptutor.multi_user.identity import get_user
    from deeptutor.multi_user.invites import list_invites

    client, token = invite_registration_client
    headers = {"Authorization": f"Bearer {token}"}

    blocked = client.post(
        "/api/v1/auth/register",
        json={
            "username": "learner@example.com",
            "password": "password1234",
            "terms_accepted": True,
        },
    )
    assert blocked.status_code == 403

    created = client.post(
        "/api/v1/auth/invites",
        headers=headers,
        json={"email": "learner@example.com"},
    )
    assert created.status_code == 201
    invite_code = created.json()["code"]

    registered = client.post(
        "/api/v1/auth/register",
        json={
            "username": "learner@example.com",
            "password": "password1234",
            "terms_accepted": True,
            "invite_code": invite_code,
        },
    )
    assert registered.status_code == 201
    assert registered.json()["role"] == "user"
    assert get_user("learner@example.com") is not None
    assert list_invites()[0]["used_by"] == "learner@example.com"

    reused = client.post(
        "/api/v1/auth/register",
        json={
            "username": "second@example.com",
            "password": "password1234",
            "terms_accepted": True,
            "invite_code": invite_code,
        },
    )
    assert reused.status_code == 403


def test_invite_email_binding_is_enforced(invite_registration_client):
    client, token = invite_registration_client
    created = client.post(
        "/api/v1/auth/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "allowed@example.com"},
    )
    assert created.status_code == 201

    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "other@example.com",
            "password": "password1234",
            "terms_accepted": True,
            "invite_code": created.json()["code"],
        },
    )
    assert response.status_code == 403


def test_invite_is_restored_when_registration_write_fails(
    invite_registration_client, monkeypatch
):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.multi_user.invites import list_invites

    client, token = invite_registration_client
    created = client.post(
        "/api/v1/auth/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "learner@example.com"},
    )
    invite_code = created.json()["code"]

    def fail_add_user(*_args, **_kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(auth_router, "add_user", fail_add_user)

    with pytest.raises(RuntimeError, match="write failed"):
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "learner@example.com",
                "password": "password1234",
                "terms_accepted": True,
                "invite_code": invite_code,
            },
        )

    invite = next(item for item in list_invites() if item["code"] == invite_code)
    assert invite["used_by"] == ""
    assert invite["used_at"] == ""


def test_repeated_login_attempts_are_rate_limited(mu_isolated_root, monkeypatch):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.api.security import reset_security_state

    reset_security_state()
    monkeypatch.setattr(auth_router, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_router, "POCKETBASE_ENABLED", False)
    monkeypatch.setattr(auth_router, "authenticate", lambda *_: None)

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1/auth")
    client = TestClient(app)

    payload = {"username": "bob@example.com", "password": "wrong-password"}
    statuses = [client.post("/api/v1/auth/login", json=payload).status_code for _ in range(11)]

    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
