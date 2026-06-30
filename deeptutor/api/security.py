"""Small HTTP security helpers for auth-enabled deployments."""

from __future__ import annotations

from collections import defaultdict, deque
import time
from typing import Any, Iterable
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status

from deeptutor.services.config import (
    load_auth_settings,
    load_integrations_settings,
    load_system_settings,
)
from deeptutor.services.config.origins import normalize_origins


class SlidingWindowRateLimiter:
    """In-process sliding-window limiter.

    ponytail: single-process memory is enough for the current single-worker
    beta path; move buckets to Redis/shared storage before multi-replica SaaS.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window_seconds: int, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        bucket = self._hits[key]
        cutoff = current - window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(current)
        return True

    def clear(self) -> None:
        self._hits.clear()


rate_limiter = SlidingWindowRateLimiter()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def websocket_ip(ws: Any) -> str:
    forwarded = ws.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or "unknown"
    return ws.client.host if ws.client else "unknown"


def require_rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    if not rate_limiter.allow(key, limit=limit, window_seconds=window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
        )


def _origin(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_localhost_origin(origin: str) -> bool:
    host = urlparse(origin).hostname or ""
    return host in {"localhost", "127.0.0.1", "::1"}


def production_security_warnings() -> list[str]:
    """Return explicit operator warnings for auth-enabled public deployments."""
    auth_settings = load_auth_settings()
    if not auth_settings["enabled"]:
        return []
    system_settings = load_system_settings()
    explicit_origins = normalize_origins(
        [system_settings["cors_origin"], system_settings["cors_origins"]]
    )
    warnings: list[str] = []
    if not auth_settings["cookie_secure"]:
        warnings.append("auth.cookie_secure=false; enable secure cookies before HTTPS SaaS use.")
    if not any(not _is_localhost_origin(origin) for origin in explicit_origins):
        warnings.append(
            "No non-localhost CORS origin is configured for an auth-enabled deployment."
        )
    if auth_settings.get("public_registration_enabled") and not auth_settings.get(
        "require_terms_acceptance"
    ):
        warnings.append("Public registration is enabled without required terms acceptance.")
    if load_integrations_settings().get("pocketbase_url"):
        warnings.append(
            "PocketBase is single-user only in DeepTutor; keep integrations.pocketbase_url "
            "blank for multi-user/SaaS deployments."
        )
    return warnings


def require_trusted_origin(
    request: Request,
    *,
    allowed_origins: Iterable[str],
    enabled: bool,
) -> None:
    """Reject cross-site unsafe requests when cookie auth is in play.

    Requests without Origin/Referer are allowed for CLI/native clients. Browser
    cross-site writes include Origin; Referer is a fallback for older flows.
    """
    if not enabled or request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return
    supplied = request.headers.get("origin") or request.headers.get("referer") or ""
    if not supplied:
        return
    origin = _origin(supplied)
    if origin and origin in set(allowed_origins):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Untrusted request origin.",
    )


def reset_security_state() -> None:
    rate_limiter.clear()
