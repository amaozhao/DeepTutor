"""Validation helpers for user-scoped filesystem resource identifiers."""

from __future__ import annotations

from pathlib import Path
import re

RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def validate_resource_id(value: str, label: str = "resource id", *, max_length: int = 128) -> str:
    """Return a normalized machine ID or raise before it can reach a path join."""
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    if len(normalized) > max_length:
        raise ValueError(f"{label} is too long; maximum length is {max_length}")
    if not RESOURCE_ID_RE.fullmatch(normalized):
        raise ValueError(
            f"Invalid {label}: use letters, numbers, underscores, or hyphens only"
        )
    return normalized


def validate_task_id(value: str, label: str = "task id") -> str:
    return validate_resource_id(value, label, max_length=160)


def safe_resolve_under(root: str | Path, *parts: str | Path) -> Path:
    """Resolve ``root / parts`` and reject traversal outside ``root``."""
    root_path = Path(root).expanduser().resolve()
    candidate = root_path.joinpath(*parts).expanduser().resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise ValueError(f"Resolved path escapes allowed root: {root_path}") from exc
    return candidate


def safe_child_path(root: str | Path, *parts: str | Path) -> Path:
    return safe_resolve_under(root, *parts)


__all__ = [
    "RESOURCE_ID_RE",
    "safe_child_path",
    "safe_resolve_under",
    "validate_resource_id",
    "validate_task_id",
]
