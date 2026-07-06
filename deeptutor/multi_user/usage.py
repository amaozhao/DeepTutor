"""Tiny file-backed LLM usage ledger and quota checks."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import threading
from typing import Any

from . import paths
from .context import get_current_user

_LOCK = threading.Lock()

QUOTA_KEYS = (
    "daily_token_limit",
    "monthly_token_limit",
    "daily_call_limit",
    "monthly_call_limit",
    "daily_cost_limit_usd",
    "monthly_cost_limit_usd",
)


class UsageQuotaExceeded(RuntimeError):
    """Raised before a turn starts when the user's quota is already spent."""


def empty_quota() -> dict[str, int | float]:
    return {
        "daily_token_limit": 0,
        "monthly_token_limit": 0,
        "daily_call_limit": 0,
        "monthly_call_limit": 0,
        "daily_cost_limit_usd": 0.0,
        "monthly_cost_limit_usd": 0.0,
    }


def normalize_quota(value: Any) -> dict[str, int | float]:
    quota = empty_quota()
    if not isinstance(value, dict):
        return quota
    for key in QUOTA_KEYS:
        raw = value.get(key, 0)
        try:
            number = float(raw)
        except (TypeError, ValueError):
            number = 0
        if number < 0:
            number = 0
        quota[key] = round(number, 6) if key.endswith("_usd") else int(number)
    return quota


def normalize_usage_summary(value: Any) -> dict[str, int | float]:
    summary = value if isinstance(value, dict) else {}

    def as_int(key: str) -> int:
        try:
            return max(0, int(summary.get(key) or 0))
        except (TypeError, ValueError):
            return 0

    def as_float(key: str) -> float:
        try:
            return max(0.0, float(summary.get(key) or 0.0))
        except (TypeError, ValueError):
            return 0.0

    prompt_tokens = as_int("prompt_tokens")
    completion_tokens = as_int("completion_tokens")
    total_tokens = as_int("total_tokens") or prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "total_calls": as_int("total_calls"),
        "total_cost_usd": round(as_float("total_cost_usd"), 8),
    }


def _usage_file():
    paths.ensure_system_dirs()
    root = paths.SYSTEM_ROOT / "usage"
    root.mkdir(parents=True, exist_ok=True)
    return root / "llm_usage.jsonl"


@contextmanager
def usage_ledger_lock() -> Iterator[None]:
    """Lock the usage ledger across local worker processes."""
    target = _usage_file()
    lock_path = target.with_suffix(".lock")
    with _LOCK:
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl_module = None
            locked = False
            try:
                import fcntl as fcntl_module

                fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_EX)
                locked = True
            except (ImportError, OSError):
                pass
            try:
                yield
            finally:
                if locked and fcntl_module is not None:
                    fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_UN)


def record_current_user_usage(
    *,
    session_id: str,
    turn_id: str,
    capability: str,
    provider: str,
    model: str,
    summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    user = get_current_user()
    return record_usage(
        user_id=user.id,
        username=user.username,
        session_id=session_id,
        turn_id=turn_id,
        capability=capability,
        provider=provider,
        model=model,
        summary=summary,
    )


def record_usage(
    *,
    user_id: str,
    username: str,
    session_id: str,
    turn_id: str,
    capability: str,
    provider: str,
    model: str,
    summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    metrics = normalize_usage_summary(summary)
    if not any(metrics.values()):
        return None
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "username": username,
        "session_id": session_id,
        "turn_id": turn_id,
        "capability": capability,
        "provider": provider,
        "model": model,
        "usage": metrics,
    }
    with usage_ledger_lock():
        with _usage_file().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def _empty_metrics() -> dict[str, int | float]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "total_calls": 0,
        "total_cost_usd": 0.0,
    }


def _read_events() -> list[dict[str, Any]]:
    target = _usage_file()
    events: list[dict[str, Any]] = []
    with usage_ledger_lock():
        if not target.exists():
            return []
        lines = target.read_text(encoding="utf-8").splitlines()
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def usage_summary(user_id: str | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    today = current.date().isoformat()
    month = today[:7]
    buckets = {"today": _empty_metrics(), "month": _empty_metrics(), "all": _empty_metrics()}

    for event in _read_events():
        if user_id and str(event.get("user_id") or "") != user_id:
            continue
        when = str(event.get("time") or "")
        metrics = normalize_usage_summary(event.get("usage"))
        for key, value in metrics.items():
            buckets["all"][key] += value
            if when.startswith(today):
                buckets["today"][key] += value
            if when.startswith(month):
                buckets["month"][key] += value

    for bucket in buckets.values():
        bucket["total_cost_usd"] = round(float(bucket["total_cost_usd"]), 8)
    return buckets


def enforce_current_user_quota() -> None:
    user = get_current_user()
    if user.is_admin:
        return
    from .grants import load_grant

    quota = normalize_quota(load_grant(user.id).get("quota"))
    usage = usage_summary(user.id)
    message = quota_violation(quota, usage)
    if message:
        raise UsageQuotaExceeded(message)


def quota_violation(quota: dict[str, Any], usage: dict[str, Any]) -> str:
    checks = (
        ("daily_token_limit", "today", "total_tokens", "daily token limit"),
        ("monthly_token_limit", "month", "total_tokens", "monthly token limit"),
        ("daily_call_limit", "today", "total_calls", "daily call limit"),
        ("monthly_call_limit", "month", "total_calls", "monthly call limit"),
        ("daily_cost_limit_usd", "today", "total_cost_usd", "daily cost limit"),
        ("monthly_cost_limit_usd", "month", "total_cost_usd", "monthly cost limit"),
    )
    for quota_key, bucket, metric_key, label in checks:
        limit = float(quota.get(quota_key) or 0)
        if limit <= 0:
            continue
        spent = float((usage.get(bucket) or {}).get(metric_key) or 0)
        if spent >= limit:
            return f"Usage quota exceeded: {label} reached."
    return ""
