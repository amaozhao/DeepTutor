from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

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
    knowledge_progress_module = importlib.import_module("deeptutor.api.routers.knowledge_progress")
    router = knowledge_router_module.router
else:  # pragma: no cover - optional dependency in lightweight envs
    knowledge_router_module = None
    knowledge_progress_module = None
    router = None


def _build_app() -> FastAPI:
    if FastAPI is None or router is None:  # pragma: no cover - guarded by pytestmark
        raise RuntimeError("fastapi is not installed")
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/knowledge")
    return app


def test_get_progress_returns_persisted_progress(monkeypatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "knowledge_bases"
    kb_dir = base_dir / "kb"
    kb_dir.mkdir(parents=True)
    (kb_dir / ".progress.json").write_text(
        json.dumps({"stage": "processing", "percent": 25}),
        encoding="utf-8",
    )
    resource = SimpleNamespace(name="kb", base_dir=base_dir)
    monkeypatch.setattr(knowledge_progress_module, "resolve_kb", lambda _kb_name: resource)

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/knowledge/kb/progress")

    assert response.status_code == 200
    assert response.json()["stage"] == "processing"


def test_clear_progress_uses_writable_kb_resolver(monkeypatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "knowledge_bases"
    kb_dir = base_dir / "kb"
    kb_dir.mkdir(parents=True)
    progress_file = kb_dir / ".progress.json"
    progress_file.write_text(json.dumps({"stage": "processing"}), encoding="utf-8")

    class _Manager:
        def __init__(self, root: Path) -> None:
            self.base_dir = root

        def _load_config(self) -> dict:
            return {"knowledge_bases": {"kb": {"path": "kb"}}}

        def list_knowledge_bases(self) -> list[str]:
            return ["kb"]

    monkeypatch.setattr(knowledge_router_module, "get_kb_manager", lambda: _Manager(base_dir))

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/knowledge/kb/progress/clear")

    assert response.status_code == 200
    assert not progress_file.exists()


def test_task_stream_route_is_still_mounted() -> None:
    app = _build_app()
    assert "/api/v1/knowledge/tasks/{task_id}/stream" in {route.path for route in app.routes}
