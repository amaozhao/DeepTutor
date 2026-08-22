"""Helpers for interpreting streamed turn events."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
import json
import logging
from typing import Any

from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.services.llm.utils import clean_thinking_tags
from deeptutor.services.path_service import get_path_service
from deeptutor.services.session.artifact_attachments import (
    artifact_attachments as artifact_attachments,
)

logger = logging.getLogger(__name__)

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
        and metadata.get("answer_visible") is not True
    ):
        call_id = metadata.get("call_id")
        return str(call_id) if call_id else None
    return None


def assemble_persisted_answer(
    content_segments: Sequence[tuple[str | None, str]],
    narration_call_ids: set[str],
) -> str:
    """Replay visible content bytes, excluding trace-only narration rounds."""
    return clean_thinking_tags(
        "".join(
            text
            for call_id, text in content_segments
            if not (call_id and call_id in narration_call_ids)
        )
    )


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
        if event.get("type") != StreamEventType.ERROR.value or not metadata.get("turn_terminal"):
            continue
        terminal_status = str(metadata.get("status") or "failed")
        status = terminal_status if terminal_status in _FINAL_TURN_STATUSES else "failed"
        if status == "completed":
            status = "failed"
        error = str(event.get("content") or "")
        break

    return status, error


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


async def flush_buffered_events(
    *,
    store: Any,
    turn_id: str,
    capability: str,
    events: list[dict[str, Any]],
    persisted_events: list[dict[str, Any]] | None = None,
) -> bool:
    persisted = persisted_events if persisted_events is not None else []
    if len(persisted) == len(events):
        await mirror_events_to_workspace(
            capability=capability,
            turn_id=turn_id,
            payloads=persisted,
        )
        return True
    append_batch = getattr(store, "append_turn_events", None)
    if callable(append_batch):
        try:
            persisted_batch = await append_batch(turn_id, events)
        except ValueError as exc:
            if "Turn not found:" not in str(exc):
                raise
            logger.warning(
                "Skip persisting %d buffered event(s) for missing turn %s",
                len(events),
                turn_id,
            )
            return True
        persisted.extend(persisted_batch)
        await mirror_events_to_workspace(
            capability=capability,
            turn_id=turn_id,
            payloads=persisted,
        )
        return True

    missing_turn = False
    for index, payload in enumerate(events[len(persisted) :], len(persisted)):
        try:
            persisted_event = await store.append_turn_event(turn_id, payload)
        except ValueError as exc:
            if "Turn not found:" not in str(exc):
                raise
            logger.warning(
                "Skip persisting %d buffered event(s) for missing turn %s (first: %s)",
                len(events) - index,
                turn_id,
                payload.get("type", ""),
            )
            missing_turn = True
            break
        persisted.append(persisted_event)
    if missing_turn and not persisted:
        return True
    await mirror_events_to_workspace(
        capability=capability,
        turn_id=turn_id,
        payloads=persisted,
    )
    return True
