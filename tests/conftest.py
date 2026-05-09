"""
Root conftest — shared fixtures for the entire test suite.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager, suppress
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import Attachment, UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.multi_user.context import reset_current_user, set_current_user
from deeptutor.multi_user.models import CurrentUser, UserScope
from deeptutor.services.path_service import PathService

# ---------------------------------------------------------------------------
# StreamBus
# ---------------------------------------------------------------------------


@pytest.fixture
def stream_bus() -> StreamBus:
    """Fresh StreamBus for one test."""
    return StreamBus()


@pytest.fixture(autouse=True)
def close_stale_event_loop():
    """Close default loops that pytest-asyncio may create for sync tests."""
    yield
    with suppress(RuntimeError):
        policy = asyncio.get_event_loop_policy()
        loop = getattr(getattr(policy, "_local", None), "_loop", None)
        if loop is not None and not loop.is_running() and not loop.is_closed():
            loop.close()
        asyncio.set_event_loop(None)


# ---------------------------------------------------------------------------
# UnifiedContext
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_context() -> UnifiedContext:
    """Context with just a user message."""
    return UnifiedContext(
        session_id="test-session",
        user_message="Hello",
        language="en",
    )


@pytest.fixture
def rich_context() -> UnifiedContext:
    """Context with attachments, tools, KB, and metadata."""
    return UnifiedContext(
        session_id="test-session",
        user_message="Explain RAG",
        conversation_history=[
            {"role": "user", "content": "What is AI?"},
            {"role": "assistant", "content": "AI is..."},
        ],
        enabled_tools=["rag", "web_search"],
        active_capability="deep_solve",
        knowledge_bases=["my-kb"],
        attachments=[Attachment(type="image", url="https://img.png")],
        config_overrides={"temperature": 0.7},
        language="en",
        metadata={"turn_id": "t-1"},
    )


# ---------------------------------------------------------------------------
# SQLiteSessionStore (in-memory / tmp)
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Temporary database file path."""
    return tmp_path / "test_chat.db"


@pytest.fixture
def sqlite_store(tmp_db_path: Path):
    """SQLiteSessionStore backed by a temp file."""
    from deeptutor.services.session.sqlite_store import SQLiteSessionStore

    return SQLiteSessionStore(db_path=tmp_db_path)


@pytest.fixture
def as_multi_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Run code with an upstream ``multi_user`` CurrentUser under ``tmp_path``."""
    from deeptutor.multi_user import paths

    multi_user_root = tmp_path / "multi-user"
    monkeypatch.setattr(paths, "MULTI_USER_ROOT", multi_user_root)
    monkeypatch.setattr(paths, "ADMIN_WORKSPACE_ROOT", tmp_path / "data")
    monkeypatch.setattr(paths, "_path_services", {})
    PathService.reset_instance()

    @contextmanager
    def _scope(uid: str, *, role: str = "user", username: str | None = None):
        if role == "admin":
            scope = paths.admin_scope()
        else:
            scope = UserScope(
                kind="user",
                user_id=uid,
                root=(multi_user_root / uid).resolve(),
            )
        token = set_current_user(
            CurrentUser(
                id=uid,
                username=username or uid,
                role=role,  # type: ignore[arg-type]
                scope=scope,
            )
        )
        try:
            yield
        finally:
            reset_current_user(token)

    return _scope


# ---------------------------------------------------------------------------
# Fake / stub capability
# ---------------------------------------------------------------------------


class _StubCapability(BaseCapability):
    """Capability that emits one content event and returns."""

    manifest = CapabilityManifest(
        name="stub",
        description="Stub for testing.",
        stages=["responding"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        await stream.content("stub response", source=self.name)


@pytest.fixture
def stub_capability() -> _StubCapability:
    return _StubCapability()


# ---------------------------------------------------------------------------
# Fake LLM helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_llm_config() -> MagicMock:
    """MagicMock mimicking LLMConfig with common defaults."""
    cfg = MagicMock()
    cfg.model = "gpt-4o-mini"
    cfg.max_tokens = 4096
    cfg.temperature = 0.7
    cfg.api_key = "sk-test"
    cfg.api_base = "https://api.openai.com/v1"
    return cfg
