"""Helpers for interpreting streamed turn events."""

from __future__ import annotations

from typing import Any

from deeptutor.core.stream import StreamEvent, StreamEventType

# Content call_kinds that make up the persisted answer. The chat agent loop
# streams every round's text as ``content`` with ``agent_loop_round``; the
# finish round (and forced-finish) are the answer, narration rounds are
# filtered back out via their ``call_role`` marker (see _narration_marker_call_id).
_ANSWER_CONTENT_CALL_KINDS = frozenset({"llm_final_response", "agent_loop_round"})


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


def artifact_attachments(event: StreamEvent) -> list[dict[str, Any]]:
    """Generated-file attachments carried by a stream event."""
    metadata = event.metadata or {}
    raw: list[Any] = []
    if event.type == StreamEventType.SOURCES:
        raw = [
            entry
            for entry in metadata.get("sources") or []
            if isinstance(entry, dict) and entry.get("type") == "artifact"
        ]
    elif event.type == StreamEventType.TOOL_RESULT:
        tool_meta = metadata.get("tool_metadata")
        if isinstance(tool_meta, dict):
            raw = [entry for entry in tool_meta.get("artifacts") or [] if isinstance(entry, dict)]
    attachments: list[dict[str, Any]] = []
    for entry in raw:
        url = str(entry.get("url") or "")
        if not url:
            continue
        mime = str(entry.get("mime_type") or "")
        attachments.append(
            {
                "type": "image" if mime.startswith("image/") else "document",
                "filename": str(entry.get("filename") or "file"),
                "mime_type": mime,
                "url": url,
                "size_bytes": entry.get("size_bytes"),
                "generated": True,
            }
        )
    return attachments


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
