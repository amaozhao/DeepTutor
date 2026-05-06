from __future__ import annotations

from pathlib import Path

from deeptutor.auth.context import user_scope
from deeptutor.services.memory.service import get_memory_service, reset_memory_services
from deeptutor.services.path_service import PathService


def test_memory_service_is_cached_per_user_memory_dir(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir
    reset_memory_services()

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
            alpha = get_memory_service()
            alpha.write_file("profile", "## Preferences\nAlpha")

        with user_scope("user_beta"):
            beta = get_memory_service()
            beta.write_file("profile", "## Preferences\nBeta")

        with user_scope("user_alpha"):
            assert get_memory_service() is alpha
            assert get_memory_service().read_profile() == "## Preferences\nAlpha"

        with user_scope("user_beta"):
            assert get_memory_service() is beta
            assert get_memory_service().read_profile() == "## Preferences\nBeta"

        assert alpha is not beta
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
        reset_memory_services()
