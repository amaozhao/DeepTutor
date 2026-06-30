from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

from fastapi import HTTPException, UploadFile
import pytest

from deeptutor.api.routers import voice as voice_router
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.multi_user.grants import normalize_grant, save_grant
from deeptutor.multi_user.usage import (
    UsageQuotaExceeded,
    empty_quota,
    enforce_current_user_quota,
    record_usage,
    usage_summary,
)
from deeptutor.services.config.provider_runtime import ResolvedSearchConfig
from deeptutor.services.embedding.client import EmbeddingClient
from deeptutor.services.embedding.config import EmbeddingConfig
from deeptutor.services.search.types import WebSearchResponse
from deeptutor.services.session.turn_runtime import _event_usage_summary


class _FakeEmbeddingAdapter:
    def __init__(self, _config):
        self.calls = 0

    async def embed(self, request):
        self.calls += 1
        return type("Resp", (), {"embeddings": [[0.1, 0.2] for _ in request.texts]})()


class _FakeSearchProvider:
    name = "duckduckgo"
    supports_answer = True

    def search(self, query: str, **kwargs):
        return WebSearchResponse(query=query, answer="ok", provider=self.name)


def _embedding_config() -> EmbeddingConfig:
    return EmbeddingConfig(
        model="text-embedding-test",
        api_key="sk-test",
        base_url="https://example.test/v1/embeddings",
        effective_url="https://example.test/v1/embeddings",
        binding="openai",
        provider_name="openai",
        provider_mode="standard",
        dim=2,
        batch_size=2,
    )


def test_grant_normalization_adds_default_quota() -> None:
    grant = normalize_grant("u_alice", {"enabled_tools": ["reason"]})

    assert grant["quota"] == empty_quota()


def test_usage_ledger_aggregates_current_day_and_month(mu_isolated_root):
    record_usage(
        user_id="u_alice",
        username="alice",
        session_id="s1",
        turn_id="t1",
        capability="chat",
        provider="minimax",
        model="M3",
        summary={
            "prompt_tokens": 7,
            "completion_tokens": 11,
            "total_tokens": 18,
            "total_calls": 2,
            "total_cost_usd": 0.012345,
        },
    )

    summary = usage_summary("u_alice", now=datetime.now(timezone.utc))

    assert summary["today"]["total_tokens"] == 18
    assert summary["month"]["total_calls"] == 2
    assert summary["all"]["total_cost_usd"] == 0.012345


def test_quota_blocks_next_turn_when_limit_is_spent(seed_user, as_user):
    seed_user("admin", role="admin")
    user = seed_user("alice")
    user_id = str(user["id"])
    save_grant(user_id, {"quota": {"daily_call_limit": 1}})
    record_usage(
        user_id=user_id,
        username="alice",
        session_id="s1",
        turn_id="t1",
        capability="chat",
        provider="minimax",
        model="M3",
        summary={"total_calls": 1},
    )

    with as_user(user_id, username="alice"):
        with pytest.raises(UsageQuotaExceeded, match="daily call limit"):
            enforce_current_user_quota()


def test_turn_runtime_reads_cost_summary_from_result_event() -> None:
    event = StreamEvent(
        type=StreamEventType.RESULT,
        source="chat",
        metadata={"metadata": {"cost_summary": {"total_tokens": 42, "total_calls": 1}}},
    )

    assert _event_usage_summary(event) == {"total_tokens": 42, "total_calls": 1}


@pytest.mark.asyncio
async def test_voice_quota_blocks_before_provider_call(seed_user, as_user, monkeypatch) -> None:
    seed_user("admin", role="admin")
    user = seed_user("alice")
    user_id = str(user["id"])
    save_grant(user_id, {"quota": {"daily_call_limit": 1}})
    record_usage(
        user_id=user_id,
        username="alice",
        session_id="s1",
        turn_id="t1",
        capability="chat",
        provider="minimax",
        model="M3",
        summary={"total_calls": 1},
    )

    async def should_not_call(*args, **kwargs):  # pragma: no cover - failure path
        raise AssertionError("provider should not be called after quota is spent")

    monkeypatch.setattr(voice_router, "synthesize_speech", should_not_call)

    with as_user(user_id, username="alice"):
        with pytest.raises(HTTPException) as exc_info:
            await voice_router.text_to_speech(voice_router.TTSRequest(text="hi"))

    assert exc_info.value.status_code == 429
    assert "daily call limit" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_voice_success_records_tts_and_stt_calls(seed_user, as_user, monkeypatch) -> None:
    user = seed_user("alice")
    user_id = str(user["id"])

    async def fake_synth(*args, **kwargs):
        return b"audio", "audio/mpeg"

    async def fake_transcribe(*args, **kwargs):
        return "hello"

    monkeypatch.setattr(voice_router, "synthesize_speech", fake_synth)
    monkeypatch.setattr(voice_router, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(
        voice_router,
        "resolve_tts_runtime_config",
        lambda: SimpleNamespace(provider_name="minimax", model="speech-01"),
    )
    monkeypatch.setattr(
        voice_router,
        "resolve_stt_runtime_config",
        lambda: SimpleNamespace(provider_name="minimax", model="audio-01"),
    )

    with as_user(user_id, username="alice"):
        await voice_router.text_to_speech(voice_router.TTSRequest(text="hi"))
        await voice_router.speech_to_text(
            file=UploadFile(filename="clip.webm", file=BytesIO(b"audio")),
            language=None,
        )

    summary = usage_summary(user_id)
    assert summary["today"]["total_calls"] == 2


def test_web_search_quota_blocks_before_provider_call(seed_user, as_user, monkeypatch) -> None:
    from deeptutor.services import search as search_service

    seed_user("admin", role="admin")
    user = seed_user("alice")
    user_id = str(user["id"])
    save_grant(user_id, {"quota": {"daily_call_limit": 1}})
    record_usage(
        user_id=user_id,
        username="alice",
        session_id="s1",
        turn_id="t1",
        capability="chat",
        provider="minimax",
        model="M3",
        summary={"total_calls": 1},
    )
    monkeypatch.setattr(search_service, "_get_web_search_config", lambda: {"enabled": True})
    monkeypatch.setattr(
        search_service,
        "resolve_search_runtime_config",
        lambda: ResolvedSearchConfig(provider="duckduckgo", requested_provider="duckduckgo"),
    )
    monkeypatch.setattr(
        search_service,
        "get_provider",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider called")),
    )

    with as_user(user_id, username="alice"):
        with pytest.raises(UsageQuotaExceeded, match="daily call limit"):
            search_service.web_search("hello")


def test_web_search_success_records_usage(seed_user, as_user, monkeypatch) -> None:
    from deeptutor.services import search as search_service

    user = seed_user("alice")
    user_id = str(user["id"])
    monkeypatch.setattr(search_service, "_get_web_search_config", lambda: {"enabled": True})
    monkeypatch.setattr(
        search_service,
        "resolve_search_runtime_config",
        lambda: ResolvedSearchConfig(provider="duckduckgo", requested_provider="duckduckgo"),
    )
    monkeypatch.setattr(
        search_service, "get_provider", lambda *args, **kwargs: _FakeSearchProvider()
    )

    with as_user(user_id, username="alice"):
        result = search_service.web_search("hello")

    assert result["answer"] == "ok"
    assert usage_summary(user_id)["today"]["total_calls"] == 1


@pytest.mark.asyncio
async def test_embedding_quota_blocks_before_provider_call(seed_user, as_user, monkeypatch) -> None:
    from deeptutor.services.embedding import client as embedding_client

    seed_user("admin", role="admin")
    user = seed_user("alice")
    user_id = str(user["id"])
    save_grant(user_id, {"quota": {"daily_call_limit": 1}})
    record_usage(
        user_id=user_id,
        username="alice",
        session_id="s1",
        turn_id="t1",
        capability="chat",
        provider="minimax",
        model="M3",
        summary={"total_calls": 1},
    )
    monkeypatch.setattr(
        embedding_client, "_resolve_adapter_class", lambda _b: _FakeEmbeddingAdapter
    )
    client = EmbeddingClient(_embedding_config())

    with as_user(user_id, username="alice"):
        with pytest.raises(UsageQuotaExceeded, match="daily call limit"):
            await client.embed(["hello"])

    assert client.adapter.calls == 0


@pytest.mark.asyncio
async def test_embedding_success_records_usage(seed_user, as_user, monkeypatch) -> None:
    from deeptutor.services.embedding import client as embedding_client

    user = seed_user("alice")
    user_id = str(user["id"])
    monkeypatch.setattr(
        embedding_client, "_resolve_adapter_class", lambda _b: _FakeEmbeddingAdapter
    )
    client = EmbeddingClient(_embedding_config())

    with as_user(user_id, username="alice"):
        vectors = await client.embed(["a", "b", "c"])

    assert len(vectors) == 3
    assert usage_summary(user_id)["today"]["total_calls"] == 3
