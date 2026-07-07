from __future__ import annotations

import importlib
import json
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
    router = knowledge_router_module.router
else:  # pragma: no cover - optional dependency in lightweight envs
    knowledge_router_module = None
    router = None


def _build_app() -> FastAPI:
    if FastAPI is None or router is None:  # pragma: no cover - guarded by pytestmark
        raise RuntimeError("fastapi is not installed")
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/knowledge")
    return app


class _FakeKBManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.config: dict[str, dict] = {"knowledge_bases": {}}

    def register_lightrag_server_kb(
        self,
        name: str,
        server_url: str,
        *,
        api_key: str = "",
        search_mode: str = "",
        description: str = "",
    ) -> dict:
        if name in self.config.get("knowledge_bases", {}):
            raise ValueError(f"A knowledge base named '{name}' already exists.")
        entry = {
            "path": name,
            "type": "lightrag_server",
            "rag_provider": "lightrag-server",
            "server_url": server_url,
            "api_key": api_key,
            "status": "ready",
        }
        if search_mode:
            entry["search_mode"] = search_mode
        self.config.setdefault("knowledge_bases", {})[name] = entry
        return entry


def test_probe_folder_endpoint_finds_ready_index(tmp_path: Path) -> None:
    version = tmp_path / "version-1"
    version.mkdir()
    (version / "docstore.json").write_text("{}", encoding="utf-8")
    (version / "index_store.json").write_text("{}", encoding="utf-8")
    (version / "meta.json").write_text(
        json.dumps({"version": "version-1", "signature": "x", "layout": "flat"}),
        encoding="utf-8",
    )

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/knowledge/probe-folder",
            json={"folder_path": str(tmp_path), "rag_provider": "llamaindex"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["version"] == "version-1"


def test_probe_folder_endpoint_rejects_pageindex(tmp_path: Path) -> None:
    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/knowledge/probe-folder",
            json={"folder_path": str(tmp_path), "rag_provider": "pageindex"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]


def _patch_server_probe(monkeypatch, *, ok: bool, error: str | None = None) -> None:
    from deeptutor.services.rag.pipelines.lightrag_server import probe as probe_module

    async def _fake_probe(server_url: str, api_key: str = "", **_kwargs):
        result = probe_module.ServerProbe(base_url=server_url.rstrip("/"))
        result.ok = ok
        result.reachable = ok
        result.auth_required = bool(api_key)
        result.auth_ok = ok
        result.error = error
        return result

    monkeypatch.setattr(probe_module, "probe_server", _fake_probe)


def test_probe_lightrag_server_endpoint_reports_verdict(monkeypatch) -> None:
    _patch_server_probe(monkeypatch, ok=True)
    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/knowledge/probe-lightrag-server",
            json={"server_url": "http://localhost:9621", "api_key": "k"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["base_url"] == "http://localhost:9621"


def test_connect_lightrag_server_registers_pointer(monkeypatch, tmp_path: Path) -> None:
    manager = _FakeKBManager(tmp_path / "knowledge_bases")
    monkeypatch.setattr(knowledge_router_module, "get_kb_manager", lambda: manager)
    _patch_server_probe(monkeypatch, ok=True)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/knowledge/connect-lightrag-server",
            json={
                "name": "remote-kb",
                "server_url": "http://localhost:9621/",
                "api_key": "secret",
                "search_mode": "MIX",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["rag_provider"] == "lightrag-server"
    entry = manager.config["knowledge_bases"]["remote-kb"]
    assert entry["type"] == "lightrag_server"
    assert entry["server_url"] == "http://localhost:9621"
    assert entry["search_mode"] == "mix"


def test_connect_lightrag_server_rejects_unreachable(monkeypatch, tmp_path: Path) -> None:
    manager = _FakeKBManager(tmp_path / "knowledge_bases")
    monkeypatch.setattr(knowledge_router_module, "get_kb_manager", lambda: manager)
    _patch_server_probe(monkeypatch, ok=False, error="Could not reach a LightRAG server")

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/knowledge/connect-lightrag-server",
            json={"name": "bad", "server_url": "http://nope:9621"},
        )

    assert response.status_code == 400
    assert "LightRAG" in response.json()["detail"]
    assert "bad" not in manager.config["knowledge_bases"]
