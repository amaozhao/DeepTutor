import asyncio
from collections import deque
from collections.abc import AsyncGenerator
import contextlib
import json
import threading
import time
from typing import Any

from deeptutor.auth.context import current_user_id
from deeptutor.auth.resource_ids import validate_task_id
from deeptutor.logging import ProcessLogEvent, bind_log_context, capture_process_logs


def _format_sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


class KnowledgeTaskStreamManager:
    _instance: "KnowledgeTaskStreamManager | None" = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._lock = threading.Lock()
        self._buffers: dict[tuple[str | None, str], deque[dict[str, Any]]] = {}
        self._subscribers: dict[
            tuple[str | None, str], list[tuple[asyncio.Queue, asyncio.AbstractEventLoop]]
        ] = {}

    @classmethod
    def get_instance(cls) -> "KnowledgeTaskStreamManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _key(self, task_id: str, user_id: str | None = None) -> tuple[str | None, str]:
        safe_task_id = validate_task_id(task_id)
        owner = str(user_id or current_user_id() or "").strip()
        if not owner:
            try:
                from deeptutor.multi_user.context import get_current_user

                owner = str(get_current_user().id or "").strip()
            except Exception:
                owner = ""
        return owner or None, safe_task_id

    def ensure_task(self, task_id: str, user_id: str | None = None):
        key = self._key(task_id, user_id)
        with self._lock:
            self._buffers.setdefault(key, deque(maxlen=500))
            self._subscribers.setdefault(key, [])

    def emit(
        self, task_id: str, event: str, payload: dict[str, Any], user_id: str | None = None
    ):
        key = self._key(task_id, user_id)
        event_payload = {"event": event, "payload": payload}
        with self._lock:
            self._buffers.setdefault(key, deque(maxlen=500)).append(event_payload)
            subscribers = list(self._subscribers.get(key, []))

        for queue, loop in subscribers:
            try:
                loop.call_soon_threadsafe(self._queue_event, queue, event_payload)
            except RuntimeError:
                continue

    def emit_process_log(
        self, task_id: str, event: ProcessLogEvent, user_id: str | None = None
    ):
        payload = event.to_dict()
        payload.setdefault("context", {})["task_id"] = task_id
        self.emit(task_id, "process_log", payload, user_id=user_id)

    def emit_log(self, task_id: str, line: str, user_id: str | None = None):
        event = ProcessLogEvent(
            level="INFO",
            message=line,
            logger="deeptutor.knowledge.task",
            timestamp=time.time(),
            context={"task_id": task_id, "capability": "knowledge", "sink": "ui"},
        )
        self.emit_process_log(task_id, event, user_id=user_id)

    def emit_complete(
        self, task_id: str, detail: str = "Task completed", user_id: str | None = None
    ):
        self.emit(task_id, "complete", {"detail": detail, "task_id": task_id}, user_id=user_id)

    def emit_failed(
        self, task_id: str, detail: str, *, details: str | None = None, user_id: str | None = None
    ):
        payload: dict[str, Any] = {"detail": detail, "task_id": task_id}
        if details:
            payload["details"] = details
        self.emit(task_id, "failed", payload, user_id=user_id)

    def subscribe(
        self, task_id: str, user_id: str | None = None
    ) -> tuple[asyncio.Queue[dict[str, Any]], list[dict[str, Any]], asyncio.AbstractEventLoop]:
        key = self._key(task_id, user_id)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        loop = asyncio.get_running_loop()
        with self._lock:
            self._buffers.setdefault(key, deque(maxlen=500))
            self._subscribers.setdefault(key, []).append((queue, loop))
            backlog = list(self._buffers[key])
        return queue, backlog, loop

    def unsubscribe(
        self,
        task_id: str,
        queue: asyncio.Queue[dict[str, Any]],
        loop: asyncio.AbstractEventLoop,
        user_id: str | None = None,
    ):
        key = self._key(task_id, user_id)
        with self._lock:
            subscribers = self._subscribers.get(key, [])
            self._subscribers[key] = [
                (subscriber_queue, subscriber_loop)
                for subscriber_queue, subscriber_loop in subscribers
                if subscriber_queue is not queue or subscriber_loop is not loop
            ]

    async def stream(self, task_id: str, user_id: str | None = None) -> AsyncGenerator[str, None]:
        queue, backlog, loop = self.subscribe(task_id, user_id=user_id)
        try:
            for item in backlog:
                yield _format_sse(item["event"], item["payload"])

            if backlog and backlog[-1]["event"] in {"complete", "failed"}:
                return

            while True:
                item = await queue.get()
                yield _format_sse(item["event"], item["payload"])
                if item["event"] in {"complete", "failed"}:
                    break
        finally:
            self.unsubscribe(task_id, queue, loop, user_id=user_id)

    @staticmethod
    def _queue_event(queue: asyncio.Queue[dict[str, Any]], payload: dict[str, Any]):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass


@contextlib.contextmanager
def capture_task_logs(task_id: str, user_id: str | None = None):
    """Forward all logs bound to ``task_id`` into the task's SSE stream."""
    manager = KnowledgeTaskStreamManager.get_instance()
    manager.ensure_task(task_id, user_id=user_id)

    def emit(event: ProcessLogEvent) -> None:
        manager.emit_process_log(task_id, event, user_id=user_id)

    with bind_log_context(task_id=task_id, capability="knowledge", sink="ui"):
        with capture_process_logs(emit, task_id=task_id):
            yield


def get_task_stream_manager() -> KnowledgeTaskStreamManager:
    return KnowledgeTaskStreamManager.get_instance()
