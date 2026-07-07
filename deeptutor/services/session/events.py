"""Helpers for interpreting streamed turn events."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.services.session.artifact_attachments import (
    artifact_attachments as artifact_attachments,
)

# Content call_kinds that make up the persisted answer. The chat agent loop
# streams every round's text as ``content`` with ``agent_loop_round``; the
# finish round (and forced-finish) are the answer, narration rounds are
# filtered back out via their ``call_role`` marker (see _narration_marker_call_id).
_ANSWER_CONTENT_CALL_KINDS = frozenset({"llm_final_response", "agent_loop_round"})
_FINAL_TURN_STATUSES = frozenset({"completed", "failed", "cancelled", "rejected"})


def should_capture_assistant_content(event: StreamEvent) -> bool:
    if event.type != StreamEventType.CONTENT:
        return False
    metadata = event.metadata or {}
    call_id = metadata.get("call_id")
    if not call_id:
        return True
    return metadata.get("call_kind") in _ANSWER_CONTENT_CALL_KINDS


def narration_marker_call_id(event: StreamEvent) -> str | None:
    """Return the call id for narration text that should not be persisted."""
    metadata = event.metadata or {}
    if (
        metadata.get("trace_kind") == "call_status"
        and metadata.get("call_state") == "complete"
        and metadata.get("call_role") == "narration"
    ):
        call_id = metadata.get("call_id")
        return str(call_id) if call_id else None
    return None


def event_usage_summary(event: StreamEvent) -> dict[str, Any] | None:
    if event.type != StreamEventType.RESULT:
        return None
    metadata = event.metadata or {}
    nested = metadata.get("metadata")
    if isinstance(nested, dict) and isinstance(nested.get("cost_summary"), dict):
        return nested["cost_summary"]
    if isinstance(metadata.get("cost_summary"), dict):
        return metadata["cost_summary"]
    return None


def merge_usage_summary(
    current: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not incoming:
        return current
    keys = ("prompt_tokens", "completion_tokens", "total_tokens", "total_calls", "total_cost_usd")
    merged = dict(current or {})
    for key in keys:
        left = float(merged.get(key) or 0)
        right = float(incoming.get(key) or 0)
        value = left + right
        merged[key] = round(value, 8) if key.endswith("_usd") else int(value)
    return merged


def resolve_turn_outcome(
    assistant_events: Sequence[dict[str, Any]],
    done_event: StreamEvent | None,
) -> tuple[str, str]:
    """Resolve the persisted turn status and error from the terminal protocol."""
    done_metadata = (done_event.metadata or {}) if done_event is not None else {}
    status = str(done_metadata.get("status") or "completed")
    if status not in _FINAL_TURN_STATUSES:
        status = "completed"

    error = ""
    for event in reversed(assistant_events):
        metadata = event.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        if event.get("type") != StreamEventType.ERROR.value or not metadata.get(
            "turn_terminal"
        ):
            continue
        terminal_status = str(metadata.get("status") or "failed")
        status = terminal_status if terminal_status in _FINAL_TURN_STATUSES else "failed"
        if status == "completed":
            status = "failed"
        error = str(event.get("content") or "")
        break

    return status, error
