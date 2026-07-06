from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_cross_site_write_is_rejected_when_auth_enabled(monkeypatch):
    from deeptutor.api import main as api_main
    from deeptutor.api.security import reset_security_state

    reset_security_state()
    monkeypatch.setattr(
        api_main,
        "load_auth_settings",
        lambda: {
            "enabled": True,
            "csrf_protection_enabled": True,
            "cookie_secure": True,
            "public_registration_enabled": False,
            "require_terms_acceptance": True,
        },
    )
    monkeypatch.setattr(
        api_main,
        "_cors_settings",
        {
            "allow_origins": ["https://app.example.com"],
            "allow_origin_regex": None,
            "mode": "explicit",
        },
    )
    client = TestClient(api_main.app)

    blocked = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://evil.example.com"},
    )
    assert blocked.status_code == 403

    allowed = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://app.example.com"},
    )
    assert allowed.status_code == 200


def test_production_security_warnings_for_auth_without_secure_public_origin(monkeypatch):
    from deeptutor.api import security

    monkeypatch.setattr(
        security,
        "load_auth_settings",
        lambda: {
            "enabled": True,
            "cookie_secure": False,
            "public_registration_enabled": False,
            "require_terms_acceptance": True,
        },
    )
    monkeypatch.setattr(
        security,
        "load_system_settings",
        lambda: {"cors_origin": "", "cors_origins": []},
    )
    monkeypatch.setattr(
        security,
        "load_integrations_settings",
        lambda: {"pocketbase_url": ""},
    )

    warnings = security.production_security_warnings()

    assert any("cookie_secure=false" in item for item in warnings)
    assert any("No non-localhost CORS origin" in item for item in warnings)


def test_production_security_warnings_for_pocketbase_multi_user(monkeypatch):
    from deeptutor.api import security

    monkeypatch.setattr(
        security,
        "load_auth_settings",
        lambda: {
            "enabled": True,
            "cookie_secure": True,
            "public_registration_enabled": False,
            "require_terms_acceptance": True,
        },
    )
    monkeypatch.setattr(
        security,
        "load_system_settings",
        lambda: {"cors_origin": "https://app.example.com", "cors_origins": []},
    )
    monkeypatch.setattr(
        security,
        "load_integrations_settings",
        lambda: {"pocketbase_url": "http://127.0.0.1:8090"},
    )

    warnings = security.production_security_warnings()

    assert any("PocketBase is single-user only" in item for item in warnings)


def test_production_security_warnings_for_multi_worker_auth(monkeypatch):
    from deeptutor.api import security

    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    monkeypatch.setattr(
        security,
        "load_auth_settings",
        lambda: {
            "enabled": True,
            "cookie_secure": True,
            "public_registration_enabled": False,
            "require_terms_acceptance": True,
        },
    )
    monkeypatch.setattr(
        security,
        "load_system_settings",
        lambda: {"cors_origin": "https://app.example.com", "cors_origins": []},
    )
    monkeypatch.setattr(
        security,
        "load_integrations_settings",
        lambda: {"pocketbase_url": ""},
    )

    warnings = security.production_security_warnings()

    assert any("2 backend workers configured" in item for item in warnings)
    assert any("external storage" in item for item in warnings)


def test_file_rate_limiter_shares_counts_across_instances(tmp_path: Path):
    from deeptutor.api.security import FileSlidingWindowRateLimiter

    first = FileSlidingWindowRateLimiter(root=tmp_path)
    second = FileSlidingWindowRateLimiter(root=tmp_path)

    assert first.allow("login:ip:alice", limit=1, window_seconds=60, now=100.0) is True
    assert second.allow("login:ip:alice", limit=1, window_seconds=60, now=101.0) is False
    assert second.allow("login:ip:alice", limit=1, window_seconds=60, now=161.0) is True


def test_system_status_writable_dir_healthcheck(tmp_path: Path):
    from deeptutor.api.routers.system import _writable_dir_status

    result = _writable_dir_status(tmp_path / "usage")

    assert result["status"] == "ok"
    assert (tmp_path / "usage").is_dir()


def test_system_status_marks_file_backed_deployment_single_replica(monkeypatch):
    from deeptutor.api.routers import system

    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
    monkeypatch.setattr(system, "load_integrations_settings", lambda: {"pocketbase_url": ""})

    result = system._deployment_status()

    assert result["status"] == "single_replica_beta"
    assert result["multi_replica_ready"] is False
    assert isinstance(result["shared_state"], dict)
    assert result["shared_state"]["token_revocation"] == "file_token_version"
    assert result["shared_state"]["rate_limit"] == "file"
    assert any("token-version revocation" in item for item in result["blocking_reasons"])


def test_system_status_reports_multi_worker_blocker(monkeypatch):
    from deeptutor.api.routers import system

    monkeypatch.setenv("UVICORN_WORKERS", "3")
    monkeypatch.setattr(system, "load_integrations_settings", lambda: {"pocketbase_url": ""})

    result = system._deployment_status()

    assert result["multi_replica_ready"] is False
    assert result["shared_state"]["backend_workers"] == 3
    assert any("multiple backend workers configured" in item for item in result["blocking_reasons"])


def test_container_health_allows_single_worker_beta(monkeypatch):
    from deeptutor.api.routers import system

    monkeypatch.setattr(system, "_writable_dir_status", lambda _path: {"status": "ok"})
    monkeypatch.setattr(
        system,
        "_deployment_status",
        lambda: {
            "multi_replica_ready": False,
            "shared_state": {"backend_workers": 1},
            "blocking_reasons": ["auth/token revocation is file-backed"],
        },
    )

    status_code, payload = system._container_health()

    assert status_code == 200
    assert payload["status"] == "ok"
    assert payload["failures"] == []


def test_container_health_fails_for_multi_worker_without_shared_state(monkeypatch):
    from deeptutor.api.routers import system

    monkeypatch.setattr(system, "_writable_dir_status", lambda _path: {"status": "ok"})
    monkeypatch.setattr(
        system,
        "_deployment_status",
        lambda: {"shared_state": {"backend_workers": 2}, "blocking_reasons": []},
    )

    status_code, payload = system._container_health()

    assert status_code == 503
    assert payload["status"] == "error"
    assert payload["failures"] == [
        "multiple backend workers configured without external auth/quota storage"
    ]


def test_container_health_fails_when_rate_store_is_unwritable(monkeypatch):
    from deeptutor.api.routers import system
    from deeptutor.multi_user import paths

    def fake_status(path):
        if path == paths.SYSTEM_ROOT / "rate":
            return {"status": "error", "error": "denied"}
        return {"status": "ok"}

    monkeypatch.setattr(system, "_writable_dir_status", fake_status)
    monkeypatch.setattr(
        system,
        "_deployment_status",
        lambda: {"shared_state": {"backend_workers": 1}, "blocking_reasons": []},
    )

    status_code, payload = system._container_health()

    assert status_code == 503
    assert payload["failures"] == ["rate store is not writable"]


def test_container_health_fails_when_auth_store_is_unwritable(monkeypatch):
    from deeptutor.api.routers import system
    from deeptutor.multi_user import paths

    def fake_status(path):
        if path == paths.SYSTEM_ROOT / "auth":
            return {"status": "error", "error": "denied"}
        return {"status": "ok"}

    monkeypatch.setattr(system, "_writable_dir_status", fake_status)
    monkeypatch.setattr(
        system,
        "_deployment_status",
        lambda: {"shared_state": {"backend_workers": 1}, "blocking_reasons": []},
    )

    status_code, payload = system._container_health()

    assert status_code == 503
    assert payload["failures"] == ["auth store is not writable"]


def test_public_health_endpoint_uses_container_health(monkeypatch):
    from deeptutor.api import main as api_main
    from deeptutor.api.routers import system

    monkeypatch.setattr(
        system,
        "_container_health",
        lambda: (503, {"status": "error", "failures": ["bad deployment"]}),
    )

    response = TestClient(api_main.app).get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "failures": ["bad deployment"]}


def test_system_status_marks_pocketbase_unsupported_for_multi_user(monkeypatch):
    from deeptutor.api.routers import system

    monkeypatch.setattr(
        system,
        "load_integrations_settings",
        lambda: {"pocketbase_url": "http://127.0.0.1:8090"},
    )

    result = system._deployment_status()

    assert result["multi_replica_ready"] is False
    assert result["shared_state"]["auth"] == "pocketbase_single_user"
    assert result["pocketbase_multi_user_supported"] is False
    assert any(
        "PocketBase multi-user/SaaS mode is unsupported" in item
        for item in result["blocking_reasons"]
    )


def test_attachment_download_requires_session_in_current_store(
    tmp_path: Path,
    monkeypatch,
):
    from deeptutor.api.routers import attachments
    from deeptutor.multi_user import paths as mu_paths
    from deeptutor.multi_user.audit import query_audit_events
    from deeptutor.multi_user.context import reset_current_user, set_current_user
    from deeptutor.multi_user.models import CurrentUser, UserScope
    from deeptutor.services.storage.attachment_store import LocalDiskAttachmentStore

    session_id = "sess1"
    attachment_id = "att1"
    filename = "file.txt"
    store = LocalDiskAttachmentStore(root=tmp_path)
    session_dir = tmp_path / session_id
    session_dir.mkdir()
    (session_dir / f"{attachment_id}_{filename}").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(mu_paths, "SYSTEM_ROOT", tmp_path / "system")

    class _MissingSessionStore:
        async def get_session(self, _session_id: str):
            return None

    class _PresentSessionStore:
        async def get_session(self, _session_id: str):
            return {"id": _session_id}

    # Keep this test on FastAPI's real routing stack without importing api.main.
    from fastapi import FastAPI

    fastapi_app = FastAPI()
    fastapi_app.include_router(attachments.router, prefix="/api/attachments")
    client = TestClient(fastapi_app)
    monkeypatch.setattr(attachments, "get_attachment_store", lambda: store)

    user = CurrentUser("u_test", "user@example.com", "user", UserScope("user", "u_test", tmp_path))
    token = set_current_user(user)
    try:
        monkeypatch.setattr(attachments, "get_session_store", lambda: _MissingSessionStore())
        missing = client.get(f"/api/attachments/{session_id}/{attachment_id}/{filename}")
        assert missing.status_code == 404
        assert query_audit_events(action="download") == []

        monkeypatch.setattr(attachments, "get_session_store", lambda: _PresentSessionStore())
        present = client.get(f"/api/attachments/{session_id}/{attachment_id}/{filename}")
        assert present.status_code == 200
        assert present.content == b"secret"
        event = query_audit_events(action="download")[0]
        assert event["resource_type"] == "attachment"
        assert event["resource_id"] == attachment_id
        assert event["user_id"] == "u_test"
        assert event["extra"] == {"session_id": session_id, "filename": filename}
    finally:
        reset_current_user(token)


def test_unified_websocket_turn_start_is_rate_limited(monkeypatch):
    from fastapi import FastAPI

    from deeptutor.api.routers import auth as auth_router
    from deeptutor.api.routers import unified_ws
    from deeptutor.api.security import reset_security_state
    from deeptutor.services import session as session_module

    class _FakeRuntime:
        async def start_turn(self, msg):
            return {"id": "session"}, {"id": f"turn-{msg.get('content', '')}"}

        async def subscribe_turn(self, _turn_id, after_seq=0):
            if False:
                yield {"type": "never", "after_seq": after_seq}

    reset_security_state()
    monkeypatch.setattr(auth_router, "AUTH_ENABLED", False)
    monkeypatch.setattr(session_module, "get_turn_runtime_manager", lambda: _FakeRuntime())

    app = FastAPI()
    app.include_router(unified_ws.router, prefix="/api/v1")
    client = TestClient(app)

    with client.websocket_connect("/api/v1/ws") as ws:
        for index in range(31):
            ws.send_text(json.dumps({"type": "start_turn", "content": str(index)}))
        blocked = json.loads(ws.receive_text())

    assert blocked["status"] == 429
    assert "Too many requests" in blocked["content"]
