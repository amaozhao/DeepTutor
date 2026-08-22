"""Tests for LLM error mapping helpers."""

from datetime import datetime, timezone

from deeptutor.services.llm.error_mapping import map_error, retry_after_seconds
from deeptutor.services.llm.exceptions import (
    LLMAPIError,
    LLMAuthenticationError,
    LLMModelNotFoundError,
    LLMNetworkError,
    LLMProviderTransportError,
    LLMRateLimitError,
    LLMTimeoutError,
    ProviderContextWindowError,
)
from deeptutor.services.llm.fallback import (
    is_unsupported_response_format,
    should_fallback_from_responses_error,
)


class DummyError(Exception):
    """Custom error used for mapping tests."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_map_error_status_code_auth() -> None:
    """401 errors should map to authentication failures."""
    mapped = map_error(DummyError("auth failed", status_code=401), provider="openai")
    assert isinstance(mapped, LLMAuthenticationError)


def test_map_error_status_code_rate_limit() -> None:
    """429 errors should map to rate limit failures."""
    mapped = map_error(DummyError("rate limited", status_code=429), provider="openai")
    assert isinstance(mapped, LLMRateLimitError)


def test_map_error_status_code_model_not_found() -> None:
    """404 errors should map to model-not-found failures."""
    mapped = map_error(DummyError("model missing", status_code=404), provider="openai")
    assert isinstance(mapped, LLMModelNotFoundError)


def test_map_error_status_code_timeout() -> None:
    """Timeout status codes should map to timeout failures."""
    mapped = map_error(DummyError("gateway timeout", status_code=504), provider="openai")
    assert isinstance(mapped, LLMTimeoutError)


def test_map_error_connection_error() -> None:
    """Network failures should map separately from HTTP API responses."""
    mapped = map_error(ConnectionError("connection refused"), provider="openai")
    assert isinstance(mapped, LLMNetworkError)


def test_map_error_preserves_retry_after_header() -> None:
    error = DummyError("rate limited", status_code=429)
    error.response = type(
        "Response",
        (),
        {"headers": {"Retry-After": "12.5"}},
    )()

    mapped = map_error(error, provider="openai")

    assert isinstance(mapped, LLMRateLimitError)
    assert mapped.retry_after == 12.5


def test_retry_after_seconds_parses_http_date() -> None:
    error = DummyError("temporarily unavailable", status_code=503)
    error.response = type(
        "Response",
        (),
        {"headers": {"Retry-After": "Wed, 21 Oct 2015 07:28:10 GMT"}},
    )()

    delay = retry_after_seconds(
        error,
        now=datetime(2015, 10, 21, 7, 28, tzinfo=timezone.utc),
    )

    assert delay == 10.0


def test_map_error_message_context_window() -> None:
    """Context length errors should map to the provider context window error."""
    mapped = map_error(DummyError("maximum context length exceeded"), provider="openai")
    assert isinstance(mapped, ProviderContextWindowError)


def test_map_error_falls_back_to_api_error() -> None:
    """Unknown errors should fall back to generic API error mapping."""
    mapped = map_error(DummyError("boom", status_code=500), provider="openai")
    assert isinstance(mapped, LLMAPIError)
    assert mapped.status_code == 500


def test_response_format_fallback_accepts_capability_error() -> None:
    """Unsupported response_format errors may drop response_format and retry."""
    error = DummyError(
        "response_format.type json_object is not supported by this model",
        status_code=400,
    )

    assert is_unsupported_response_format(error)


def test_response_format_fallback_rejects_auth_and_rate_limit() -> None:
    """Auth/rate errors must not be hidden by capability fallback."""
    auth_error = DummyError("response_format rejected because key is invalid", status_code=401)
    rate_error = DummyError("response_format temporarily rate limited", status_code=429)

    assert not is_unsupported_response_format(auth_error)
    assert not is_unsupported_response_format(rate_error)


def test_responses_api_fallback_is_status_gated() -> None:
    """Responses API fallback is only for capability-shaped provider errors."""
    assert should_fallback_from_responses_error(
        DummyError("unknown parameter: max_output_tokens", status_code=400)
    )
    assert not should_fallback_from_responses_error(
        DummyError("unknown parameter: max_output_tokens", status_code=401)
    )


def test_map_error_preserves_structured_transport_error() -> None:
    error = LLMProviderTransportError("provider connection failed")

    mapped = map_error(error, provider="openai_codex")

    assert mapped is error
    assert mapped.provider == "openai_codex"
