from __future__ import annotations

from pathlib import Path

from deeptutor.auth.context import user_scope
from deeptutor.services.path_service import PathService
from deeptutor.services.session import (
    get_sqlite_session_store,
    get_turn_runtime_manager,
    reset_session_services,
)
from deeptutor.services.storage import get_attachment_store, reset_attachment_store


def test_session_runtime_and_attachment_stores_are_cached_per_user(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir
    reset_session_services()
    reset_attachment_store()

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
            store_alpha = get_sqlite_session_store()
            runtime_alpha = get_turn_runtime_manager()
            attachments_alpha = get_attachment_store()

        with user_scope("user_beta"):
            store_beta = get_sqlite_session_store()
            runtime_beta = get_turn_runtime_manager()
            attachments_beta = get_attachment_store()

        with user_scope("user_alpha"):
            assert get_sqlite_session_store() is store_alpha
            assert get_turn_runtime_manager() is runtime_alpha
            assert get_attachment_store() is attachments_alpha

        assert store_alpha is not store_beta
        assert runtime_alpha is not runtime_beta
        assert runtime_alpha.store is store_alpha
        assert runtime_beta.store is store_beta
        assert store_alpha.db_path == (
            tmp_path / "data" / "users" / "user_alpha" / "chat_history.db"
        )
        assert store_beta.db_path == tmp_path / "data" / "users" / "user_beta" / "chat_history.db"
        assert attachments_alpha.root == (
            tmp_path / "data" / "users" / "user_alpha" / "workspace" / "chat" / "attachments"
        )
        assert attachments_beta.root == (
            tmp_path / "data" / "users" / "user_beta" / "workspace" / "chat" / "attachments"
        )
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
        reset_session_services()
        reset_attachment_store()
