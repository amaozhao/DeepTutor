"""
Root conftest — shared fixtures for the entire test suite.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from deeptutor.auth.dependencies import SESSION_COOKIE
from deeptutor.auth.models import AuthUser
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import Attachment, UnifiedContext
from deeptutor.core.stream_bus import StreamBus

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
        loop = asyncio.get_event_loop()
        if not loop.is_running() and not loop.is_closed():
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


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_user() -> AuthUser:
    """Default authenticated user for API/router tests."""
    return AuthUser(
        id="test_user",
        email="test@example.com",
        password_hash="hash",
        display_name="Test User",
        created_at=1.0,
        updated_at=1.0,
        role="admin",
    )


@pytest.fixture
def auth_cookie(monkeypatch: pytest.MonkeyPatch, auth_user: AuthUser) -> dict[str, str]:
    """Cookie that satisfies auth dependencies without touching the real auth DB."""
    token = "test-session-token"
    monkeypatch.setattr(
        "deeptutor.auth.dependencies.get_auth_store",
        lambda: type(
            "FakeAuthStore",
            (),
            {"get_user_by_session_token": lambda self, value: auth_user if value == token else None},
        )(),
    )
    return {SESSION_COOKIE: token}
