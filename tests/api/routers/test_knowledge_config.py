from __future__ import annotations

import importlib
from pathlib import Path

import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - optional dependency in lightweight envs
    FastAPI = None
    TestClient = None

pytestmark = pytest.mark.skipif(
    FastAPI is None or TestClient is None, reason="fastapi not installed"
)

if FastAPI is not None and TestClient is not None:
    knowledge_router_module = importlib.import_module("deeptutor.api.routers.knowledge")
    config_router_module = importlib.import_module("deeptutor.api.routers.knowledge_config")
    router = knowledge_router_module.router
else:  # pragma: no cover - optional dependency in lightweight envs
    config_router_module = None
    router = None


def _build_app() -> FastAPI:
    if FastAPI is None or router is None:  # pragma: no cover - guarded by pytestmark
        raise RuntimeError("fastapi is not installed")
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/knowledge")
    return app


def _write_ready_llamaindex_version(kb_dir: Path) -> None:
    version_dir = kb_dir / "version-1"
    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / "docstore.json").write_text("{}", encoding="utf-8")
    (version_dir / "index_store.json").write_text("{}", encoding="utf-8")
    (version_dir / "meta.json").write_text(
        '{"provider": "llamaindex", "signature": "sig", "version": "version-1"}',
        encoding="utf-8",
    )


class _FakeConfigService:
    def __init__(self, config: dict | None = None) -> None:
        self.config: dict = config or {}

    def set_kb_config(self, kb_name: str, config: dict) -> None:
        self.kb_name = kb_name
        self.config.update(config)

    def get_kb_config(self, _kb_name: str) -> dict:
        return dict(self.config)


def test_update_config_coerces_legacy_provider_to_llamaindex(monkeypatch) -> None:
    fake_service = _FakeConfigService()
    config_module = importlib.import_module("deeptutor.services.config")
    monkeypatch.setattr(config_module, "get_kb_config_service", lambda: fake_service)

    with TestClient(_build_app()) as client:
        response = client.put(
            "/api/v1/knowledge/demo/config",
            json={"rag_provider": "raganything"},
        )

    assert response.status_code in {200, 204}
    assert fake_service.config.get("rag_provider") == "llamaindex"


def test_update_config_preserves_known_provider(monkeypatch) -> None:
    fake_service = _FakeConfigService()
    config_module = importlib.import_module("deeptutor.services.config")
    monkeypatch.setattr(config_module, "get_kb_config_service", lambda: fake_service)

    with TestClient(_build_app()) as client:
        response = client.put(
            "/api/v1/knowledge/demo/config",
            json={"rag_provider": "pageindex"},
        )

    assert response.status_code in {200, 204}
    assert fake_service.config.get("rag_provider") == "pageindex"


def test_update_config_rejects_provider_change_for_ready_index(monkeypatch, tmp_path: Path) -> None:
    kb_dir = tmp_path / "demo"
    kb_dir.mkdir(parents=True)
    _write_ready_llamaindex_version(kb_dir)

    fake_service = _FakeConfigService({"rag_provider": "llamaindex"})
    config_module = importlib.import_module("deeptutor.services.config")

    monkeypatch.setattr(config_module, "get_kb_config_service", lambda: fake_service)
    monkeypatch.setattr(config_router_module, "_kb_base_dir_resolver", lambda: tmp_path)

    with TestClient(_build_app()) as client:
        response = client.put(
            "/api/v1/knowledge/demo/config",
            json={"rag_provider": "pageindex"},
        )

    assert response.status_code == 409
    assert "ready llamaindex index" in response.json()["detail"]
    assert fake_service.config["rag_provider"] == "llamaindex"
