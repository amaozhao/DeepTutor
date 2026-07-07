from __future__ import annotations

import importlib
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
    knowledge_linked_module = importlib.import_module("deeptutor.api.routers.knowledge_linked")
    router = knowledge_router_module.router
else:  # pragma: no cover - optional dependency in lightweight envs
    knowledge_router_module = None
    knowledge_linked_module = None
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
        self.config = {
            "knowledge_bases": {
                "kb": {
                    "path": "kb",
                    "rag_provider": "llamaindex",
                    "needs_reindex": False,
                    "status": "ready",
                }
            }
        }
        self.folders = [
            {
                "id": "folder-1",
                "path": str(base_dir / "source"),
                "added_at": "2026-01-01T00:00:00",
                "file_count": 1,
            }
        ]
        self.changes = {
            "new_files": [],
            "modified_files": [],
            "new_count": 0,
            "modified_count": 0,
        }

    def _load_config(self) -> dict:
        return self.config

    def list_knowledge_bases(self) -> list[str]:
        return ["kb"]

    def update_kb_status(self, name: str, status: str, progress: dict | None = None) -> None:
        entry = self.config["knowledge_bases"][name]
        entry["status"] = status
        entry["progress"] = progress or {}

    def get_default(self) -> str:
        return "kb"

    def link_folder(self, _kb_name: str, folder_path: str) -> dict:
        linked = {
            "id": "folder-2",
            "path": folder_path,
            "added_at": "2026-01-02T00:00:00",
            "file_count": 0,
        }
        self.folders.append(linked)
        return linked

    def get_linked_folders(self, _kb_name: str) -> list[dict]:
        return list(self.folders)

    def unlink_folder(self, _kb_name: str, folder_id: str) -> bool:
        before = len(self.folders)
        self.folders = [folder for folder in self.folders if folder["id"] != folder_id]
        return len(self.folders) != before

    def detect_folder_changes(self, _kb_name: str, _folder_id: str) -> dict:
        return self.changes


def test_link_folder_uses_existing_knowledge_url(monkeypatch, tmp_path: Path) -> None:
    manager = _FakeKBManager(tmp_path / "knowledge_bases")
    monkeypatch.setattr(knowledge_router_module, "get_kb_manager", lambda: manager)

    with TestClient(_build_app()) as client:
        response = client.post(
            "/api/v1/knowledge/kb/link-folder",
            json={"folder_path": str(tmp_path / "docs")},
        )

    assert response.status_code == 200
    assert response.json()["id"] == "folder-2"
    assert response.json()["path"] == str(tmp_path / "docs")


def test_get_linked_folders_reads_resolved_resource(monkeypatch, tmp_path: Path) -> None:
    manager = _FakeKBManager(tmp_path / "knowledge_bases")
    resource = SimpleNamespace(name="kb")
    monkeypatch.setattr(knowledge_linked_module, "resolve_kb", lambda _kb_name: resource)
    monkeypatch.setattr(knowledge_linked_module, "manager_for_resource", lambda _resource: manager)

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/knowledge/kb/linked-folders")

    assert response.status_code == 200
    assert response.json()[0]["id"] == "folder-1"


def test_sync_folder_schedules_upload_task(monkeypatch, tmp_path: Path) -> None:
    manager = _FakeKBManager(tmp_path / "knowledge_bases")
    source_file = tmp_path / "source" / "new.txt"
    manager.changes = {
        "new_files": [str(source_file)],
        "modified_files": [],
        "new_count": 1,
        "modified_count": 0,
    }
    monkeypatch.setattr(knowledge_router_module, "get_kb_manager", lambda: manager)
    captured: dict = {}

    async def _upload_task(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(knowledge_router_module, "run_upload_processing_task", _upload_task)

    with TestClient(_build_app()) as client:
        response = client.post("/api/v1/knowledge/kb/sync-folder/folder-1")

    assert response.status_code == 200
    assert response.json()["new_files"] == 1
    assert captured["kb_name"] == "kb"
    assert captured["uploaded_file_paths"] == [str(source_file)]
    assert captured["folder_id"] == "folder-1"
    entry = manager.config["knowledge_bases"]["kb"]
    assert entry["status"] == "processing"
    assert entry["progress"]["stage"] == "starting"
    assert entry["progress"]["task_id"] == response.json()["task_id"]


def test_unlink_folder_reports_missing_id(monkeypatch, tmp_path: Path) -> None:
    manager = _FakeKBManager(tmp_path / "knowledge_bases")
    monkeypatch.setattr(knowledge_router_module, "get_kb_manager", lambda: manager)

    with TestClient(_build_app()) as client:
        response = client.delete("/api/v1/knowledge/kb/linked-folders/missing")

    assert response.status_code == 404
