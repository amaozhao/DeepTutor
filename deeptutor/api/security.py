"""Small HTTP security helpers for auth-enabled deployments."""

from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Iterable, Iterator, Mapping
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


class FileSlidingWindowRateLimiter:
    """File-backed sliding-window limiter for the single-node beta path.

    ponytail: this is shared across local worker processes through data/system;
    replace with Redis or the chosen external store for real multi-replica SaaS.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root
        self._fallback = SlidingWindowRateLimiter()

    @property
    def root(self) -> Path:
        if self._root is not None:
            return self._root
        from deeptutor.multi_user import paths

        paths.ensure_system_dirs()
        root = paths.SYSTEM_ROOT / "rate"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def allow(self, key: str, *, limit: int, window_seconds: int, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        if limit <= 0:
            return False
        path = self._path_for(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock(path):
                cutoff = current - window_seconds
                try:
                    hits = json.loads(path.read_text(encoding="utf-8"))
                except FileNotFoundError:
                    hits = []
                if not isinstance(hits, list):
                    hits = []
                bucket = [
                    float(item) for item in hits if isinstance(item, int | float) and item > cutoff
                ]
                if len(bucket) >= limit:
                    self._write(path, bucket)
                    return False
                bucket.append(current)
                self._write(path, bucket)
            return True
        except Exception:
            return self._fallback.allow(key, limit=limit, window_seconds=window_seconds, now=now)

    @contextmanager
    def _lock(self, path: Path) -> Iterator[None]:
        lock_path = path.with_suffix(".lock")
        handle = lock_path.open("a+", encoding="utf-8")
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def _write(self, path: Path, hits: list[float]) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(hits, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)

    def clear(self) -> None:
        self._fallback.clear()
        try:
            for child in self.root.glob("*.json"):
                child.unlink(missing_ok=True)
            for child in self.root.glob("*.tmp"):
                child.unlink(missing_ok=True)
            for child in self.root.glob("*.lock"):
                child.unlink(missing_ok=True)
        except Exception:
            pass


rate_limiter = FileSlidingWindowRateLimiter()

_WORKER_ENV_VARS = ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS")


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


def configured_worker_count(env: Mapping[str, str] | None = None) -> int:
    source = os.environ if env is None else env
    counts: list[int] = []
    for name in _WORKER_ENV_VARS:
        try:
            value = int(str(source.get(name, "")).strip() or "0")
        except ValueError:
            continue
        if value > 0:
            counts.append(value)
    return max(counts, default=1)


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
    worker_count = configured_worker_count()
    if worker_count > 1:
        warnings.append(
            f"{worker_count} backend workers configured, but auth and quota state are not "
            "multi-worker safe. Use one worker until external shared storage is added."
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
