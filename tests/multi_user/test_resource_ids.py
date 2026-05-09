from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.multi_user.resource_ids import safe_resolve_under
from deeptutor.services.path_service import get_path_service
from deeptutor.services.tutorbot.manager import TutorBotManager
from deeptutor.tutorbot.config import paths as tutorbot_paths


def test_path_service_rejects_unsafe_resource_ids(as_multi_user) -> None:
    with as_multi_user("u_alpha"):
        service = get_path_service()
        unsafe_calls = [
            lambda: service.get_task_workspace("chat", "../escape"),
            lambda: service.get_session_workspace("chat", "session/escape"),
            lambda: service.get_task_dir("question", ".."),
            lambda: service.get_notebook_file("../../secret"),
            lambda: service.get_co_writer_doc_root("../other-doc"),
            lambda: service.get_book_root("book/other"),
            lambda: service.get_book_page_file("bk_valid123", "../page"),
            lambda: service.get_question_batch_dir("batch\\escape"),
        ]

        for call in unsafe_calls:
            with pytest.raises(ValueError):
                call()


def test_path_service_uses_upstream_user_workspace(as_multi_user) -> None:
    with as_multi_user("u_alpha"):
        service = get_path_service()
        user_root = service.workspace_root / "user"

        assert service.get_user_root() == user_root
        assert service.get_chat_history_db() == user_root / "chat_history.db"
        assert service.get_memory_dir() == service.workspace_root / "memory"
        assert service.get_knowledge_bases_root() == service.workspace_root / "knowledge_bases"
        assert service.get_task_workspace("chat", "chat_20260507_abcd1234") == (
            user_root / "workspace" / "chat" / "chat" / "chat_20260507_abcd1234"
        )


def test_safe_resolve_under_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError):
        safe_resolve_under(root, "../outside")


def test_tutorbot_path_helpers_reject_unsafe_bot_ids(as_multi_user) -> None:
    with as_multi_user("u_alpha"):
        with pytest.raises(ValueError):
            tutorbot_paths.get_bot_dir("../other-user")


def test_tutorbot_manager_rejects_unsafe_bot_ids(tmp_path: Path) -> None:
    manager = TutorBotManager()
    manager._tutorbot_root = tmp_path / "tutorbot"  # type: ignore[attr-defined]

    with pytest.raises(ValueError):
        manager._bot_dir("../other-user")
