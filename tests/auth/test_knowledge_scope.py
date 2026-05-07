from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.api.routers import knowledge as knowledge_router
from deeptutor.auth.context import user_scope
from deeptutor.knowledge.manager import KnowledgeBaseManager
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


def test_authenticated_user_cannot_link_folder_outside_private_root(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"
        user_kb_root = tmp_path / "data" / "users" / "user_alpha" / "knowledge_bases"
        (user_kb_root / "kb1").mkdir(parents=True)
        (user_kb_root / "kb_config.json").write_text(
            '{"knowledge_bases":{"kb1":{"path":"kb1"}}}', encoding="utf-8"
        )
        outside = tmp_path / "shared"
        outside.mkdir()
        (outside / "doc.txt").write_text("not private", encoding="utf-8")

        manager = KnowledgeBaseManager(base_dir=user_kb_root)

        with user_scope("user_alpha"):
            with pytest.raises(ValueError, match="private user root"):
                manager.link_folder("kb1", str(outside))
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


def test_authenticated_user_can_link_folder_under_private_root(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"
        user_root = tmp_path / "data" / "users" / "user_alpha"
        user_kb_root = user_root / "knowledge_bases"
        (user_kb_root / "kb1").mkdir(parents=True)
        (user_kb_root / "kb_config.json").write_text(
            '{"knowledge_bases":{"kb1":{"path":"kb1"}}}', encoding="utf-8"
        )
        private_docs = user_root / "workspace" / "docs"
        private_docs.mkdir(parents=True)
        (private_docs / "doc.txt").write_text("private", encoding="utf-8")

        manager = KnowledgeBaseManager(base_dir=user_kb_root)

        with user_scope("user_alpha"):
            linked = manager.link_folder("kb1", str(private_docs))

        assert linked["path"] == str(private_docs.resolve())
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
