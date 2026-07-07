from __future__ import annotations

import importlib

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
    router = None


def _build_app() -> FastAPI:
    if FastAPI is None or router is None:  # pragma: no cover - guarded by pytestmark
        raise RuntimeError("fastapi is not installed")
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/knowledge")
    return app


def test_rag_providers_lists_llamaindex_and_pageindex() -> None:
    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/knowledge/rag-providers")

    assert response.status_code == 200
    payload = response.json()
    by_id = {p["id"]: p for p in payload["providers"]}
    assert set(by_id) == {
        "llamaindex",
        "pageindex",
        "graphrag",
        "lightrag",
        "lightrag-server",
    }
    assert by_id["llamaindex"]["requires_api_key"] is False
    assert by_id["pageindex"]["requires_api_key"] is True
    assert by_id["graphrag"]["requires_api_key"] is False
    assert by_id["lightrag"]["requires_api_key"] is False
    assert by_id["lightrag-server"]["requires_api_key"] is False
    assert by_id["lightrag-server"]["configured"] is True
    assert "hybrid" in by_id["lightrag"]["modes"]
    assert "mix" in by_id["lightrag-server"]["modes"]
    assert not by_id["llamaindex"].get("modes")


def test_set_rag_provider_mode_persists_validates_and_reflects() -> None:
    with TestClient(_build_app()) as client:
        ok = client.put("/api/v1/knowledge/rag-providers/lightrag/mode", json={"mode": "MIX"})
        assert ok.status_code == 200
        assert ok.json()["mode"] == "mix"

        providers = client.get("/api/v1/knowledge/rag-providers").json()["providers"]
        by_id = {p["id"]: p for p in providers}
        assert by_id["lightrag"]["default_mode"] == "mix"

        assert (
            client.put(
                "/api/v1/knowledge/rag-providers/lightrag/mode", json={"mode": "bogus"}
            ).status_code
            == 400
        )
        assert (
            client.put(
                "/api/v1/knowledge/rag-providers/llamaindex/mode", json={"mode": "x"}
            ).status_code
            == 404
        )


def test_rag_providers_marks_linkable() -> None:
    with TestClient(_build_app()) as client:
        providers = client.get("/api/v1/knowledge/rag-providers").json()["providers"]

    by_id = {p["id"]: p for p in providers}
    assert by_id["llamaindex"]["linkable"] is True
    assert by_id["graphrag"]["linkable"] is True
    assert by_id["lightrag"]["linkable"] is True
    assert by_id["pageindex"]["linkable"] is False
    assert by_id["lightrag-server"]["linkable"] is False
