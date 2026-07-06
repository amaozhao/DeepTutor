from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
import logging
from pathlib import Path
import zipfile

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from deeptutor.multi_user.audit import log_admin_action, query_audit_events
from deeptutor.multi_user.data_governance import (
    apply_data_retention_policy,
    apply_user_delete_policy,
    export_user_data,
    save_data_governance_settings,
)
from deeptutor.multi_user.grants import save_grant
from deeptutor.multi_user.usage import record_usage


def _seed_admin_and_user(seed_user) -> tuple[str, str]:
    seed_user("admin", role="admin")
    user = seed_user("alice")
    return "alice", str(user["id"])


def test_export_user_data_includes_workspace_grant_and_usage(seed_user):
    from deeptutor.multi_user import paths
    from deeptutor.multi_user.identity import record_terms_acceptance, set_disabled

    username, user_id = _seed_admin_and_user(seed_user)
    set_disabled(username, True, reason="policy review")
    record_terms_acceptance(
        username,
        terms_version="terms-2026-06",
        privacy_version="privacy-2026-06",
    )
    workspace = paths.ensure_user_workspace(user_id)
    (workspace / "notes.txt").write_text("private notes", encoding="utf-8")
    save_grant(user_id, {"quota": {"daily_call_limit": 3}})
    record_usage(
        user_id=user_id,
        username=username,
        session_id="s1",
        turn_id="t1",
        capability="chat",
        provider="minimax",
        model="M3",
        summary={"total_calls": 1, "total_tokens": 9},
    )

    archive = export_user_data(user_id, username)

    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "workspace/notes.txt" in names
        assert "system/account.json" in names
        assert "system/grant.json" in names
        assert "system/usage.jsonl" in names
        assert "private notes" == zf.read("workspace/notes.txt").decode()
        account = json.loads(zf.read("system/account.json").decode())
        assert account["username"] == username
        assert account["disabled_reason"] == "policy review"
        assert account["terms_version"] == "terms-2026-06"
        assert account["privacy_version"] == "privacy-2026-06"
        assert "hash" not in account
        assert user_id in zf.read("system/usage.jsonl").decode()


def test_delete_policy_archive_moves_workspace_and_grant(seed_user):
    from deeptutor.multi_user import paths

    _username, user_id = _seed_admin_and_user(seed_user)
    workspace = paths.ensure_user_workspace(user_id)
    (workspace / "notes.txt").write_text("private notes", encoding="utf-8")
    save_grant(user_id, {"quota": {"daily_call_limit": 3}})

    result = apply_user_delete_policy(user_id, "archive")

    archive = result["archive"]
    assert result["workspace"] == "archived"
    assert not workspace.exists()
    assert (paths.SYSTEM_ROOT / "grants" / f"{user_id}.json").exists() is False
    assert (paths.SYSTEM_ROOT / "deleted_users").exists()
    assert "deleted_users" in archive
    assert (Path(archive) / "manifest.json").exists()
    assert not (Path(archive) / "manifest.tmp").exists()
    assert (paths.SYSTEM_ROOT / "grants" / f"{user_id}.lock").exists()


def test_delete_policy_hard_delete_uses_grant_write_lock(seed_user):
    from deeptutor.multi_user import paths

    _username, user_id = _seed_admin_and_user(seed_user)
    save_grant(user_id, {"quota": {"daily_call_limit": 3}})
    lock_file = paths.SYSTEM_ROOT / "grants" / f"{user_id}.lock"
    if lock_file.exists():
        lock_file.unlink()

    result = apply_user_delete_policy(user_id, "delete")

    assert result["grant"] == "deleted"
    assert not (paths.SYSTEM_ROOT / "grants" / f"{user_id}.json").exists()
    assert lock_file.exists()


def test_data_retention_policy_prunes_configured_files_and_archives(mu_isolated_root):
    from deeptutor.multi_user import paths

    def days_ago(days: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    paths.ensure_system_dirs()
    audit_file = paths.SYSTEM_ROOT / "audit" / "usage.jsonl"
    usage_file = paths.SYSTEM_ROOT / "usage" / "llm_usage.jsonl"
    audit_file.write_text(
        "\n".join(
            [
                json.dumps({"time": days_ago(40), "action": "old"}),
                json.dumps({"time": days_ago(1), "action": "new"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    usage_file.write_text(
        "\n".join(
            [
                json.dumps({"time": days_ago(50), "user_id": "old"}),
                json.dumps({"time": days_ago(2), "user_id": "new"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    deleted_root = paths.SYSTEM_ROOT / "deleted_users"
    old_archive = deleted_root / "u_old-20250101T000000Z"
    new_archive = deleted_root / "u_new-20260101T000000Z"
    old_archive.mkdir(parents=True)
    new_archive.mkdir(parents=True)
    (old_archive / "manifest.json").write_text(
        json.dumps({"archived_at": days_ago(60)}),
        encoding="utf-8",
    )
    (new_archive / "manifest.json").write_text(
        json.dumps({"archived_at": days_ago(1)}),
        encoding="utf-8",
    )
    save_data_governance_settings(
        {
            "audit_retention_days": 30,
            "usage_retention_days": 30,
            "deleted_user_retention_days": 30,
        }
    )

    result = apply_data_retention_policy()

    assert result["removed_total"] == 3
    assert result["audit"]["removed"] == 1
    assert result["usage"]["removed"] == 1
    assert result["deleted_users"]["removed"] == 1
    assert "old" not in audit_file.read_text(encoding="utf-8")
    assert "old" not in usage_file.read_text(encoding="utf-8")
    assert not audit_file.with_suffix(".tmp").exists()
    assert not usage_file.with_suffix(".tmp").exists()
    assert old_archive.exists() is False
    assert new_archive.exists()


def test_data_retention_prune_uses_audit_write_lock(mu_isolated_root):
    from deeptutor.multi_user import paths

    paths.ensure_system_dirs()
    audit_file = paths.SYSTEM_ROOT / "audit" / "usage.jsonl"
    audit_file.write_text(
        json.dumps(
            {
                "time": (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(),
                "action": "old",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    save_data_governance_settings({"audit_retention_days": 30})
    lock_file = paths.SYSTEM_ROOT / "audit" / "usage.lock"
    if lock_file.exists():
        lock_file.unlink()

    result = apply_data_retention_policy()

    assert result["audit"]["removed"] == 1
    assert lock_file.exists()


def test_multi_user_export_endpoint_returns_zip(seed_user):
    from deeptutor.multi_user import router as multi_router

    username, user_id = _seed_admin_and_user(seed_user)
    app = FastAPI()
    app.dependency_overrides[multi_router.require_admin] = lambda: object()
    app.include_router(multi_router.router, prefix="/api/v1/multi-user")
    client = TestClient(app)

    response = client.get(f"/api/v1/multi-user/users/{user_id}/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert f"deeptutor-user-{username}-{user_id}.zip" in response.headers["content-disposition"]


def _auth_client(monkeypatch) -> TestClient:
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.services import auth as auth_service

    monkeypatch.setattr(auth_router, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_router, "POCKETBASE_ENABLED", False)
    monkeypatch.setattr(auth_service, "AUTH_SECRET", "test-secret")
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1/auth")
    return TestClient(app)


def test_profile_export_endpoint_returns_current_user_zip(seed_user, monkeypatch):
    from deeptutor.multi_user import paths
    from deeptutor.services.auth import create_token

    seed_user("admin", role="admin")
    user = seed_user("alice", password="password1234")
    user_id = str(user["id"])
    workspace = paths.ensure_user_workspace(user_id)
    (workspace / "notes.txt").write_text("private notes", encoding="utf-8")
    client = _auth_client(monkeypatch)
    token = create_token("alice", "user", user_id)

    response = client.get(
        "/api/v1/auth/profile/export",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert f"deeptutor-user-alice-{user_id}.zip" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert "workspace/notes.txt" in zf.namelist()
        assert zf.read("workspace/notes.txt").decode() == "private notes"
    assert query_audit_events(action="user_self_export")[0]["target_user_id"] == user_id


def test_profile_delete_requires_password_and_deletes_current_user_data(seed_user, monkeypatch):
    from deeptutor.multi_user import paths
    from deeptutor.multi_user.identity import get_user
    from deeptutor.services.auth import create_token, decode_token

    seed_user("admin", role="admin")
    user = seed_user("alice", password="password1234")
    user_id = str(user["id"])
    workspace = paths.ensure_user_workspace(user_id)
    (workspace / "notes.txt").write_text("private notes", encoding="utf-8")
    save_grant(user_id, {"quota": {"daily_call_limit": 3}})
    client = _auth_client(monkeypatch)
    token = create_token("alice", "user", user_id)
    headers = {"Authorization": f"Bearer {token}"}

    wrong = client.request(
        "DELETE",
        "/api/v1/auth/profile",
        headers=headers,
        json={"password": "wrong-password", "data_action": "delete"},
    )
    assert wrong.status_code == 400
    assert get_user("alice") is not None

    response = client.request(
        "DELETE",
        "/api/v1/auth/profile",
        headers=headers,
        json={"password": "password1234", "data_action": "delete"},
    )

    assert response.status_code == 200
    assert response.json()["data_policy"]["workspace"] == "deleted"
    assert get_user("alice") is None
    assert not workspace.exists()
    assert not (paths.SYSTEM_ROOT / "grants" / f"{user_id}.json").exists()
    assert decode_token(token) is None
    assert query_audit_events(action="user_self_delete")[0]["target_user_id"] == user_id


def test_profile_delete_keeps_user_when_data_policy_fails(seed_user, monkeypatch):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.multi_user.identity import get_user
    from deeptutor.services.auth import create_token

    seed_user("admin", role="admin")
    user = seed_user("alice", password="password1234")
    client = _auth_client(monkeypatch)

    def fail_data_policy(*_args, **_kwargs):
        raise HTTPException(status_code=500, detail="policy failed")

    monkeypatch.setattr(auth_router, "_apply_user_data_policy", fail_data_policy)

    response = client.request(
        "DELETE",
        "/api/v1/auth/profile",
        headers={"Authorization": f"Bearer {create_token('alice', 'user', user['id'])}"},
        json={"password": "password1234", "data_action": "delete"},
    )

    assert response.status_code == 500
    assert get_user("alice") is not None


def test_admin_delete_keeps_user_when_data_policy_fails(seed_user, monkeypatch):
    import deeptutor.api.routers.auth as auth_router
    from deeptutor.multi_user.identity import get_user
    from deeptutor.services.auth import create_token

    admin = seed_user("admin", role="admin")
    seed_user("alice")
    client = _auth_client(monkeypatch)

    def fail_data_policy(*_args, **_kwargs):
        raise HTTPException(status_code=500, detail="policy failed")

    monkeypatch.setattr(auth_router, "_apply_user_data_policy", fail_data_policy)

    response = client.delete(
        "/api/v1/auth/users/alice?data_action=delete",
        headers={"Authorization": f"Bearer {create_token('admin', 'admin', admin['id'])}"},
    )

    assert response.status_code == 500
    assert get_user("alice") is not None


def test_query_audit_events_filters_newest_first(mu_isolated_root):
    log_admin_action("user_create", target_user_id="u1", summary={"username": "alice"})
    log_admin_action("grant_set", target_user_id="u1", summary={"model_count": 1})
    log_admin_action("user_create", target_user_id="u2", summary={"username": "bob"})

    events = query_audit_events(action="user_create", limit=10)

    assert [event["target_user_id"] for event in events] == ["u2", "u1"]


def test_audit_writes_use_local_file_lock(mu_isolated_root):
    from deeptutor.multi_user import paths

    log_admin_action("user_create", target_user_id="u1", summary={"username": "alice"})

    assert (paths.SYSTEM_ROOT / "audit" / "usage.lock").exists()


def test_audit_queries_do_not_take_write_lock(mu_isolated_root):
    from deeptutor.multi_user import paths

    log_admin_action("user_create", target_user_id="u1", summary={"username": "alice"})
    lock_file = paths.SYSTEM_ROOT / "audit" / "usage.lock"
    lock_file.unlink()

    assert query_audit_events(action="user_create", limit=10)
    assert not lock_file.exists()


def test_audit_write_failure_logs_without_breaking_request(mu_isolated_root, monkeypatch, caplog):
    import deeptutor.multi_user.audit as audit

    def fail_lock():
        raise OSError("disk full")

    monkeypatch.setattr(audit, "_audit_write_lock", fail_lock)

    with caplog.at_level(logging.ERROR, logger="deeptutor.multi_user.audit"):
        log_admin_action("user_create", target_user_id="u1", summary={"username": "alice"})

    assert "Failed to write audit event: user_create" in caplog.text


def test_audit_query_logs_malformed_lines_and_returns_valid_events(mu_isolated_root, caplog):
    from deeptutor.multi_user import paths

    audit_file = paths.SYSTEM_ROOT / "audit" / "usage.jsonl"
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    audit_file.write_text(
        "\n".join(
            [
                "{not-json}",
                json.dumps({"action": "user_create", "target_user_id": "u1"}),
            ]
        ),
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="deeptutor.multi_user.audit"):
        events = query_audit_events(action="user_create", limit=10)

    assert [event["target_user_id"] for event in events] == ["u1"]
    assert "Skipping malformed audit log line" in caplog.text


def test_data_governance_settings_endpoint_normalizes_and_audits(mu_isolated_root):
    from deeptutor.multi_user import router as multi_router

    app = FastAPI()
    app.dependency_overrides[multi_router.require_admin] = lambda: object()
    app.include_router(multi_router.router, prefix="/api/v1/multi-user")
    client = TestClient(app)

    response = client.put(
        "/api/v1/multi-user/admin/data-governance",
        json={
            "audit_retention_days": 90,
            "usage_retention_days": -1,
            "deleted_user_retention_days": 30,
        },
    )

    assert response.status_code == 200
    assert response.json()["settings"] == {
        "audit_retention_days": 90,
        "usage_retention_days": 0,
        "deleted_user_retention_days": 30,
    }
    assert (
        client.get("/api/v1/multi-user/admin/data-governance").json()["settings"][
            "audit_retention_days"
        ]
        == 90
    )
    assert (
        client.get("/api/v1/multi-user/admin/audit?action=data_governance_update").json()["events"][
            0
        ]["summary"]["audit_retention_days"]
        == 90
    )

    pruned = client.post("/api/v1/multi-user/admin/data-governance/prune")
    assert pruned.status_code == 200
    assert pruned.json()["removed_total"] == 0
    assert (
        client.get("/api/v1/multi-user/admin/audit?action=data_governance_prune").json()["events"][
            0
        ]["summary"]["removed_total"]
        == 0
    )


def test_data_governance_settings_write_is_atomic(mu_isolated_root):
    from deeptutor.multi_user import paths

    saved = save_data_governance_settings({"audit_retention_days": 14})

    settings_file = paths.get_admin_path_service().get_settings_file("data_governance")
    assert saved["audit_retention_days"] == 14
    assert json.loads(settings_file.read_text(encoding="utf-8"))["audit_retention_days"] == 14
    assert not settings_file.with_suffix(".tmp").exists()
