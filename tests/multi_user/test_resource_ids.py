from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.multi_user.resource_ids import safe_resolve_under
from deeptutor.partners.config import paths as partner_paths
from deeptutor.services.path_service import get_path_service
from deeptutor.services.partners.manager import PartnerManager


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


def test_partner_path_helpers_reject_unsafe_partner_ids(as_multi_user) -> None:
    with as_multi_user("u_alpha"):
        with pytest.raises(ValueError):
            partner_paths.get_partner_dir("../other-user")


def test_partner_manager_rejects_unsafe_partner_ids() -> None:
    manager = PartnerManager()

    with pytest.raises(ValueError):
        manager._partner_dir("../other-user")
