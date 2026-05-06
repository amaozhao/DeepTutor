from __future__ import annotations

from pathlib import Path

from deeptutor.auth.context import user_scope
from deeptutor.services.path_service import PathService
from deeptutor.services.tutorbot import get_tutorbot_manager, reset_tutorbot_managers


def test_tutorbot_manager_is_cached_per_user_root(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir
    reset_tutorbot_managers()

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
            alpha = get_tutorbot_manager()

        with user_scope("user_beta"):
            beta = get_tutorbot_manager()

        assert alpha is not beta
        assert alpha._tutorbot_dir == (
            tmp_path / "data" / "users" / "user_alpha" / "workspace" / "tutorbot"
        )
        assert beta._tutorbot_dir == (
            tmp_path / "data" / "users" / "user_beta" / "workspace" / "tutorbot"
        )
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
        reset_tutorbot_managers()
