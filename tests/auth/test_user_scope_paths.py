from __future__ import annotations

from pathlib import Path

from deeptutor.auth.context import user_scope
from deeptutor.services.path_service import PathService


def test_path_service_rejects_unsafe_resource_ids(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
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
                try:
                    call()
                except ValueError:
                    continue
                raise AssertionError("unsafe resource id was accepted")
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


def test_path_service_keeps_valid_generated_resource_ids(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
            assert service.get_task_workspace("chat", "chat_20260507_abcd1234") == (
                tmp_path
                / "data"
                / "users"
                / "user_alpha"
                / "workspace"
                / "chat"
                / "chat"
                / "chat_20260507_abcd1234"
            )
            assert service.get_notebook_file("a1b2c3d4").name == "a1b2c3d4.json"
            assert service.get_co_writer_doc_root("9f0e1d2c3b4a").name == "doc_9f0e1d2c3b4a"
            assert service.get_book_page_file("bk_123456abcd", "pg_123456abcd").name == (
                "pg_123456abcd.json"
            )
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


def test_path_service_uses_user_root_inside_user_scope(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        assert service.get_user_root() == tmp_path / "data" / "user"
        assert service.get_system_settings_file("model_catalog") == (
            tmp_path / "data" / "system" / "settings" / "model_catalog.json"
        )

        with user_scope("user_alpha"):
            assert service.get_user_root() == tmp_path / "data" / "users" / "user_alpha"
            assert service.get_chat_history_db() == (
                tmp_path / "data" / "users" / "user_alpha" / "chat_history.db"
            )
            assert service.get_memory_dir() == (
                tmp_path / "data" / "users" / "user_alpha" / "workspace" / "memory"
            )
            assert service.get_system_settings_file("model_catalog") == (
                tmp_path / "data" / "system" / "settings" / "model_catalog.json"
            )

        with user_scope("user_beta"):
            assert service.get_user_root() == tmp_path / "data" / "users" / "user_beta"
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
