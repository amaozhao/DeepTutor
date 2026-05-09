from __future__ import annotations

import json
import threading

import pytest

from deeptutor.api.utils.progress_broadcaster import ProgressBroadcaster
from deeptutor.api.utils.task_log_stream import KnowledgeTaskStreamManager
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
async def test_progress_tracker_emits_task_progress_to_captured_owner_from_thread(tmp_path):
    stream_manager = KnowledgeTaskStreamManager.get_instance()
    stream_manager._buffers.clear()
    stream_manager._subscribers.clear()
    from deeptutor.multi_user.context import reset_current_user, set_current_user
    from deeptutor.multi_user.models import CurrentUser, UserScope

    token = set_current_user(
        CurrentUser(
            id="user_alpha",
            username="user_alpha",
            role="user",
            scope=UserScope(kind="user", user_id="user_alpha", root=tmp_path / "user_alpha"),
        )
    )
    try:
        tracker = ProgressTracker("demo-kb", tmp_path)
        tracker.task_id = "kb_init_demo"
        stream_manager.ensure_task("kb_init_demo", user_id="user_alpha")
    finally:
        reset_current_user(token)

    thread = threading.Thread(
        target=tracker.update,
        args=(ProgressStage.PROCESSING_DOCUMENTS, "Embedding batches: 1/2 complete"),
        kwargs={"current": 1, "total": 2},
    )
    thread.start()
    thread.join()

    queue, backlog, loop = stream_manager.subscribe("kb_init_demo", user_id="user_alpha")
    stream_manager.unsubscribe("kb_init_demo", queue, loop, user_id="user_alpha")

    assert backlog
    assert backlog[-1]["event"] == "progress"
    assert backlog[-1]["payload"]["message"] == "Embedding batches: 1/2 complete"
    assert backlog[-1]["payload"]["stage"] == "processing_documents"


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
