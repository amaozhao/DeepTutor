"""Quota shape helpers for multi-user grants and usage."""

from __future__ import annotations

from typing import Any

QUOTA_KEYS = (
    "daily_token_limit",
    "monthly_token_limit",
    "daily_call_limit",
    "monthly_call_limit",
    "daily_cost_limit_usd",
    "monthly_cost_limit_usd",
)


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
