from __future__ import annotations

from pathlib import Path

from deeptutor.auth.context import user_scope
from deeptutor.services.path_service import PathService


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
