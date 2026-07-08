"""DISABLE_SSL_VERIFY coverage for the OpenAI Codex Responses provider."""

from __future__ import annotations

from typing import Any

import pytest

from deeptutor.services.llm import openai_http_client
from deeptutor.services.llm.provider_core import openai_codex_provider


@pytest.fixture(autouse=True)
def _clean_ssl_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISABLE_SSL_VERIFY", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setattr(openai_http_client, "_warning_logged", False)


def _stub_token_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Token:
        access = "test-token"
        account_id = "test-account"

    async def _fake_load_token(self: Any) -> _Token:
        return _Token()

    monkeypatch.setattr(openai_codex_provider.OpenAICodexProvider, "_load_token", _fake_load_token)


@pytest.mark.asyncio
async def test_codex_first_attempt_verify_true_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_token_loader(monkeypatch)
    captured: list[dict[str, Any]] = []

    async def fake_request(*args: Any, **kwargs: Any) -> tuple[str, list[Any], str]:
        captured.append(kwargs)
        return ("ok", [], "stop")

    monkeypatch.setattr(openai_codex_provider, "_request_codex", fake_request)

    provider = openai_codex_provider.OpenAICodexProvider()
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.content == "ok"
    assert captured[0]["verify"] is True


@pytest.mark.asyncio
async def test_codex_first_attempt_verify_false_when_flag_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISABLE_SSL_VERIFY", "1")
    _stub_token_loader(monkeypatch)
    captured: list[dict[str, Any]] = []

    async def fake_request(*args: Any, **kwargs: Any) -> tuple[str, list[Any], str]:
        captured.append(kwargs)
        return ("ok", [], "stop")

    monkeypatch.setattr(openai_codex_provider, "_request_codex", fake_request)

    provider = openai_codex_provider.OpenAICodexProvider()
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.content == "ok"
    assert captured[0]["verify"] is False


@pytest.mark.asyncio
async def test_codex_cert_failure_does_not_disable_ssl_without_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SSL verification is disabled only through DISABLE_SSL_VERIFY."""
    _stub_token_loader(monkeypatch)
    captured: list[dict[str, Any]] = []

    async def fake_request(*args: Any, **kwargs: Any) -> tuple[str, list[Any], str]:
        captured.append(kwargs)
        raise RuntimeError("[SSL: CERTIFICATE_VERIFY_FAILED] cert chain")

    monkeypatch.setattr(openai_codex_provider, "_request_codex", fake_request)

    provider = openai_codex_provider.OpenAICodexProvider()
    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.finish_reason == "error"
    assert "CERTIFICATE_VERIFY_FAILED" in (result.content or "")
    assert len(captured) == 1
    assert captured[0]["verify"] is True
