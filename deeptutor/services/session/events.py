"""Helpers for interpreting streamed turn events."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.services.path_service import get_path_service

logger = logging.getLogger(__name__)

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


def synthesize_done_event(turn_id: str, turn: dict[str, Any] | None) -> dict[str, Any]:
    status = "completed"
    error: str | None = None
    if turn is not None:
        raw_status = str(turn.get("status") or "").strip()
        if raw_status in {"failed", "cancelled", "completed"}:
            status = raw_status
        error_text = str(turn.get("error") or "").strip()
        if error_text:
            error = error_text
    metadata: dict[str, Any] = {"status": status, "synthesized": True}
    if error:
        metadata["error"] = error
    return {
        "type": "done",
        "source": "turn_runtime",
        "stage": "",
        "content": "",
        "metadata": metadata,
        "session_id": "",
        "turn_id": turn_id,
        "seq": 0,
    }


def synthesize_error_event(turn_id: str, turn: dict[str, Any] | None) -> dict[str, Any] | None:
    error = str((turn or {}).get("error") or "").strip()
    if not error:
        return None
    return {
        "type": "error",
        "source": "turn_runtime",
        "stage": "",
        "content": error,
        "metadata": {"status": "failed", "synthesized": True},
        "session_id": str((turn or {}).get("session_id") or ""),
        "turn_id": turn_id,
        "seq": 0,
    }


async def mirror_events_to_workspace(
    *, capability: str, turn_id: str, payloads: list[dict[str, Any]]
) -> None:
    """Append a batch of turn events to the workspace mirror off the event loop."""
    if payloads:
        await asyncio.to_thread(
            _mirror_events_to_workspace_sync,
            capability=capability,
            turn_id=turn_id,
            payloads=payloads,
        )


def mirror_event_to_workspace(*, capability: str, turn_id: str, payload: dict[str, Any]) -> None:
    _mirror_events_to_workspace_sync(
        capability=capability,
        turn_id=turn_id,
        payloads=[payload],
    )


def _mirror_events_to_workspace_sync(
    *, capability: str, turn_id: str, payloads: list[dict[str, Any]]
) -> None:
    try:
        task_dir = get_path_service().get_task_workspace(capability, turn_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        event_file = task_dir / "events.jsonl"
        with open(event_file, "a", encoding="utf-8") as file:
            file.write(
                "".join(
                    json.dumps(payload, ensure_ascii=False, default=str) + "\n"
                    for payload in payloads
                )
            )
    except Exception:
        logger.debug("Failed to mirror turn events to workspace", exc_info=True)
