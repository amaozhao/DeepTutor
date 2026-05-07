from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.auth.context import user_scope
from deeptutor.services.path_service import PathService
from deeptutor.services.rag import factory as rag_factory
from deeptutor.services.rag.service import RAGService
from deeptutor.tools import rag_tool


def test_rag_service_defaults_to_current_user_knowledge_base_root(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
            rag = RAGService()

        assert Path(rag.kb_base_dir) == (
            tmp_path / "data" / "users" / "user_alpha" / "knowledge_bases"
        )
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


def test_rag_search_resolves_default_kb_from_current_user_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    class FakeRAGService:
        def __init__(self, kb_base_dir=None, provider=None):
            self.kb_base_dir = kb_base_dir or rag_tool.default_kb_base_dir()
            self.provider = provider

        async def search(self, *, query, kb_name, event_sink=None, **kwargs):
            return {
                "query": query,
                "kb_name": kb_name,
                "kb_base_dir": self.kb_base_dir,
            }

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"
        user_kb_root = tmp_path / "data" / "users" / "user_alpha" / "knowledge_bases"
        (user_kb_root / "alpha_kb" / "raw").mkdir(parents=True)
        (user_kb_root / "kb_config.json").write_text(
            '{"defaults":{"default_kb":"alpha_kb"},"knowledge_bases":{"alpha_kb":{"path":"alpha_kb"}}}',
            encoding="utf-8",
        )
        monkeypatch.setattr(rag_tool, "RAGService", FakeRAGService)

        with user_scope("user_alpha"):
            import asyncio

            result = asyncio.run(rag_tool.rag_search("what is private?"))

        assert result["kb_name"] == "alpha_kb"
        assert Path(result["kb_base_dir"]) == user_kb_root
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


def test_rag_search_rejects_unknown_kb_in_current_user_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    class FakeRAGService:
        def __init__(self, kb_base_dir=None, provider=None):
            self.kb_base_dir = kb_base_dir or rag_tool.default_kb_base_dir()
            self.provider = provider

        async def search(self, **_kwargs):
            return {"answer": "should not search missing kb"}

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"
        user_kb_root = tmp_path / "data" / "users" / "user_alpha" / "knowledge_bases"
        (user_kb_root / "alpha_kb" / "raw").mkdir(parents=True)
        (user_kb_root / "kb_config.json").write_text(
            '{"knowledge_bases":{"alpha_kb":{"path":"alpha_kb"}}}',
            encoding="utf-8",
        )
        monkeypatch.setattr(rag_tool, "RAGService", FakeRAGService)

        with user_scope("user_alpha"):
            import asyncio

            with pytest.raises(ValueError, match="Knowledge base .*not found"):
                asyncio.run(rag_tool.rag_search("what is private?", kb_name="missing_kb"))
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


def test_rag_search_rejects_traversal_kb_name(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    class FakeRAGService:
        def __init__(self, kb_base_dir=None, provider=None):
            self.kb_base_dir = kb_base_dir or rag_tool.default_kb_base_dir()
            self.provider = provider

        async def search(self, **_kwargs):
            return {"answer": "should not search traversal kb"}

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"
        user_kb_root = tmp_path / "data" / "users" / "user_alpha" / "knowledge_bases"
        (user_kb_root / "alpha_kb" / "raw").mkdir(parents=True)
        (user_kb_root / "kb_config.json").write_text(
            '{"knowledge_bases":{"alpha_kb":{"path":"alpha_kb"}}}',
            encoding="utf-8",
        )
        monkeypatch.setattr(rag_tool, "RAGService", FakeRAGService)

        with user_scope("user_alpha"):
            import asyncio

            with pytest.raises(ValueError, match="Knowledge base name"):
                asyncio.run(rag_tool.rag_search("what is private?", kb_name="../alpha_kb"))
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


@pytest.mark.asyncio
async def test_rag_service_rejects_traversal_before_pipeline_search(tmp_path: Path) -> None:
    called = False

    class FakePipeline:
        async def search(self, **_kwargs):
            nonlocal called
            called = True
            return {"answer": "should not call pipeline"}

    service = RAGService(kb_base_dir=str(tmp_path))
    service._pipeline = FakePipeline()

    with pytest.raises(ValueError, match="Knowledge base name"):
        await service.search(query="private?", kb_name="../outside")

    assert called is False


def test_rag_pipeline_cache_key_uses_current_user_root(tmp_path: Path, monkeypatch) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import pipeline as pipeline_module

    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir
    rag_factory._PIPELINE_CACHE.clear()

    class FakePipeline:
        def __init__(self, kb_base_dir=None, **_kwargs):
            self.kb_base_dir = kb_base_dir

    monkeypatch.setattr(pipeline_module, "LlamaIndexPipeline", FakePipeline)

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
            alpha = rag_factory.get_pipeline()

        with user_scope("user_beta"):
            beta = rag_factory.get_pipeline()

        assert alpha is not beta
        assert Path(alpha.kb_base_dir) == (
            tmp_path / "data" / "users" / "user_alpha" / "knowledge_bases"
        )
        assert Path(beta.kb_base_dir) == (
            tmp_path / "data" / "users" / "user_beta" / "knowledge_bases"
        )
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
        rag_factory._PIPELINE_CACHE.clear()
