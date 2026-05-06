from __future__ import annotations

from pathlib import Path

from deeptutor.api.routers import knowledge as knowledge_router
from deeptutor.auth.context import user_scope
from deeptutor.services.path_service import PathService


def test_knowledge_manager_is_cached_per_user_base_dir(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir
    original_kb_base = knowledge_router._kb_base_dir
    knowledge_router._kb_managers.clear()

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"
        knowledge_router._kb_base_dir = tmp_path / "data" / "knowledge_bases"

        with user_scope("user_alpha"):
            alpha = knowledge_router.get_kb_manager()

        with user_scope("user_beta"):
            beta = knowledge_router.get_kb_manager()

        assert alpha is not beta
        assert alpha.base_dir == tmp_path / "data" / "users" / "user_alpha" / "knowledge_bases"
        assert beta.base_dir == tmp_path / "data" / "users" / "user_beta" / "knowledge_bases"
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
        knowledge_router._kb_base_dir = original_kb_base
        knowledge_router._kb_managers.clear()
