"""
Turn-level runtime manager for unified chat streaming.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
import contextlib
from contextvars import Token
from dataclasses import dataclass, field
import importlib
import logging
import threading
from typing import TYPE_CHECKING, Any

from deeptutor.agents.notebook import NotebookAnalysisAgent
from deeptutor.api.routers.settings import get_enabled_optional_tools
from deeptutor.book import context as book_context_services
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.multi_user.context import get_current_user
from deeptutor.multi_user.model_access import (
    apply_allowed_llm_selection,
    has_capability_access,
    redacted_model_access,
)
from deeptutor.multi_user.paths import get_admin_path_service
from deeptutor.multi_user.personal_models import merge_personal_llm_profiles
from deeptutor.multi_user.skill_access import assigned_skill_ids
from deeptutor.multi_user.tool_access import allowed_optional_tools
from deeptutor.multi_user.usage import enforce_current_user_quota, record_current_user_usage
from deeptutor.runtime import orchestrator as runtime_orchestrator
from deeptutor.runtime.memory_reclaim import schedule_memory_reclaim
from deeptutor.runtime.request_contracts import validate_capability_config
from deeptutor.services import config as config_services
from deeptutor.services import memory as memory_services
from deeptutor.services import persona as persona_services
from deeptutor.services import skill as skill_services
from deeptutor.services.llm import stream as llm_stream
from deeptutor.services.model_selection import LLMSelection, apply_llm_selection_to_catalog
from deeptutor.services.model_selection import runtime as model_selection_runtime
from deeptutor.services.notebook import get_notebook_manager
from deeptutor.services.persona import PersonaService
from deeptutor.services.session import context_builder as session_context
from deeptutor.services.session.artifact_attachments import fill_preview_text
from deeptutor.services.session.attachments import prepare_attachments
from deeptutor.services.session.events import (
    artifact_attachments as _artifact_attachments,
)
from deeptutor.services.session.events import (
    assemble_persisted_answer as _assemble_persisted_answer,
)
from deeptutor.services.session.events import (
    event_usage_summary as _event_usage_summary,
)
from deeptutor.services.session.events import (
    flush_buffered_events as _flush_buffered_events,
)
from deeptutor.services.session.events import (
    merge_usage_summary as _merge_usage_summary,
)
from deeptutor.services.session.events import (
    narration_marker_call_id as _narration_marker_call_id,
)
from deeptutor.services.session.events import resolve_turn_outcome as _resolve_turn_outcome
from deeptutor.services.session.events import (
    should_capture_assistant_content as _should_capture_assistant_content,
)
from deeptutor.services.session.events import (
    synthesize_done_event as _synthesize_done_event,
)
from deeptutor.services.session.events import (
    synthesize_error_event as _synthesize_error_event,
)
from deeptutor.services.session.followup import (
    extract_followup_question_context as _extract_followup_question_context,
)
from deeptutor.services.session.followup import (
    extract_persist_user_message as _extract_persist_user_message,
)
from deeptutor.services.session.followup import (
    extract_regenerate_flag as _extract_regenerate_flag,
)
from deeptutor.services.session.followup import (
    format_followup_question_context as _format_followup_question_context,
)
from deeptutor.services.session.payloads import (
    READING_SELECTION_MAX_CHARS as READING_SELECTION_MAX_CHARS,
)
from deeptutor.services.session.payloads import (
    clip_text as _clip_text,
)
from deeptutor.services.session.payloads import (
    extract_memory_references as _extract_memory_references,
)
from deeptutor.services.session.payloads import (
    llm_selection_dict as _llm_selection_dict,
)
from deeptutor.services.session.payloads import mastery_path_id as _mastery_path_id
from deeptutor.services.session.payloads import reading_material_id as _reading_material_id
from deeptutor.services.session.payloads import reading_viewport as _reading_viewport
from deeptutor.services.session.payloads import (
    request_snapshot_metadata as _base_request_snapshot_metadata,
)
from deeptutor.services.session.payloads import (
    sanitize_session_title as _sanitize_session_title,
)
from deeptutor.services.session.protocol import SessionStoreProtocol
from deeptutor.services.session.questions import format_question_bank_entry
from deeptutor.services.session.source_inventory import (
    build_inventory,
    render_manifest,
    serialize_referenced_transcript,
)
from deeptutor.services.session.store import get_session_store
from deeptutor.services.settings import interface_settings
from deeptutor.services.skill.service import SkillService, render_skills_manifest

if TYPE_CHECKING:
    from deeptutor.learning.storage import MasteryPathLease
    from deeptutor.services.llm.config import LLMConfig

logger = logging.getLogger(__name__)

_INTERRUPTED_TURN_ERROR = "Turn interrupted by server restart. Please retry your message."


def _request_snapshot_metadata(**kwargs: Any) -> dict[str, Any]:
    """Persist reading context omitted by the shared snapshot helper."""
    metadata = _base_request_snapshot_metadata(**kwargs)
    material_id = _reading_material_id(kwargs["payload"].get("reading_material_id"))
    if material_id:
        metadata["request_snapshot"]["readingMaterialId"] = material_id
    return metadata


async def _count_branch_user_turns(
    store: SessionStoreProtocol,
    session_id: str,
    leaf_message_id: int | None,
) -> int:
    """Count user messages on the active branch's ancestor chain.

    Used by the chat source inventory to assign ``first_seen_turn`` for
    *fresh* sources (= current turn = past_user_turns + 1). When
    ``leaf_message_id`` is ``None`` (legacy linear append) all messages
    in the session are counted; otherwise we walk the
    ``parent_message_id`` chain so sibling branches don't inflate the
    count. Kept tiny and protocol-only (``get_messages``) so it stays
    compatible with every store backend.
    """
    all_msgs = await store.get_messages(session_id)
    if leaf_message_id is None:
        return sum(1 for m in all_msgs if m.get("role") == "user")
    by_id: dict[int, dict[str, Any]] = {}
    for m in all_msgs:
        mid = m.get("id")
        if mid is not None:
            by_id[int(mid)] = m
    count = 0
    current: int | None = int(leaf_message_id)
    safety = 10_000
    while current is not None and safety > 0:
        m = by_id.get(int(current))
        if m is None:
            break
        if m.get("role") == "user":
            count += 1
        parent = m.get("parent_message_id")
        current = int(parent) if parent is not None else None
        safety -= 1
    return count


async def _build_question_bank_context(
    store: SessionStoreProtocol,
    entry_ids: list[Any],
) -> str:
    """Fetch the requested Question Bank entries and render them as context."""
    get_entry = getattr(store, "get_notebook_entry", None)
    if not callable(get_entry):
        return ""

    seen: set[int] = set()
    blocks: list[str] = []
    for raw in entry_ids:
        try:
            entry_id = int(raw)
        except (TypeError, ValueError):
            continue
        if entry_id in seen:
            continue
        seen.add(entry_id)
        try:
            entry = await get_entry(entry_id)
        except Exception as exc:
            logger.warning("Failed to load question bank entry %s: %s", entry_id, exc)
            entry = None
        if not entry:
            continue
        blocks.append(format_question_bank_entry(entry))
    return "\n\n---\n\n".join(blocks)


@dataclass
class _LiveSubscriber:
    queue: asyncio.Queue[dict[str, Any]]


@dataclass
class _TurnExecution:
    turn_id: str
    session_id: str
    capability: str
    payload: dict[str, Any]
    task: asyncio.Task[None] | None = None
    # True while the turn is parked inside ``ask_user`` waiting for a learner
    # reply. Such a turn holds its resources (notably a mastery path lease)
    # but is doing no work, so another turn may take over from it.
    awaiting_user_reply: bool = False
    subscribers: list[_LiveSubscriber] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    next_seq: int = 1
    flush_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    events_persisted: bool = False
    persisted_events: list[dict[str, Any]] = field(default_factory=list)
    events_flushed: bool = False


class TurnRuntimeManager:
    """Run one turn in the background and multiplex persisted/live events."""

    def __init__(self, store: SessionStoreProtocol | None = None) -> None:
        self.store = store or get_session_store()
        self._lock = asyncio.Lock()
        self._executions: dict[str, _TurnExecution] = {}
        # Per-turn reply queues used by tools that pause the agentic
        # loop (e.g. ``ask_user``). Queue is created in ``_run_turn``
        # before the orchestrator is invoked and cleaned up in the
        # ``finally`` block, so callers of ``submit_user_reply`` see
        # ``False`` for any turn that is no longer awaiting input.
        # Each entry is a dict of shape:
        #   {"text": str, "answers": list[{"questionId": str, "text": str}] | None}
        # ``text`` is always present (flat fallback for legacy callers);
        # ``answers`` carries the structured per-question replies when the
        # frontend sends the v2 ``ask_user`` shape.
        self._reply_queues: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}

    async def has_live_execution(self, turn_id: str) -> bool:
        """Public check for whether this process still owns the turn's runner.

        Lets transport callers (e.g. the unified WS router) avoid reaching into
        ``_lock`` / ``_executions`` directly.
        """
        return await self._has_live_execution(turn_id)

    async def _has_live_execution(self, turn_id: str) -> bool:
        """Whether this process still owns the turn's in-memory runner."""
        async with self._lock:
            execution = self._executions.get(turn_id)
            if execution is None:
                return False
            # Some tests and pause/resubscribe paths create an execution
            # placeholder without a task. Treat its presence as live so we do
            # not falsely fail a turn that is still owned by this process.
            return execution.task is None or not execution.task.done()

    async def _fail_orphan_running_turn(self, turn: dict[str, Any] | None) -> dict[str, Any] | None:
        """Finalize a persisted running turn that has no local execution.

        Running turns are process-local: after a server/container restart the
        database row may still say ``running`` while the task and subscriber
        queues are gone. The runtime owns that liveness check, not the store,
        so recovery stays backend-agnostic.
        """
        if turn is None or str(turn.get("status") or "") != "running":
            return turn
        turn_id = str(turn.get("id") or turn.get("turn_id") or "").strip()
        if not turn_id or await self._has_live_execution(turn_id):
            return turn
        await self.store.update_turn_status(turn_id, "failed", _INTERRUPTED_TURN_ERROR)
        return await self.store.get_turn(turn_id)

    async def _recover_orphan_running_turns_for_session(self, session_id: str) -> None:
        """Clear stale active turns before creating a fresh turn."""
        for turn in await self.store.list_active_turns(session_id):
            await self._fail_orphan_running_turn(turn)

    async def _is_awaiting_user_reply(self, turn_id: str) -> bool:
        async with self._lock:
            execution = self._executions.get(turn_id)
            return execution is not None and execution.awaiting_user_reply

    async def _release_superseded_lease(self, path_id: str, lease: MasteryPathLease) -> None:
        """Free ``lease`` when its turn can no longer be working on the path.

        Two cases release it. A turn that is no longer ``running`` (finished,
        or orphaned by a restart) is simply gone. A turn parked inside
        ``ask_user`` is alive but idle — it holds the lease for as long as the
        learner takes to answer, which may be forever. Since the posed question
        is persisted on the path itself, the arriving turn resumes exactly
        where the parked one stopped, so handing the path over loses nothing;
        the parked turn is cancelled rather than left to mutate a path it no
        longer owns. Only a turn that is actively generating keeps the lease.
        """
        LearningStore = importlib.import_module("deeptutor.learning.storage").LearningStore
        leased_turn = await self._fail_orphan_running_turn(await self.store.get_turn(lease.turn_id))
        alive = leased_turn is not None and str(leased_turn.get("status") or "") == "running"
        if alive:
            if not await self._is_awaiting_user_reply(lease.turn_id):
                # Genuinely busy — leave the lease, and let the store report
                # the conflict to the caller.
                return
            await self.cancel_turn(lease.turn_id)
        # Scoped to the superseded turn id, so a lease already re-taken by
        # someone else survives.
        await asyncio.to_thread(
            LearningStore().release_path_lease,
            path_id,
            turn_id=lease.turn_id,
        )

    async def _acquire_mastery_path_lease(
        self,
        *,
        path_id: str,
        session_id: str,
        turn_id: str,
        owns_path: bool,
    ) -> None:
        """Bind a session to its path and take over from any superseded turn."""
        learning_storage = importlib.import_module("deeptutor.learning.storage")
        LearningStore = learning_storage.LearningStore
        PathLeaseConflictError = learning_storage.PathLeaseConflictError
        learning_store = LearningStore()
        await asyncio.to_thread(
            learning_store.bind_session,
            path_id,
            session_id,
            owns_path=owns_path,
        )
        lease = await asyncio.to_thread(learning_store.get_path_lease, path_id)
        if lease is not None and lease.turn_id != turn_id and lease.session_id != "__path_api__":
            await self._release_superseded_lease(path_id, lease)
        try:
            await asyncio.to_thread(
                learning_store.acquire_path_lease,
                path_id,
                session_id,
                turn_id,
            )
        except PathLeaseConflictError as exc:
            raise RuntimeError(
                "mastery_path_busy: "
                f"path {path_id!r} is already active in session {exc.lease.session_id!r}"
            ) from exc

    async def start_turn(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        capability = str(payload.get("capability") or "chat")
        if not payload.get("language"):
            payload = {
                **payload,
                "language": interface_settings.get_response_language(default="en"),
            }
        raw_config = dict(payload.get("config", {}) or {})
        runtime_only_keys = (
            "_persist_user_message",
            "_regenerate",
            "_regenerated_from_message_id",
            "_superseded_turn_id",
            "followup_question_context",
            # Per-turn subagent consult budget (composer stepper). Not part of
            # any capability's public config schema, so it rides as a runtime
            # key — stripped before validation, merged back into the turn config
            # and read by the subagent capability from context.config_overrides.
            "subagent_consult_budget",
        )
        runtime_only_config = {
            key: raw_config.pop(key) for key in runtime_only_keys if key in raw_config
        }
        try:
            validated_public_config = validate_capability_config(capability, raw_config)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        payload = {
            **payload,
            "capability": capability,
            "config": {**validated_public_config, **runtime_only_config},
        }
        session = await self.store.ensure_session(payload.get("session_id"))
        preferences = session.get("preferences") or {}
        mastery_path_explicit = "mastery_path_id" in payload
        configured_mastery_path_id = _mastery_path_id(
            payload.get("mastery_path_id")
            if mastery_path_explicit
            else preferences.get("mastery_path_id")
        )
        mastery_binding = None
        if capability == "mastery_path":
            mastery_binding = importlib.import_module(
                "deeptutor.learning.identity"
            ).resolve_mastery_path_binding(
                configured_path_id=configured_mastery_path_id,
                book_references=payload.get("book_references", []),
                session_id=session["id"],
            )
            mastery_path_id = mastery_binding.path_id
        else:
            mastery_path_id = configured_mastery_path_id
        payload = {**payload, "mastery_path_id": mastery_path_id}
        # Persona is a session-level preference (mirrors llm_selection): an
        # explicit ``persona`` key in the payload — including an empty string,
        # which means "Default" / no persona — wins and is persisted below; an
        # absent key falls back to the session's stored preference so the
        # active persona survives reloads and follows the session.
        persona_explicit = "persona" in payload
        persona_pref = str(
            (payload.get("persona") if persona_explicit else preferences.get("persona")) or ""
        ).strip()
        payload = {**payload, "persona": persona_pref}
        raw_llm_selection = payload.get("llm_selection")
        if raw_llm_selection is None:
            raw_llm_selection = preferences.get("llm_selection")
        try:
            llm_selection = _llm_selection_dict(raw_llm_selection)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        if llm_selection:
            try:
                llm_selection = apply_allowed_llm_selection(llm_selection) or {}
            except PermissionError as exc:
                raise RuntimeError(str(exc)) from exc
        else:
            # Non-admin users MUST end up with a concrete llm_selection so we
            # never silently fall through to the global LLM client (which is
            # configured from admin runtime settings). Admin keeps the existing behavior
            # (None llm_selection → default config from admin scope).
            current_user = get_current_user()
            if not current_user.is_admin:
                # Single gate, shared with the frontend lock and any HTTP
                # surface: no usable LLM grant → a clear terminal error here
                # instead of a silent fall-through to the global client.
                if not has_capability_access("llm"):
                    raise RuntimeError(
                        "No LLM model is assigned to your account. Please contact an administrator."
                    )
                # Pin the first granted-and-available model as the selection.
                assigned_llms = [
                    item
                    for item in redacted_model_access(current_user.id).get("llm", [])
                    if item.get("available")
                ]
                llm_selection = {
                    "profile_id": assigned_llms[0].get("profile_id"),
                    "model_id": assigned_llms[0].get("model_id"),
                }
        if llm_selection:
            try:
                apply_llm_selection_to_catalog(
                    merge_personal_llm_profiles(config_services.get_model_catalog_service().load()),
                    LLMSelection.from_payload(llm_selection),
                )
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
        # If the caller didn't pin a per-turn tool list (e.g. non-web
        # channels or the new web UI which sources tools from
        # /settings/tools), back-fill from the user's saved toggleable-tool
        # preference so the chat pipeline sees the same set the user picked
        # in Settings. Callers that explicitly pass ``tools`` (including
        # an empty list) keep their value untouched.
        if payload.get("tools") is None:
            try:
                payload = {**payload, "tools": list(get_enabled_optional_tools())}
            except Exception as exc:
                logger.warning("Failed to load enabled optional tools: %s", exc)
                payload = {**payload, "tools": []}
        # Admin-imposed per-user tool whitelist (grant v2). Sits after the
        # back-fill so explicit caller lists and settings defaults pass the
        # same gate; this is the single enforcement point for every
        # capability's turn.
        allowed_tools = allowed_optional_tools()
        if allowed_tools is not None:
            payload = {
                **payload,
                "tools": [t for t in (payload.get("tools") or []) if t in allowed_tools],
            }
        payload = {**payload, "llm_selection": llm_selection}
        await self._recover_orphan_running_turns_for_session(session["id"])
        preference_update: dict[str, Any] = {
            "capability": capability,
            "tools": list(payload.get("tools") or []),
            "knowledge_bases": list(payload.get("knowledge_bases") or []),
            "language": str(payload.get("language") or "en"),
        }
        if llm_selection:
            preference_update["llm_selection"] = llm_selection
        if persona_explicit:
            # Persist explicit set AND explicit clear ("" = back to Default).
            preference_update["persona"] = persona_pref
        if mastery_path_explicit or mastery_binding is not None:
            # Mastery turns persist their resolved path for later turns.
            preference_update["mastery_path_id"] = mastery_path_id
        await self.store.update_session_preferences(session["id"], preference_update)
        turn = await self.store.create_turn(session["id"], capability=capability)
        execution = _TurnExecution(
            turn_id=turn["id"],
            session_id=session["id"],
            capability=capability,
            payload=dict(payload),
        )
        # Publish an ownership marker before trying to recover another path
        # lease. Two start_turn calls can otherwise interleave after the first
        # turn row is created but before its task is registered, causing the
        # second caller to misclassify that healthy turn as a restart orphan.
        async with self._lock:
            self._executions[turn["id"]] = execution
        mastery_lease_acquired = False
        if mastery_binding is not None:
            try:
                await self._acquire_mastery_path_lease(
                    path_id=mastery_binding.path_id,
                    session_id=session["id"],
                    turn_id=turn["id"],
                    owns_path=mastery_binding.owned_by_session,
                )
                mastery_lease_acquired = True
            except Exception as exc:
                async with self._lock:
                    self._executions.pop(turn["id"], None)
                with contextlib.suppress(Exception):
                    await self.store.update_turn_status(turn["id"], "rejected", str(exc))
                raise
            persisted_turn = await self.store.get_turn(turn["id"])
            if persisted_turn is None or persisted_turn.get("status") != "running":
                # An administrative reset/delete can cancel the placeholder
                # while lease acquisition is in flight. Never launch a task
                # after that cancellation has already become durable.
                LearningStore = importlib.import_module("deeptutor.learning.storage").LearningStore
                async with self._lock:
                    self._executions.pop(turn["id"], None)
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(
                        LearningStore().release_path_lease,
                        mastery_binding.path_id,
                        turn_id=turn["id"],
                    )
                raise RuntimeError("Mastery turn was cancelled while starting")
        session_metadata: dict[str, Any] = {
            "session_id": session["id"],
            "turn_id": turn["id"],
        }
        regenerated_from = runtime_only_config.get("_regenerated_from_message_id")
        if regenerated_from is not None:
            session_metadata["regenerated_from_message_id"] = regenerated_from
        superseded_turn_id = runtime_only_config.get("_superseded_turn_id")
        if superseded_turn_id:
            session_metadata["superseded_turn_id"] = str(superseded_turn_id)
        if runtime_only_config.get("_regenerate"):
            session_metadata["regenerate"] = True
        try:
            await self._publish_live_event(
                execution,
                StreamEvent(
                    type=StreamEventType.SESSION,
                    source="turn_runtime",
                    metadata=session_metadata,
                ),
            )
            async with self._lock:
                execution.task = asyncio.create_task(self._run_turn(execution))
        except Exception as exc:
            async with self._lock:
                self._executions.pop(turn["id"], None)
            if mastery_binding is not None and mastery_lease_acquired:
                LearningStore = importlib.import_module("deeptutor.learning.storage").LearningStore
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(
                        LearningStore().release_path_lease,
                        mastery_binding.path_id,
                        turn_id=turn["id"],
                    )
            with contextlib.suppress(Exception):
                await self.store.update_turn_status(turn["id"], "failed", str(exc))
            raise
        return session, turn

    async def regenerate_last_turn(
        self,
        session_id: str,
        overrides: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Re-run the prior user message in ``session_id``.

        Deletes the trailing assistant message (if any), then dispatches a new
        turn with ``_persist_user_message=False`` and ``_regenerate=True`` so
        the runtime knows not to duplicate the user row or refresh long-term
        memory a second time. The original user message stays in place.
        """
        session_id = str(session_id or "").strip()
        if not session_id:
            raise RuntimeError("nothing_to_regenerate")

        session = await self.store.get_session(session_id)
        if session is None:
            raise RuntimeError("nothing_to_regenerate")

        active = await self.store.get_active_turn(session_id)
        if active is not None:
            raise RuntimeError("regenerate_busy")

        last_user = await self.store.get_last_message(session_id, role="user")
        if last_user is None:
            raise RuntimeError("nothing_to_regenerate")

        last_message = await self.store.get_last_message(session_id)
        previous_turn_id: str | None = None
        if last_message is not None and last_message.get("role") == "assistant":
            for event in last_message.get("events") or []:
                turn_id = str((event or {}).get("turn_id") or "")
                if turn_id:
                    previous_turn_id = turn_id
                    break
            await self.store.delete_message(last_message["id"])

        preferences = session.get("preferences") or {}
        overrides = overrides or {}
        snapshot = {}
        metadata = last_user.get("metadata") or {}
        if isinstance(metadata, dict):
            candidate = metadata.get("request_snapshot") or metadata.get("requestSnapshot")
            if isinstance(candidate, dict):
                snapshot = candidate

        capability = str(
            overrides.get("capability")
            or last_user.get("capability")
            or preferences.get("capability")
            or "chat"
        )
        tools = list(
            overrides.get("tools")
            if overrides.get("tools") is not None
            else preferences.get("tools") or []
        )
        knowledge_bases = list(
            overrides.get("knowledge_bases")
            if overrides.get("knowledge_bases") is not None
            else preferences.get("knowledge_bases") or []
        )
        language = str(overrides.get("language") or preferences.get("language") or "en")

        config: dict[str, Any] = dict(overrides.get("config") or {})
        config.update(
            {
                "_persist_user_message": False,
                "_regenerate": True,
                "_regenerated_from_message_id": int(last_user["id"]),
            }
        )
        if previous_turn_id:
            config["_superseded_turn_id"] = previous_turn_id
        llm_selection = (
            overrides.get("llm_selection")
            if overrides.get("llm_selection") is not None
            else snapshot.get("llmSelection") or preferences.get("llm_selection")
        )
        mastery_path_id = _mastery_path_id(
            overrides.get("mastery_path_id")
            if "mastery_path_id" in overrides
            else snapshot.get("masteryPathId") or preferences.get("mastery_path_id")
        )

        payload: dict[str, Any] = {
            "session_id": session_id,
            "capability": capability,
            "content": str(last_user.get("content", "") or ""),
            "tools": tools,
            "knowledge_bases": knowledge_bases,
            "language": language,
            "attachments": list(last_user.get("attachments") or []),
            "notebook_references": list(
                overrides.get("notebook_references")
                if overrides.get("notebook_references") is not None
                else preferences.get("notebook_references") or []
            ),
            "history_references": list(
                overrides.get("history_references")
                if overrides.get("history_references") is not None
                else preferences.get("history_references") or []
            ),
            "book_references": list(
                overrides.get("book_references")
                if overrides.get("book_references") is not None
                else snapshot.get("bookReferences") or []
            ),
            "mastery_path_id": mastery_path_id,
            # Recovered from the original turn's snapshot so the regenerate runs
            # against the same document. An explicit override wins (the reader
            # may have moved on), and the viewport is deliberately not restored —
            # "where the user was looking" is stale by definition on a retry.
            "reading_material_id": _reading_material_id(
                overrides.get("reading_material_id")
                if "reading_material_id" in overrides
                else snapshot.get("readingMaterialId")
            ),
            "config": config,
        }
        if llm_selection:
            payload["llm_selection"] = llm_selection
        return await self.start_turn(payload)

    async def cancel_turn(self, turn_id: str) -> bool:
        async with self._lock:
            execution = self._executions.get(turn_id)
        if execution is None or execution.task is None or execution.task.done():
            turn = await self.store.get_turn(turn_id)
            if turn is None or turn.get("status") != "running":
                return False
            await self.store.update_turn_status(turn_id, "cancelled", "Turn cancelled")
            return True
        execution.task.cancel()
        # Wait for the task to finish so its finally block (including save)
        # completes before the caller proceeds.
        try:
            await execution.task
        except asyncio.CancelledError:
            pass
        return True

    async def submit_user_reply(
        self,
        turn_id: str,
        text: str | None = None,
        *,
        answers: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Deliver a user reply to a turn that's paused on ``ask_user``.

        Returns ``True`` if the turn was waiting and the reply was
        accepted; ``False`` if no waiter is registered (turn finished,
        was cancelled, or the model never asked).

        Accepts either ``text`` (single free-form reply, legacy single-
        question shape) or ``answers`` (list of ``{questionId, text}``
        pairs, v2 multi-question shape). Both may be passed; the
        consumer prefers structured ``answers`` when present and falls
        back to ``text`` for the legacy case. The payload is enqueued —
        the pipeline's ``await waiter()`` call unblocks on the next
        event-loop tick and substitutes the reply into the matching
        ``role=tool`` message.
        """
        queue = self._reply_queues.get(turn_id)
        if queue is None:
            return False
        payload: dict[str, Any] = {"text": text or "", "answers": answers}
        await queue.put(payload)
        return True

    async def subscribe_turn(
        self,
        turn_id: str,
        after_seq: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        backlog = await self.store.get_turn_events(turn_id, after_seq=after_seq)
        last_seq = after_seq
        # Track whether we ever yielded a terminal event (DONE) — if the live
        # queue ends WITHOUT one (e.g. a transient send-side stall on
        # ``safe_send`` swallowed it), we synthesise one before returning so
        # the frontend's ``isStreaming`` state clears immediately rather than
        # waiting on the 45s heartbeat-timeout + reconnect catchup path.
        done_yielded = False

        def _track(item: dict[str, Any]) -> dict[str, Any]:
            nonlocal done_yielded
            if str(item.get("type") or "") == "done":
                done_yielded = True
            return item

        for item in backlog:
            last_seq = max(last_seq, int(item.get("seq") or 0))
            yield _track(item)

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        subscriber = _LiveSubscriber(queue=queue)
        execution: _TurnExecution | None = None
        live_backlog: list[dict[str, Any]] = []
        async with self._lock:
            execution = self._executions.get(turn_id)
            if execution is not None:
                execution.subscribers.append(subscriber)
                live_backlog = [
                    item for item in execution.events if int(item.get("seq") or 0) > last_seq
                ]

        for item in live_backlog:
            seq = int(item.get("seq") or 0)
            if seq <= last_seq:
                continue
            last_seq = seq
            yield _track(item)

        catchup = []
        if execution is None:
            catchup = await self.store.get_turn_events(turn_id, after_seq=last_seq)
        for item in catchup:
            seq = int(item.get("seq") or 0)
            if seq <= last_seq:
                continue
            last_seq = seq
            yield _track(item)

        turn = await self.store.get_turn(turn_id)
        if execution is None:
            turn = await self._fail_orphan_running_turn(turn)
            if turn is None or turn.get("status") != "running":
                # Turn already finished and we didn't see a DONE in any of the
                # persisted history above — synthesise one so the caller can
                # still close out its streaming state cleanly.
                if not done_yielded:
                    if turn is not None and str(turn.get("status") or "") == "failed":
                        error_event = _synthesize_error_event(turn_id, turn)
                        if error_event is not None:
                            yield error_event
                    yield _synthesize_done_event(turn_id, turn)
                return
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                seq = int(item.get("seq") or 0)
                if seq <= last_seq:
                    continue
                last_seq = seq
                yield _track(item)
        finally:
            async with self._lock:
                execution = self._executions.get(turn_id)
                if execution is not None:
                    execution.subscribers = [
                        sub for sub in execution.subscribers if sub is not subscriber
                    ]
            # Safety net: if we drained the live queue (None sentinel arrived)
            # without ever yielding a DONE, the turn is over server-side but
            # the frontend wouldn't know. Read the persisted turn status one
            # more time and synthesise a terminal DONE only for genuinely
            # terminal turns so ``isStreaming`` clears without waiting on
            # the heartbeat-reconnect fallback. A running turn may be paused
            # on ``ask_user`` or may have had this subscription replaced; in
            # that case a synthetic DONE would falsely mark the turn
            # completed while the backend is still awaiting input.
            if not done_yielded:
                final_turn = await self.store.get_turn(turn_id)
                final_status = str((final_turn or {}).get("status") or "").strip()
                if final_turn is None or final_status in {"failed", "cancelled", "completed"}:
                    yield _synthesize_done_event(turn_id, final_turn)

    async def subscribe_session(
        self,
        session_id: str,
        after_seq: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        active_turn = await self.store.get_active_turn(session_id)
        if active_turn is None:
            return
        async for item in self.subscribe_turn(active_turn["id"], after_seq=after_seq):
            yield item

    async def _run_turn(self, execution: _TurnExecution) -> None:
        payload = execution.payload
        session_id = execution.session_id
        capability_name = execution.capability
        turn_id = execution.turn_id
        assistant_events: list[dict[str, Any]] = []
        assistant_content = ""
        turn_usage_summary: dict[str, Any] | None = None
        # Per-round content segments + narration call_ids: a chat-loop round's
        # text is captured live but a round that resolves as narration is
        # dropped from the persisted answer (mirrors the frontend bubble).
        content_segments: list[tuple[str | None, str]] = []
        narration_call_ids: set[str] = set()

        def _persisted_answer() -> str:
            # clean_thinking_tags is a second line of defence: providers that
            # inline <think> in the content channel are split at streaming
            # time by the agent loop, but anything that slips through must
            # never be persisted as the user-facing answer.
            return _assemble_persisted_answer(content_segments, narration_call_ids)

        # Files the model generated this turn (exec/code_execution artifacts),
        # persisted as assistant-message attachments so the UI shows openable
        # cards. Deduped by URL across the turn's SOURCES events.
        generated_attachments: list[dict[str, Any]] = []
        seen_artifact_urls: set[str] = set()
        stream_done_sent = False
        llm_scope_token: Token[LLMConfig | None] | None = None
        reset_active_llm_selection: Callable[[Token[LLMConfig | None] | None], None] | None = (
            model_selection_runtime.reset_llm_selection
        )
        # One queue per turn for ``ask_user`` style pause-resume.
        # Created here (BEFORE the orchestrator runs) so the pipeline can
        # await on the awaitable we publish into ``context.metadata``.
        # Cleaned up unconditionally in the outer ``finally``.
        reply_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._reply_queues[turn_id] = reply_queue

        async def _wait_for_user_reply() -> dict[str, Any] | None:
            # Publish the pause so a turn that wants the same mastery path can
            # tell "busy generating" apart from "parked, learner walked away".
            execution.awaiting_user_reply = True
            try:
                return await reply_queue.get()
            finally:
                execution.awaiting_user_reply = False

        try:
            request_config = dict(payload.get("config", {}) or {})
            followup_question_context = _extract_followup_question_context(request_config)
            persist_user_message = _extract_persist_user_message(request_config)
            is_regenerate = _extract_regenerate_flag(request_config)
            request_config.pop("_regenerated_from_message_id", None)
            request_config.pop("_superseded_turn_id", None)
            raw_user_content = str(payload.get("content", "") or "")
            # Edit-branching tip: when the FE includes ``parent_message_id``
            # (even as ``null``), the new user message attaches at that
            # exact parent — creating a sibling of any existing children
            # and forcing LLM context to come from that parent's ancestor
            # chain only. When the key is absent (legacy callers), the
            # store auto-appends to the latest message in the session.
            branch_parent_explicit = "parent_message_id" in payload
            branch_parent_raw = payload.get("parent_message_id")
            branch_parent_id: int | None
            if branch_parent_explicit:
                try:
                    branch_parent_id = (
                        int(branch_parent_raw) if branch_parent_raw is not None else None
                    )
                except (TypeError, ValueError):
                    branch_parent_id = None
                    branch_parent_explicit = False
            else:
                branch_parent_id = None
            notebook_references = payload.get("notebook_references", []) or []
            history_references = payload.get("history_references", []) or []
            question_notebook_references = payload.get("question_notebook_references", []) or []
            book_context_result = book_context_services.build_book_context(
                payload.get("book_references", []) or []
            )
            book_references = book_context_result.references
            memory_references = _extract_memory_references(payload)
            notebook_context = ""
            history_context = ""
            question_bank_context = ""
            book_context = book_context_result.text

            prepared_attachments = await prepare_attachments(
                session_id=session_id,
                raw_items=payload.get("attachments", []) or [],
                logger=logger,
            )
            attachment_records = prepared_attachments.records
            attachments = prepared_attachments.context
            persisted_attachment_records = prepared_attachments.persisted
            document_texts = prepared_attachments.document_texts

            if followup_question_context:
                existing_messages = await self.store.get_messages_for_context(
                    session_id, leaf_message_id=branch_parent_id
                )
                if not existing_messages:
                    await self.store.add_message(
                        session_id=session_id,
                        role="system",
                        content=_format_followup_question_context(
                            followup_question_context,
                            language=str(payload.get("language", "en") or "en"),
                        ),
                        capability=capability_name or "chat",
                    )

            llm_config, llm_scope_token = model_selection_runtime.activate_llm_selection(
                payload.get("llm_selection")
            )

            current_user = get_current_user()
            enforce_current_user_quota()
            builder = session_context.ContextBuilder(self.store)

            async def _emit_context_event(event: StreamEvent) -> None:
                if event.source in {"context", "context_builder"}:
                    return
                await self._publish_live_event(execution, event)

            history_result = await builder.build(
                session_id=session_id,
                llm_config=llm_config,
                language=payload.get("language", "en"),
                on_event=_emit_context_event,
                leaf_message_id=branch_parent_id,
            )
            memory_store = memory_services.get_memory_store()
            memory_context = memory_store.read_l3_concat() if memory_references else ""

            # Persona: at most one behaviour preset per turn, eagerly
            # injected (a persona must shape the voice from the first
            # token). Resolution: the user's own workspace first; non-admin
            # users fall back to admin-authored presets (personas carry no
            # privileged workflow, so no grant gate applies).
            requested_persona = str(payload.get("persona") or "").strip()
            persona_context = ""
            if requested_persona:
                persona_context = persona_services.get_persona_service().load_for_context(
                    requested_persona
                )
                if not persona_context and not current_user.is_admin:
                    persona_context = PersonaService(
                        root=get_admin_path_service().get_workspace_dir() / "personas"
                    ).load_for_context(requested_persona)
            active_persona = requested_persona if persona_context else ""

            # Skills: never user-selected per turn. The model sees a
            # one-line manifest of every skill visible to this user (own +
            # builtin, plus admin-assigned for non-admin users) and pulls
            # full content on demand via ``read_skill``. ``always`` skills
            # are the exception — their bodies are injected eagerly.
            user_skill_service = skill_services.get_skill_service()
            skill_entries = user_skill_service.summary_entries()
            always_blocks = [user_skill_service.load_always_for_context()]
            if not current_user.is_admin:
                assigned_service = SkillService(
                    root=get_admin_path_service().get_workspace_dir() / "skills",
                    builtin_root=None,
                )
                allowed_skills = assigned_skill_ids(current_user.id)
                assigned_entries = [
                    e for e in assigned_service.summary_entries() if e.name in allowed_skills
                ]
                skill_entries = skill_entries + assigned_entries
                always_blocks.append(
                    assigned_service.load_for_context(
                        [e.name for e in assigned_entries if e.always and e.available]
                    )
                )
            skills_manifest = "\n\n".join(
                part for part in (*always_blocks, render_skills_manifest(skill_entries)) if part
            )

            # Chat capability uses the lightweight manifest + read_source
            # affordance (no upstream LLM call, no wholesale-dump into the
            # user message). All other capabilities keep the legacy concat
            # path because their internal pipelines consume the named blocks
            # (``[Notebook Context]`` etc.) directly.
            is_chat_capability = (capability_name or "") in {"", "chat"}

            source_manifest_text = ""
            source_index: dict[str, str] = {}

            if is_chat_capability:
                resolved_notebook_records = (
                    get_notebook_manager().get_records_by_references(notebook_references)
                    if notebook_references
                    else []
                )
                # Current turn ordinal = (#user messages on this branch's
                # ancestor chain) + 1. ``_count_branch_user_turns`` walks
                # the same lineage the inventory builder uses, so we agree
                # on what "turn N" means for the historical labels.
                current_turn_ordinal = (
                    await _count_branch_user_turns(self.store, session_id, branch_parent_id) + 1
                )
                inventory = await build_inventory(
                    self.store,
                    session_id=session_id,
                    leaf_message_id=branch_parent_id,
                    current_turn_ordinal=current_turn_ordinal,
                    fresh_attachment_records=attachment_records,
                    fresh_notebook_records=resolved_notebook_records,
                    fresh_book_context_text=book_context,
                    fresh_book_references=book_references,
                    fresh_history_session_ids=history_references,
                    fresh_question_entry_ids=question_notebook_references,
                    language=str(payload.get("language", "en") or "en"),
                )
                source_manifest_text, source_index = render_manifest(inventory)
                effective_user_message = raw_user_content
            else:
                if notebook_references:
                    referenced_records = get_notebook_manager().get_records_by_references(
                        notebook_references
                    )
                    if referenced_records:
                        analysis_agent = NotebookAnalysisAgent(
                            language=str(payload.get("language", "en") or "en")
                        )
                        notebook_context = await analysis_agent.analyze(
                            user_question=raw_user_content,
                            records=referenced_records,
                            emit=_emit_context_event,
                        )

                if history_references:
                    history_records: list[dict[str, Any]] = []
                    for session_ref in history_references:
                        history_session_id = str(session_ref or "").strip()
                        if not history_session_id:
                            continue

                        history_session = await self.store.get_session(history_session_id)
                        if not history_session:
                            continue

                        history_messages = await self.store.get_messages_for_context(
                            history_session_id
                        )
                        transcript = serialize_referenced_transcript(
                            history_session,
                            history_messages,
                            language=str(payload.get("language", "en") or "en"),
                        )
                        if not transcript:
                            continue

                        history_summary = str(
                            history_session.get("compressed_summary", "") or ""
                        ).strip()
                        if not history_summary:
                            history_summary = _clip_text(
                                " ".join(
                                    str(message.get("content", "") or "").strip()
                                    for message in history_messages[-4:]
                                    if str(message.get("content", "") or "").strip()
                                ),
                                limit=400,
                            )
                        if not history_summary:
                            history_summary = f"{len(history_messages)} messages"

                        history_records.append(
                            {
                                "id": history_session_id,
                                "notebook_id": "__history__",
                                "notebook_name": "History",
                                "title": str(
                                    history_session.get("title", "") or "Untitled session"
                                ),
                                "summary": history_summary,
                                "output": transcript,
                                "metadata": {
                                    "session_id": history_session_id,
                                    "source": "history",
                                },
                            }
                        )

                    if history_records:
                        analysis_agent = NotebookAnalysisAgent(
                            language=str(payload.get("language", "en") or "en")
                        )
                        history_context = await analysis_agent.analyze(
                            user_question=raw_user_content,
                            records=history_records,
                            emit=_emit_context_event,
                        )
                        if not history_context.strip():
                            MAX_FALLBACK_CHARS = 8000
                            parts: list[str] = []
                            total = 0
                            for record in history_records:
                                output = record.get("output")
                                if not output:
                                    continue
                                part = f"## Session: {record.get('title', 'Untitled')}\n{output}"
                                if total + len(part) > MAX_FALLBACK_CHARS:
                                    remaining = MAX_FALLBACK_CHARS - total
                                    if remaining > 100:
                                        parts.append(part[:remaining] + "\n...(truncated)")
                                    break
                                parts.append(part)
                                total += len(part)
                            history_context = "\n\n".join(parts)

                if question_notebook_references:
                    question_bank_context = await _build_question_bank_context(
                        self.store, question_notebook_references
                    )

                effective_user_message = raw_user_content
                context_parts: list[str] = []
                if document_texts:
                    context_parts.append("[Attached Documents]\n" + "\n\n".join(document_texts))
                if book_context:
                    context_parts.append(f"[Book Context]\n{book_context}")
                if notebook_context:
                    context_parts.append(f"[Notebook Context]\n{notebook_context}")
                if history_context:
                    context_parts.append(f"[History Context]\n{history_context}")
                if question_bank_context:
                    context_parts.append(f"[Question Bank Context]\n{question_bank_context}")
                if context_parts:
                    context_parts.append(f"[User Question]\n{raw_user_content}")
                    effective_user_message = "\n\n".join(context_parts)

            conversation_history = list(history_result.conversation_history)
            conversation_context_text = history_result.context_text

            # SQLite returns integer rowids; PocketBase returns its string
            # record ids. Both are opaque to this layer — they only flow into
            # ``parent_message_id`` chaining and the DONE reconcile metadata.
            new_user_message_id: int | str | None = None
            if persist_user_message:
                # Pass parent explicitly only when the FE pinned it (covers
                # both branched edits with a positive id and root edits
                # with explicit null). Otherwise let the store auto-append.
                parent_kwargs: dict[str, Any] = (
                    {"parent_message_id": branch_parent_id} if branch_parent_explicit else {}
                )
                new_user_message_id = await self.store.add_message(
                    session_id=session_id,
                    role="user",
                    content=raw_user_content,
                    capability=capability_name,
                    attachments=persisted_attachment_records,
                    metadata=_request_snapshot_metadata(
                        payload=payload,
                        content=raw_user_content,
                        capability=capability_name,
                        config=request_config,
                        attachments=persisted_attachment_records,
                        notebook_references=notebook_references,
                        history_references=history_references,
                        question_notebook_references=question_notebook_references,
                        book_references=book_references,
                        persona=active_persona,
                        memory_references=memory_references,
                        llm_selection=payload.get("llm_selection"),
                    ),
                    **parent_kwargs,
                )

            context = UnifiedContext(
                session_id=session_id,
                user_message=effective_user_message,
                conversation_history=conversation_history,
                enabled_tools=payload.get("tools"),
                active_capability=payload.get("capability"),
                knowledge_bases=payload.get("knowledge_bases", []),
                attachments=attachments,
                config_overrides=request_config,
                language=payload.get("language", "en"),
                memory_context=memory_context,
                persona_context=persona_context,
                skills_manifest=skills_manifest,
                source_manifest=source_manifest_text,
                metadata={
                    "conversation_summary": history_result.conversation_summary,
                    "conversation_context_text": conversation_context_text,
                    "history_token_count": history_result.token_count,
                    "history_budget": history_result.budget,
                    "turn_id": turn_id,
                    "question_followup_context": followup_question_context or {},
                    "notebook_references": notebook_references,
                    "history_references": history_references,
                    "question_notebook_references": question_notebook_references,
                    "book_references": book_references,
                    "mastery_path_id": _mastery_path_id(payload.get("mastery_path_id")),
                    "mastery_path_lease_managed": capability_name == "mastery_path",
                    # Immersive reading: the open material activates the reading
                    # capability and binds its tools; the viewport tells the
                    # model where the user is actually looking.
                    "reading_material_id": _reading_material_id(payload.get("reading_material_id")),
                    "reading_viewport": _reading_viewport(payload.get("reading_viewport")),
                    "book_context": book_context,
                    "book_context_warnings": book_context_result.warnings,
                    "memory_references": memory_references,
                    "question_bank_context": question_bank_context,
                    "memory_context": memory_context,
                    "active_persona": active_persona,
                    "llm_selection": payload.get("llm_selection") or {},
                    "llm_model": str(getattr(llm_config, "model", "") or ""),
                    "llm_provider": str(getattr(llm_config, "provider_name", "") or ""),
                    # Per-turn full-text payload for read_source. Empty when
                    # the manifest is empty (non-chat capabilities, or chat
                    # turns with no attached sources). Consumed by the chat
                    # pipeline's tool kwargs injector.
                    "source_index": source_index,
                    # Pause-resume hook: the agentic chat pipeline awaits
                    # this callable when ``ask_user`` (or any other
                    # ``pause_for_user``-emitting tool) pauses the loop.
                    # The callable resolves when the frontend POSTs a
                    # reply via the ``submit_user_reply`` WS message.
                    "wait_for_user_reply": _wait_for_user_reply,
                },
            )

            orch = runtime_orchestrator.ChatOrchestrator()
            pending_done_event: StreamEvent | None = None
            async for event in orch.handle(context):
                turn_usage_summary = _merge_usage_summary(
                    turn_usage_summary,
                    _event_usage_summary(event),
                )
                if event.type == StreamEventType.SESSION:
                    continue
                if event.type == StreamEventType.DONE:
                    pending_done_event = event
                    continue
                payload_event = await self._publish_live_event(execution, event)
                if payload_event.get("type") not in {"done", "session"}:
                    assistant_events.append(payload_event)
                if _should_capture_assistant_content(event):
                    call_id = (event.metadata or {}).get("call_id")
                    content_segments.append((str(call_id) if call_id else None, event.content))
                narration_call_id = _narration_marker_call_id(event)
                if narration_call_id:
                    narration_call_ids.add(narration_call_id)
                for attachment in _artifact_attachments(event):
                    if attachment["url"] not in seen_artifact_urls:
                        seen_artifact_urls.add(attachment["url"])
                        generated_attachments.append(attachment)

            # A mastery turn may have changed which path it is on
            # (``mastery_switch`` / ``mastery_leave``). The conversation's
            # stored preference already followed it; tell the open client too,
            # so what it shows as "currently mastering" is not the path the
            # turn merely started on.
            await self._publish_mastery_path_change(
                execution,
                capability_name=capability_name,
                started_on=_mastery_path_id(payload.get("mastery_path_id")),
                ended_on=str(context.metadata.get("mastery_path_id") or ""),
            )

            # Office binaries the browser cannot render need their text pulled
            # out now, while the files are still on disk, or their preview card
            # opens empty. Skipped on the cancelled path below: that one is
            # already unwinding and must not start new blocking work.
            await fill_preview_text(generated_attachments)

            # The persisted answer is the captured content minus any narration
            # rounds (their text stayed in the trace, never the answer).
            assistant_content = _persisted_answer()

            # Assistant continues the same branch as the user message it
            # answers. If we just persisted a new user row we chain off
            # that; if we did not (regenerate path) and the caller pinned a
            # parent, we use it; otherwise we let the store auto-append
            # (legacy behavior).
            if new_user_message_id is not None:
                assistant_message_id = await self.store.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_content,
                    capability=capability_name,
                    events=assistant_events,
                    attachments=generated_attachments or None,
                    parent_message_id=new_user_message_id,
                )
            elif branch_parent_explicit:
                assistant_message_id = await self.store.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_content,
                    capability=capability_name,
                    events=assistant_events,
                    attachments=generated_attachments or None,
                    parent_message_id=branch_parent_id,
                )
            else:
                assistant_message_id = await self.store.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_content,
                    capability=capability_name,
                    events=assistant_events,
                    attachments=generated_attachments or None,
                )
            try:
                record_current_user_usage(
                    session_id=session_id,
                    turn_id=turn_id,
                    capability=capability_name,
                    provider=str(getattr(llm_config, "provider_name", "") or ""),
                    model=str(getattr(llm_config, "model", "") or ""),
                    summary=turn_usage_summary,
                )
            except Exception:
                logger.warning("Failed to record usage for turn %s", turn_id, exc_info=True)
            turn_status, turn_error = _resolve_turn_outcome(
                assistant_events,
                pending_done_event,
            )
            await self.store.update_turn_status(turn_id, turn_status, turn_error)
            if pending_done_event is None:
                pending_done_event = StreamEvent(
                    type=StreamEventType.DONE,
                    source=capability_name,
                    metadata={"status": turn_status},
                )
            else:
                pending_done_event.metadata = {
                    **pending_done_event.metadata,
                    "status": turn_status,
                }
            # Attach the persisted row ids so the frontend can reconcile its
            # optimistic (negative) message ids with a targeted in-place swap
            # instead of refetching and re-rendering the whole session.
            persisted_ids = {
                key: value
                for key, value in (
                    ("user_message_id", new_user_message_id),
                    ("assistant_message_id", assistant_message_id),
                )
                if value
            }
            if persisted_ids:
                pending_done_event.metadata = {**pending_done_event.metadata, **persisted_ids}
            await self._publish_live_event(execution, pending_done_event)
            stream_done_sent = True
            # DONE is part of the same persisted replay log as all preceding
            # events. Reconnects therefore observe the real terminal envelope
            # (including message ids), not a lossy synthesized substitute.
            await self._flush_buffered_events(execution)
            if not is_regenerate and turn_status == "completed":
                # Title generation is post-turn metadata. Keep it after DONE
                # so the composer and duration clock stop as soon as the
                # assistant answer is saved; the frontend keeps this socket
                # open briefly so the later ``session_meta`` title update can
                # still arrive.
                try:
                    await self._maybe_generate_session_title(
                        execution=execution,
                        session_id=session_id,
                        ui_language=str(payload.get("language", "en") or "en"),
                    )
                except Exception:
                    logger.debug("Failed to generate session title", exc_info=True)
            # Flush once every terminal/post-turn event (DONE, and the title
            # ``session_meta`` above) has been published, not before: a
            # client that reconnects after this task's ``finally`` pops
            # ``execution`` from ``_executions`` falls back entirely to this
            # persisted backlog, and ``subscribe_turn`` synthesises an
            # id-less DONE when it finds none there -- permanently orphaning
            # the just-persisted assistant reply from that client's
            # reconcile path (it can still see the message after a full
            # session reload, since the row itself is fine; only the
            # targeted in-place swap is unreachable).
            await self._flush_buffered_events(execution)
        except asyncio.CancelledError:
            if not stream_done_sent:
                await self._publish_live_event(
                    execution,
                    StreamEvent(
                        type=StreamEventType.ERROR,
                        source=capability_name,
                        content="Turn cancelled",
                        metadata={"turn_terminal": True, "status": "cancelled"},
                    ),
                )
                await self._publish_live_event(
                    execution,
                    StreamEvent(
                        type=StreamEventType.DONE,
                        source=capability_name,
                        metadata={"status": "cancelled"},
                    ),
                )
            with contextlib.suppress(Exception):
                await self._flush_buffered_events(execution)
            # Best-effort: persist what the turn already produced (streamed
            # answer text, trace events, generated files) so cancelling a
            # turn does not erase visible work — files the model created are
            # on disk either way and must stay reachable. Shielded because
            # we are already unwinding a cancellation. Every step is
            # suppressed separately so the status update below always runs —
            # a turn left "running" gets mislabelled as a restart orphan.
            partial_content = _persisted_answer()
            if partial_content or generated_attachments or assistant_events:
                with contextlib.suppress(Exception):
                    await asyncio.shield(
                        self.store.add_message(
                            session_id=session_id,
                            role="assistant",
                            content=partial_content,
                            capability=capability_name,
                            events=assistant_events,
                            attachments=generated_attachments or None,
                        )
                    )
            with contextlib.suppress(Exception):
                await self.store.update_turn_status(turn_id, "cancelled", "Turn cancelled")
            raise
        except Exception as exc:
            if stream_done_sent:
                logger.error(
                    "Post-stream persistence for turn %s failed: %s",
                    turn_id,
                    exc,
                    exc_info=True,
                )
                # Suppress each step separately: a flush failure must not
                # also skip the status update, or the turn stays "running"
                # forever and gets mislabelled as a server-restart orphan.
                with contextlib.suppress(Exception):
                    await self._flush_buffered_events(execution)
                with contextlib.suppress(Exception):
                    await self.store.update_turn_status(turn_id, "failed", str(exc))
            else:
                logger.error("Turn %s failed: %s", turn_id, exc, exc_info=True)
                await self._publish_live_event(
                    execution,
                    StreamEvent(
                        type=StreamEventType.ERROR,
                        source=capability_name,
                        content=str(exc),
                        metadata={"turn_terminal": True, "status": "failed"},
                    ),
                )
                await self._publish_live_event(
                    execution,
                    StreamEvent(
                        type=StreamEventType.DONE,
                        source=capability_name,
                        metadata={"status": "failed"},
                    ),
                )
                with contextlib.suppress(Exception):
                    await self._flush_buffered_events(execution)
                await self.store.update_turn_status(turn_id, "failed", str(exc))
        finally:
            if llm_scope_token is not None and reset_active_llm_selection is not None:
                reset_active_llm_selection(llm_scope_token)
            # Drop the reply queue first — any in-flight ``submit_user_reply``
            # that finds the queue gone will return ``False`` rather than
            # accumulating on a dead turn.
            self._reply_queues.pop(turn_id, None)
            if capability_name == "mastery_path":
                LearningStore = importlib.import_module("deeptutor.learning.storage").LearningStore
                # By turn, not by the path the turn started on: mastery_switch
                # can move a turn onto a different path mid-flight, and freeing
                # the original id would release someone else's lease while
                # leaking the one this turn actually holds.
                with contextlib.suppress(Exception):
                    await asyncio.shield(
                        asyncio.to_thread(LearningStore().release_leases_for_turn, turn_id)
                    )
            async with self._lock:
                current = self._executions.get(turn_id)
                if current is not None:
                    for subscriber in current.subscribers:
                        with contextlib.suppress(asyncio.QueueFull):
                            subscriber.queue.put_nowait(None)
                    self._executions.pop(turn_id, None)
            # A turn may have parsed large attachments or built substantial
            # temporary prompts/results. Reclaim after this coroutine returns,
            # outside the user-visible streaming path.
            schedule_memory_reclaim()

    async def _publish_mastery_path_change(
        self,
        execution: _TurnExecution,
        *,
        capability_name: str,
        started_on: str,
        ended_on: str,
    ) -> None:
        """Announce a path the turn moved onto, so the client stops lying."""
        if capability_name != "mastery_path" or not ended_on or ended_on == started_on:
            return
        await self._publish_live_event(
            execution,
            StreamEvent(
                type=StreamEventType.SESSION_META,
                source="turn_runtime",
                metadata={"mastery_path_id": ended_on},
            ),
        )

    async def _publish_live_event(
        self,
        execution: _TurnExecution,
        event: StreamEvent,
    ) -> dict[str, Any]:
        if event.type == StreamEventType.DONE and not event.metadata.get("status"):
            event.metadata = {**event.metadata, "status": "completed"}
        event.session_id = execution.session_id
        event.turn_id = execution.turn_id
        payload = event.to_dict()
        async with self._lock:
            current = self._executions.get(execution.turn_id, execution)
            seq = int(payload.get("seq") or 0)
            if seq <= 0:
                seq = current.next_seq
                current.next_seq += 1
                if current is not execution:
                    execution.next_seq = max(execution.next_seq, current.next_seq)
            else:
                current.next_seq = max(current.next_seq, seq + 1)
                execution.next_seq = max(execution.next_seq, seq + 1)
            payload["seq"] = seq
            current.events.append(payload)
            if current is not execution:
                execution.events.append(payload)
            subscribers = list(current.subscribers)
        for subscriber in subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                subscriber.queue.put_nowait(payload)
        return payload

    async def _maybe_generate_session_title(
        self,
        *,
        execution: _TurnExecution,
        session_id: str,
        ui_language: str,
    ) -> None:
        """Generate a short LLM-written title for a freshly-named session.

        Runs only when the session still carries the ``New conversation``
        sentinel — once a user manually renames the chat (or this method
        has already filled in a title), it short-circuits. Uses the LLM
        scope already active on the calling task, which is the user's
        currently selected model.
        """
        if not session_id:
            return
        session = await self.store.get_session(session_id)
        if not session:
            return
        current_title = str(session.get("title") or "").strip()
        if current_title and current_title != "New conversation":
            return

        messages = await self.store.get_messages(session_id)
        first_user = ""
        first_assistant = ""
        for m in messages:
            role = str(m.get("role") or "")
            content = str(m.get("content") or "").strip()
            if not content:
                continue
            if role == "user" and not first_user:
                first_user = content
            elif role == "assistant" and not first_assistant:
                first_assistant = content
            if first_user and first_assistant:
                break
        if not first_user or not first_assistant:
            return

        title = ""
        try:
            zh = str(ui_language or "").lower().startswith("zh")
            if zh:
                sys_prompt = (
                    "你需要为一段对话生成一个简洁的标题。"
                    "直接输出标题文本，不要引号、不要 Markdown 格式、"
                    '不要末尾标点、不要 "标题：" 这类前缀。'
                    "标题控制在 4-10 个汉字以内。"
                )
                user_prompt = (
                    "请基于以下对话生成标题：\n\n"
                    f"[用户]\n{_clip_text(first_user, 800)}\n\n"
                    f"[助手]\n{_clip_text(first_assistant, 1500)}"
                )
            else:
                sys_prompt = (
                    "You generate a concise, descriptive title for a "
                    "conversation. Output only the title as plain text "
                    "— no quotes, no markdown, no trailing punctuation, "
                    'no "Title:" prefix. Keep it 4-8 words.'
                )
                user_prompt = (
                    "Generate a title for this conversation:\n\n"
                    f"[User]\n{_clip_text(first_user, 800)}\n\n"
                    f"[Assistant]\n{_clip_text(first_assistant, 1500)}"
                )

            async def _collect_title() -> str:
                buf: list[str] = []
                async for c in llm_stream(
                    prompt=user_prompt,
                    system_prompt=sys_prompt,
                    temperature=0.3,
                    max_tokens=80,
                ):
                    buf.append(c)
                return "".join(buf)

            raw_title = await asyncio.wait_for(_collect_title(), timeout=20.0)
            title = _sanitize_session_title(raw_title)
        except asyncio.TimeoutError:
            logger.debug("Title LLM call timed out — falling back")
        except Exception:
            logger.debug("Title LLM call failed", exc_info=True)

        if not title:
            # Fallback: truncate the first user message so the sidebar
            # doesn't sit on "New conversation" indefinitely when the
            # title model errors out.
            title = first_user[:50] + ("..." if len(first_user) > 50 else "")

        if not title:
            return

        try:
            await self.store.update_session_title(session_id, title)
        except Exception:
            logger.debug("update_session_title failed", exc_info=True)
            return

        await self._publish_live_event(
            execution,
            StreamEvent(
                type=StreamEventType.SESSION_META,
                source="turn_runtime",
                stage="title",
                content=title,
                metadata={"title": title, "session_id": session_id},
            ),
        )

    async def _flush_buffered_events(self, execution: _TurnExecution) -> None:
        """Persist buffered turn events after the live stream has already drained."""
        async with execution.flush_lock:
            await self._flush_buffered_events_once(execution)

    async def _flush_buffered_events_once(self, execution: _TurnExecution) -> None:
        """One serialized persistence attempt for :meth:`_flush_buffered_events`."""
        if execution.events_flushed:
            return
        async with self._lock:
            events = list(execution.events)

        execution.events_persisted = await _flush_buffered_events(
            store=self.store,
            turn_id=execution.turn_id,
            capability=execution.capability,
            events=events,
            persisted_events=execution.persisted_events,
        )
        execution.events_flushed = execution.events_persisted


_runtime_lock = threading.Lock()
_runtime_instances: dict[str, TurnRuntimeManager] = {}


def get_turn_runtime_manager() -> TurnRuntimeManager:
    store = get_session_store()
    key = str(getattr(store, "db_path", id(store)))
    with _runtime_lock:
        if key not in _runtime_instances:
            _runtime_instances[key] = TurnRuntimeManager(store=store)
        return _runtime_instances[key]


__all__ = ["TurnRuntimeManager", "get_turn_runtime_manager"]
