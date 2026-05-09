"""Resource identifier and path-safety helpers for user-scoped storage."""

from __future__ import annotations

from pathlib import Path
import re

RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def validate_resource_id(value: str, label: str = "resource id", *, max_length: int = 128) -> str:
    """Return a filesystem-safe resource id or raise ``ValueError``."""
    if not isinstance(value, str):
        raise ValueError(f"Invalid {label}.")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_length or not RESOURCE_ID_RE.match(cleaned):
        raise ValueError(
            f"Invalid {label}: use 1-{max_length} letters, numbers, dashes, or underscores."
        )
    return cleaned


def validate_task_id(value: str, label: str = "task id") -> str:
    """Task ids are resource ids with a slightly larger length cap."""
    return validate_resource_id(value, label, max_length=160)


def validate_user_id(value: str) -> str:
    """Validate a user id before using it as part of a filesystem path."""
    return validate_resource_id(value, "user id")


def safe_resolve_under(root: str | Path, *parts: str | Path) -> Path:
    """Resolve a child path and ensure it stays under ``root``."""
    root_path = Path(root).resolve()
    candidate = root_path.joinpath(*parts).resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("Path escapes the configured storage root.") from exc
    return candidate


def safe_child_path(root: str | Path, *parts: str | Path) -> Path:
    """Backward-compatible alias for ``safe_resolve_under``."""
    return safe_resolve_under(root, *parts)


__all__ = [
    "safe_child_path",
    "safe_resolve_under",
    "validate_resource_id",
    "validate_task_id",
    "validate_user_id",
]
