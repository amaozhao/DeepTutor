"""Shared LLM provider fallback decisions."""

from __future__ import annotations

_CAPABILITY_ERROR_STATUS_CODES = {400, 404, 422}
_RESPONSE_FORMAT_NEEDLES = (
    "response_format",
    "response format",
)
_RESPONSE_FORMAT_UNSUPPORTED_NEEDLES = (
    "json_object",
    "json_schema",
    "must be",
    "not supported",
    "not valid",
    "unsupported",
)
_RESPONSES_API_NEEDLES = (
    "responses",
    "response api",
    "max_output_tokens",
    "instructions",
    "previous_response",
    "unknown parameter",
    "unrecognized request argument",
    "unsupported",
    "not supported",
)


def provider_status_code(error: object) -> int | None:
    """Extract a provider HTTP status code from SDK or internal exceptions."""
    status_code = getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    try:
        return int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        return None


def provider_error_text(error: object) -> str:
    """Return lowercase searchable provider error text."""
    if isinstance(error, str):
        return error.lower()

    parts: list[str] = []
    for attr in ("body", "doc", "message"):
        value = getattr(error, attr, None)
        if value is not None:
            parts.append(str(value))
    response = getattr(error, "response", None)
    if response is not None:
        value = getattr(response, "text", None)
        if value is not None and not callable(value):
            parts.append(str(value))
    parts.append(str(error))
    return " ".join(parts).lower()


def _is_capability_error(status_code: int | None) -> bool:
    return status_code is None or status_code in _CAPABILITY_ERROR_STATUS_CODES


def is_unsupported_response_format(error: object) -> bool:
    """Detect provider errors where response_format should be dropped and retried."""
    text = provider_error_text(error)
    if not any(needle in text for needle in _RESPONSE_FORMAT_NEEDLES):
        return False
    if not any(needle in text for needle in _RESPONSE_FORMAT_UNSUPPORTED_NEEDLES):
        return False
    return _is_capability_error(provider_status_code(error))


def should_fallback_from_responses_error(error: object) -> bool:
    """Detect Responses API capability errors that may use Chat Completions."""
    if not _is_capability_error(provider_status_code(error)):
        return False
    text = provider_error_text(error)
    return any(needle in text for needle in _RESPONSES_API_NEEDLES)
