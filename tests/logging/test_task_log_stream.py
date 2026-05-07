import json

import pytest

from deeptutor.api.utils.task_id_manager import TaskIDManager
from deeptutor.api.utils.task_log_stream import KnowledgeTaskStreamManager


@pytest.mark.asyncio
async def test_knowledge_task_stream_emits_process_log_sse_event():
    manager = KnowledgeTaskStreamManager()
    manager.ensure_task("task-1")
    manager.emit_log("task-1", "Indexing started")

    stream = manager.stream("task-1")
    try:
        chunk = await anext(stream)
    finally:
        await stream.aclose()

    lines = chunk.splitlines()
    header, data_line = lines[:2]
    assert header == "event: process_log"
    payload = json.loads(data_line.removeprefix("data: "))
    assert payload["type"] == "process_log"
    assert payload["message"] == "Indexing started"
    assert payload["context"]["task_id"] == "task-1"


def test_task_id_manager_records_and_checks_task_owner() -> None:
    manager = TaskIDManager()
    manager._task_ids.clear()
    manager._task_metadata.clear()

    task_id = manager.generate_task_id("kb_upload", "alpha", user_id="user_alpha")

    assert manager.is_task_owned_by(task_id, "user_alpha") is True
    assert manager.is_task_owned_by(task_id, "user_beta") is False


@pytest.mark.asyncio
async def test_knowledge_task_stream_is_scoped_by_user_id():
    manager = KnowledgeTaskStreamManager()
    manager.ensure_task("same-task", user_id="user_alpha")
    manager.ensure_task("same-task", user_id="user_beta")
    manager.emit_log("same-task", "alpha log", user_id="user_alpha")
    manager.emit_log("same-task", "beta log", user_id="user_beta")

    alpha_stream = manager.stream("same-task", user_id="user_alpha")
    beta_stream = manager.stream("same-task", user_id="user_beta")
    try:
        alpha_chunk = await anext(alpha_stream)
        beta_chunk = await anext(beta_stream)
    finally:
        await alpha_stream.aclose()
        await beta_stream.aclose()

    assert "alpha log" in alpha_chunk
    assert "beta log" not in alpha_chunk
    assert "beta log" in beta_chunk
    assert "alpha log" not in beta_chunk
