from __future__ import annotations

from pathlib import Path

from deeptutor.api.routers import settings as settings_router
from deeptutor.auth.context import user_scope
from deeptutor.services.path_service import PathService


def test_ui_settings_are_user_scoped(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
            settings_router.save_ui_settings({"theme": "dark", "language": "en"})

        with user_scope("user_beta"):
            settings_router.save_ui_settings({"theme": "snow", "language": "zh"})

        assert (
            tmp_path / "data" / "users" / "user_alpha" / "settings" / "interface.json"
        ).exists()
        assert (
            tmp_path / "data" / "users" / "user_beta" / "settings" / "interface.json"
        ).exists()

        with user_scope("user_alpha"):
            assert settings_router.load_ui_settings()["theme"] == "dark"

        with user_scope("user_beta"):
            assert settings_router.load_ui_settings()["theme"] == "snow"
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
