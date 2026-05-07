from __future__ import annotations

import json

import pytest

from deeptutor.api.utils.progress_broadcaster import ProgressBroadcaster
from deeptutor.knowledge.manager import KnowledgeBaseManager
from deeptutor.knowledge.progress_tracker import ProgressStage, ProgressTracker


class _FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


def test_progress_tracker_persists_snapshot_and_config(tmp_path) -> None:
    tracker = ProgressTracker("demo-kb", tmp_path)

    tracker.update(
        ProgressStage.PROCESSING_DOCUMENTS,
        "Embedding batches: 2/8 complete",
        current=2,
        total=8,
    )

    assert tracker.progress_file.exists()

    with open(tracker.progress_file, encoding="utf-8") as f:
        payload = json.load(f)

    assert payload["stage"] == "processing_documents"
    assert payload["progress_percent"] == 25
    assert payload["message"] == "Embedding batches: 2/8 complete"

    manager = KnowledgeBaseManager(base_dir=str(tmp_path))
    status = manager.get_kb_status("demo-kb")

    assert status is not None
    assert status["status"] == "processing"
    assert status["progress"]["message"] == "Embedding batches: 2/8 complete"


def test_progress_tracker_rejects_traversal_kb_name(tmp_path) -> None:
    with pytest.raises(ValueError, match="Knowledge base name"):
        ProgressTracker("../outside", tmp_path)


def test_progress_tracker_get_progress_falls_back_to_config(tmp_path) -> None:
    manager = KnowledgeBaseManager(base_dir=str(tmp_path))
    manager.update_kb_status(
        name="demo-kb",
        status="processing",
        progress={
            "stage": "processing_documents",
            "message": "Recovered from kb_config",
            "percent": 60,
            "current": 3,
            "total": 5,
        },
    )

    tracker = ProgressTracker("demo-kb", tmp_path)

    assert tracker.get_progress() == {
        "stage": "processing_documents",
        "message": "Recovered from kb_config",
        "percent": 60,
        "current": 3,
        "total": 5,
    }


@pytest.mark.asyncio
async def test_progress_broadcaster_scopes_same_kb_name_by_user() -> None:
    broadcaster = ProgressBroadcaster()
    broadcaster._connections = {}
    alpha_ws = _FakeWebSocket()
    beta_ws = _FakeWebSocket()

    await broadcaster.connect("shared-kb", alpha_ws, user_id="user_alpha")
    await broadcaster.connect("shared-kb", beta_ws, user_id="user_beta")
    await broadcaster.broadcast("shared-kb", {"message": "alpha only"}, user_id="user_alpha")

    assert alpha_ws.messages == [
        {"type": "progress", "data": {"message": "alpha only"}},
    ]
    assert beta_ws.messages == []
