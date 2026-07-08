"""Tests for OpenAI SDK HTTP client options shared across providers."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.services.llm import openai_http_client
from deeptutor.services.llm.exceptions import LLMConfigError


@pytest.fixture(autouse=True)
def _clean_ssl_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISABLE_SSL_VERIFY", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setattr(openai_http_client, "_warning_logged", False)


def _enable_ssl_override(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    clients: list[Any] = []

    class HTTPClientStub:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            clients.append(self)

    monkeypatch.setenv("DISABLE_SSL_VERIFY", "1")
    monkeypatch.setattr(openai_http_client.httpx, "AsyncClient", HTTPClientStub)
    return clients


def _capture_async_openai(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    class AsyncOpenAIStub:
        def __init__(self, **kwargs: Any) -> None:
            captured.append(kwargs)

    monkeypatch.setattr(module, "AsyncOpenAI", AsyncOpenAIStub)
    return captured


def test_openai_client_kwargs_disable_ssl_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    clients = _enable_ssl_override(monkeypatch)

    kwargs = openai_http_client.openai_client_kwargs(timeout=60)

    assert kwargs["http_client"] is clients[0]
    assert clients[0].kwargs == {"verify": False, "timeout": 60}


def test_openai_client_kwargs_rejects_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISABLE_SSL_VERIFY", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(LLMConfigError, match="not allowed in production"):
        openai_http_client.openai_client_kwargs()


def test_provider_core_passes_disable_ssl_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    provider_mod = __import__(
        "deeptutor.services.llm.provider_core", fromlist=["openai_compat_provider"]
    ).openai_compat_provider

    clients = _enable_ssl_override(monkeypatch)
    captured = _capture_async_openai(monkeypatch, provider_mod)

    provider_mod.OpenAICompatProvider(api_key="sk-test", api_base="https://example.com/v1")

    assert captured[0]["http_client"] is clients[0]
    assert clients[0].kwargs["verify"] is False


def test_provider_core_does_not_write_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    provider_mod = __import__(
        "deeptutor.services.llm.provider_core", fromlist=["openai_compat_provider"]
    ).openai_compat_provider
    find_by_name = __import__(
        "deeptutor.services.provider_registry", fromlist=["find_by_name"]
    ).find_by_name

    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "external-openai-key")
    _capture_async_openai(monkeypatch, provider_mod)

    provider_mod.OpenAICompatProvider(
        api_key="minimax-key",
        api_base="https://api.minimax.io/v1",
        spec=find_by_name("minimax"),
    )

    assert "MINIMAX_API_KEY" not in os.environ
    assert os.environ["OPENAI_API_KEY"] == "external-openai-key"


def test_azure_provider_passes_disable_ssl_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    azure_mod = __import__(
        "deeptutor.services.llm.provider_core", fromlist=["azure_openai_provider"]
    ).azure_openai_provider

    clients = _enable_ssl_override(monkeypatch)
    captured = _capture_async_openai(monkeypatch, azure_mod)

    azure_mod.AzureOpenAIProvider(
        api_key="sk-test",
        api_base="https://example.openai.azure.com",
        default_model="gpt-test",
    )

    assert captured[0]["http_client"] is clients[0]
    assert clients[0].kwargs["verify"] is False


def test_agentic_client_passes_disable_ssl_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    agentic_client = __import__("deeptutor.core.agentic", fromlist=["client"]).client

    clients = _enable_ssl_override(monkeypatch)
    captured = _capture_async_openai(monkeypatch, agentic_client)

    agentic_client.build_openai_client(
        agentic_client.LLMClientConfig(
            binding="openai",
            model="gpt-test",
            api_key="sk-test",
            base_url="https://example.com/v1",
        )
    )

    assert captured[0]["http_client"] is clients[0]
    assert clients[0].kwargs["verify"] is False


def test_legacy_openai_provider_rejects_disable_ssl_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    LLMConfig = __import__("deeptutor.services.llm.config", fromlist=["LLMConfig"]).LLMConfig
    OpenAIProvider = __import__(
        "deeptutor.services.llm.providers.open_ai", fromlist=["OpenAIProvider"]
    ).OpenAIProvider

    monkeypatch.setenv("DISABLE_SSL_VERIFY", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(LLMConfigError, match="not allowed in production"):
        OpenAIProvider(LLMConfig(model="gpt-test", api_key="sk-test"))


@pytest.mark.asyncio
async def test_sdk_complete_passes_disable_ssl_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executors = __import__("deeptutor.services.llm", fromlist=["executors"]).executors

    clients = _enable_ssl_override(monkeypatch)
    captured = _capture_async_openai(monkeypatch, executors)

    async def fake_create_with_format_fallback(*_args: Any, **_kwargs: Any) -> Any:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        )

    monkeypatch.setattr(executors, "_create_with_format_fallback", fake_create_with_format_fallback)

    result = await executors.sdk_complete(
        prompt="hi",
        system_prompt="system",
        provider_name="openai",
        model="gpt-test",
        api_key="sk-test",
        base_url="https://example.com/v1",
    )

    assert result == "ok"
    assert captured[0]["http_client"] is clients[0]
    assert clients[0].kwargs["verify"] is False


@pytest.mark.asyncio
async def test_sdk_complete_does_not_write_provider_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executors = __import__("deeptutor.services.llm", fromlist=["executors"]).executors

    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "external-openai-key")
    captured = _capture_async_openai(monkeypatch, executors)

    async def fake_create_with_format_fallback(*_args: Any, **_kwargs: Any) -> Any:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        )

    monkeypatch.setattr(executors, "_create_with_format_fallback", fake_create_with_format_fallback)

    result = await executors.sdk_complete(
        prompt="hi",
        system_prompt="system",
        provider_name="minimax",
        model="MiniMax-M1",
        api_key="minimax-key",
        base_url="https://api.minimax.io/v1",
    )

    assert result == "ok"
    assert captured[0]["api_key"] == "minimax-key"
    assert captured[0]["base_url"] == "https://api.minimax.io/v1"
    assert "MINIMAX_API_KEY" not in os.environ
    assert os.environ["OPENAI_API_KEY"] == "external-openai-key"


@pytest.mark.asyncio
async def test_sdk_stream_passes_disable_ssl_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executors = __import__("deeptutor.services.llm", fromlist=["executors"]).executors

    clients = _enable_ssl_override(monkeypatch)
    captured = _capture_async_openai(monkeypatch, executors)

    class StreamStub:
        def __init__(self) -> None:
            self._chunks = [
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="hi"))],
                )
            ]

        def __aiter__(self) -> "StreamStub":
            return self

        async def __anext__(self) -> Any:
            if not self._chunks:
                raise StopAsyncIteration
            return self._chunks.pop(0)

    async def fake_create_with_format_fallback(*_args: Any, **_kwargs: Any) -> StreamStub:
        return StreamStub()

    monkeypatch.setattr(executors, "_create_with_format_fallback", fake_create_with_format_fallback)

    chunks = [
        chunk
        async for chunk in executors.sdk_stream(
            prompt="hi",
            system_prompt="system",
            provider_name="openai",
            model="gpt-test",
            api_key="sk-test",
            base_url="https://example.com/v1",
        )
    ]

    assert chunks == ["hi"]
    assert captured[0]["http_client"] is clients[0]
    assert clients[0].kwargs["verify"] is False


def test_embedding_sdk_passes_disable_ssl_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedding_mod = __import__(
        "deeptutor.services.embedding.adapters", fromlist=["openai_sdk"]
    ).openai_sdk

    clients = _enable_ssl_override(monkeypatch)
    captured = _capture_async_openai(monkeypatch, embedding_mod)

    adapter = embedding_mod.OpenAISDKEmbeddingAdapter(
        {
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "text-embedding-3-large",
            "request_timeout": 30,
        }
    )
    adapter._build_client()

    assert captured[0]["http_client"] is clients[0]
    assert clients[0].kwargs == {"verify": False, "timeout": 60}
