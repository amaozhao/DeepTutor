"""Tests for admin-user helpers split from the auth router."""

from __future__ import annotations

import csv
from io import StringIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


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


def test_parse_user_import_csv_normalizes_and_validates_rows():
    from deeptutor.api.routers.users import parse_user_import_csv

    rows = parse_user_import_csv(
        (
            "email,password,disabled,disabled_reason\n"
            "NEW@Example.com,password1234,false,\n"
            "blocked@example.com,password5678,true,manual review\n"
        ).encode("utf-8")
    )

    assert rows == [
        {
            "email": "new@example.com",
            "password": "password1234",
            "disabled": False,
            "disabled_reason": "",
        },
        {
            "email": "blocked@example.com",
            "password": "password5678",
            "disabled": True,
            "disabled_reason": "manual review",
        },
    ]


@pytest.mark.parametrize(
    ("csv_body", "status_code", "detail"),
    [
        ("email,password\nbad-account,password1234\n", 422, "valid email address"),
        ("email,password\na@example.com,short\n", 422, "Password must be at least"),
        (
            "email,password\na@example.com,password1234\na@example.com,password5678\n",
            409,
            "duplicate",
        ),
        ("email\nnew@example.com\n", 400, "email,password"),
    ],
)
def test_parse_user_import_csv_rejects_invalid_input(csv_body, status_code, detail):
    from fastapi import HTTPException

    from deeptutor.api.routers.users import parse_user_import_csv

    with pytest.raises(HTTPException) as exc:
        parse_user_import_csv(csv_body.encode("utf-8"))

    assert exc.value.status_code == status_code
    assert detail in str(exc.value.detail)


def test_admin_user_csv_endpoints_stay_mounted_under_auth(mu_isolated_root, monkeypatch):
    from deeptutor.multi_user.identity import get_user, save_user
    from deeptutor.services.auth import set_disabled

    client, token = _client(mu_isolated_root, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}

    imported = client.post(
        "/api/v1/auth/users/import.csv",
        headers=headers,
        files={
            "file": (
                "users.csv",
                "email,password,disabled,disabled_reason\n"
                "new@example.com,password1234,false,\n"
                "blocked@example.com,password5678,true,manual review\n",
                "text/csv",
            )
        },
    )
    assert imported.status_code == 200
    assert imported.json()["created"] == 2
    assert get_user("new@example.com")["role"] == "user"  # type: ignore[index]
    assert get_user("blocked@example.com")["disabled_reason"] == "manual review"  # type: ignore[index]

    save_user("exported@example.com", "$2b$12$placeholder", role="user")
    assert set_disabled("exported@example.com", True, reason="policy review")

    exported = client.get("/api/v1/auth/users/export.csv", headers=headers)
    assert exported.status_code == 200
    assert "password" not in exported.text.lower()
    assert "hash" not in exported.text.lower()

    rows = list(csv.DictReader(StringIO(exported.text)))
    exported_row = next(row for row in rows if row["email"] == "exported@example.com")
    assert exported_row["disabled"] == "true"
    assert exported_row["disabled_reason"] == "policy review"
