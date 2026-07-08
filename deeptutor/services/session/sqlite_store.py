"""
SQLite-backed unified chat session store.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any
import uuid

from deeptutor.services.path_service import get_path_service
from deeptutor.services.session import messages as message_sql
from deeptutor.services.session import notebook as notebook_sql
from deeptutor.services.session import turns as turn_sql
from deeptutor.services.session.schema import initialize_schema


def _json_dumps(value: Any) -> str:
    # default=str: a single non-serializable object inside an event payload
    # (e.g. a dataclass smuggled into tool args) must degrade to its repr,
    # never kill message/event persistence for the whole turn.
    return json.dumps(value, ensure_ascii=False, default=str)


# Sentinel so ``add_message`` can distinguish "caller wants the legacy
# auto-pick-latest-message default" from "caller explicitly wants the
# message attached at the session root (parent = NULL)". Both surface as
# ``None`` in the public ``parent_message_id`` arg, which is why we need
# a sentinel separate from None.
class _Unset:
    pass


_PARENT_AUTO = _Unset()


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


# Imported conversations share the session tables with native chats but carry
# this id prefix as their discriminator (see ``SQLiteSessionStore._WHERE_*``).
_IMPORTED_ID_PREFIX = "imported_"
_ID_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def make_imported_session_id(source: str, external_id: str) -> str:
    """Build a deterministic, dedup-friendly id for an imported conversation.

    ``source`` (e.g. ``claude_code``/``codex``) namespaces the original
    session uuid so two tools that happen to reuse an id never collide; the
    determinism is what makes re-importing the same folder idempotent.
    """
    src = _ID_SAFE.sub("-", (source or "external").strip()) or "external"
    ext = _ID_SAFE.sub("-", (external_id or "").strip()) or uuid.uuid4().hex
    return f"{_IMPORTED_ID_PREFIX}{src}_{ext}"


class SQLiteSessionStore:
    """Persist unified chat sessions and messages in a SQLite database."""

    def __init__(self, db_path: Path | None = None) -> None:
        path_service = get_path_service()
        self.db_path = db_path or path_service.get_chat_history_db()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_db(path_service)
        self._lock = asyncio.Lock()
        self._initialize()

    def _migrate_legacy_db(self, path_service) -> None:
        """Move the legacy ``data/chat_history.db`` into ``data/user/`` once."""
        legacy_path = path_service.project_root / "data" / "chat_history.db"
        if self.db_path.exists() or not legacy_path.exists() or legacy_path == self.db_path:
            return
        try:
            os.replace(legacy_path, self.db_path)
        except OSError:
            # Fall back to leaving the legacy DB in place if an OS-level move
            # is not possible; the new DB path will be initialized empty.
            pass

    def _initialize(self) -> None:
        with self._connect() as conn:
            initialize_schema(conn)

    async def _run(self, fn, *args):
        async with self._lock:
            return await asyncio.to_thread(fn, *args)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # sqlite3.Connection's own context manager commits/rolls back but does
        # NOT close the connection — so naked `with sqlite3.connect(...)` leaks
        # one FD per call until GC. Wrap it so each call site gets both
        # transaction semantics and deterministic close. The inner `with conn`
        # commits on clean exit and rolls back on exception, so call sites do
        # NOT need an explicit conn.commit() (any remaining ones are no-ops).
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _create_session_sync(
        self,
        title: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        resolved_id = session_id or f"unified_{int(now * 1000)}_{uuid.uuid4().hex[:8]}"
        resolved_title = (title or "New conversation").strip() or "New conversation"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, title, created_at, updated_at,
                    compressed_summary, summary_up_to_msg_id
                )
                VALUES (?, ?, ?, ?, '', 0)
                """,
                (resolved_id, resolved_title[:100], now, now),
            )
            conn.commit()
        return {
            "id": resolved_id,
            "session_id": resolved_id,
            "title": resolved_title[:100],
            "created_at": now,
            "updated_at": now,
            "compressed_summary": "",
            "summary_up_to_msg_id": 0,
        }

    async def create_session(
        self,
        title: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._run(self._create_session_sync, title, session_id)

    def _get_session_sync(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    s.id,
                    s.title,
                    s.created_at,
                    s.updated_at,
                    s.compressed_summary,
                    s.summary_up_to_msg_id,
                    s.preferences_json,
                    COALESCE(
                        (
                            SELECT t.status
                            FROM turns t
                            WHERE t.session_id = s.id
                            ORDER BY t.updated_at DESC
                            LIMIT 1
                        ),
                        'idle'
                    ) AS status,
                    COALESCE(
                        (
                            SELECT t.id
                            FROM turns t
                            WHERE t.session_id = s.id AND t.status = 'running'
                            ORDER BY t.updated_at DESC
                            LIMIT 1
                        ),
                        ''
                    ) AS active_turn_id,
                    COALESCE(
                        (
                            SELECT t.capability
                            FROM turns t
                            WHERE t.session_id = s.id
                            ORDER BY t.updated_at DESC
                            LIMIT 1
                        ),
                        ''
                    ) AS capability
                FROM sessions
                s
                WHERE s.id = ?
                """,
                (session_id,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["session_id"] = payload["id"]
        payload["preferences"] = _json_loads(payload.pop("preferences_json", ""), {})
        return payload

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return await self._run(self._get_session_sync, session_id)

    async def ensure_session(
        self,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if session_id:
            session = await self.get_session(session_id)
            if session is not None:
                return session
        return await self.create_session()

    def _create_turn_sync(self, session_id: str, capability: str = "") -> dict[str, Any]:
        with self._connect() as conn:
            return turn_sql.create_turn(conn, session_id, capability)

    async def create_turn(self, session_id: str, capability: str = "") -> dict[str, Any]:
        return await self._run(self._create_turn_sync, session_id, capability)

    def _get_turn_sync(self, turn_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            return turn_sql.get_turn(conn, turn_id)

    async def get_turn(self, turn_id: str) -> dict[str, Any] | None:
        return await self._run(self._get_turn_sync, turn_id)

    def _get_active_turn_sync(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            return turn_sql.get_active_turn(conn, session_id)

    async def get_active_turn(self, session_id: str) -> dict[str, Any] | None:
        return await self._run(self._get_active_turn_sync, session_id)

    def _list_active_turns_sync(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return turn_sql.list_active_turns(conn, session_id)

    async def list_active_turns(self, session_id: str) -> list[dict[str, Any]]:
        return await self._run(self._list_active_turns_sync, session_id)

    def _update_turn_status_sync(self, turn_id: str, status: str, error: str = "") -> bool:
        with self._connect() as conn:
            return turn_sql.update_turn_status(conn, turn_id, status, error)

    async def update_turn_status(self, turn_id: str, status: str, error: str = "") -> bool:
        return await self._run(self._update_turn_status_sync, turn_id, status, error)

    def _append_turn_event_sync(self, turn_id: str, event: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            return turn_sql.append_turn_event(conn, turn_id, event, json_dumps=_json_dumps)

    async def append_turn_event(self, turn_id: str, event: dict[str, Any]) -> dict[str, Any]:
        return await self._run(self._append_turn_event_sync, turn_id, event)

    def _get_turn_events_sync(self, turn_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return turn_sql.get_turn_events(conn, turn_id, after_seq, json_loads=_json_loads)

    async def get_turn_events(self, turn_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        return await self._run(self._get_turn_events_sync, turn_id, after_seq)

    def _update_session_title_sync(self, session_id: str, title: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE sessions
                SET title = ?, updated_at = ?
                WHERE id = ?
                """,
                ((title.strip() or "New conversation")[:100], time.time(), session_id),
            )
            conn.commit()
        return cur.rowcount > 0

    async def update_session_title(self, session_id: str, title: str) -> bool:
        return await self._run(self._update_session_title_sync, session_id, title)

    def _delete_session_sync(self, session_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        return cur.rowcount > 0

    async def delete_session(self, session_id: str) -> bool:
        return await self._run(self._delete_session_sync, session_id)

    def _add_message_sync(
        self,
        session_id: str,
        role: str,
        content: str,
        capability: str = "",
        events: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        parent_message_id: int | str | None | _Unset = _PARENT_AUTO,
    ) -> int:
        with self._connect() as conn:
            resolved_parent_id: int | None
            if isinstance(parent_message_id, _Unset):
                resolved_parent_id = message_sql.last_message_id(conn, session_id)
            else:
                resolved_parent_id = (
                    int(parent_message_id) if parent_message_id is not None else None
                )
            return message_sql.add_message(
                conn,
                session_id,
                role,
                content,
                capability,
                events,
                attachments,
                metadata,
                resolved_parent_id,
                json_dumps=_json_dumps,
            )

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        capability: str = "",
        events: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        parent_message_id: int | str | None | _Unset = _PARENT_AUTO,
    ) -> int:
        return await self._run(
            self._add_message_sync,
            session_id,
            role,
            content,
            capability,
            events,
            attachments,
            metadata,
            parent_message_id,
        )

    def _import_session_sync(
        self,
        session_id: str,
        title: str,
        created_at: float,
        updated_at: float,
        preferences: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        with self._connect() as conn:
            return message_sql.import_session(
                conn,
                session_id,
                title,
                created_at,
                updated_at,
                preferences,
                messages,
                json_dumps=_json_dumps,
                json_loads=_json_loads,
            )

    async def import_session(
        self,
        session_id: str,
        title: str,
        created_at: float,
        updated_at: float,
        preferences: dict[str, Any] | None,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Persist a pre-existing conversation (imported from an external CLI
        such as Claude Code or Codex) as a normal session, so the chat loop can
        re-open and continue it. ``session_id`` must carry the ``imported_``
        prefix (see :data:`_IMPORTED_ID_PREFIX`). Idempotent by id: a session
        already present is left untouched.
        """
        return await self._run(
            self._import_session_sync,
            session_id,
            title,
            created_at,
            updated_at,
            preferences or {},
            messages,
        )

    def _delete_message_sync(self, message_id: int | str) -> bool:
        with self._connect() as conn:
            return message_sql.delete_message(conn, message_id)

    async def delete_message(self, message_id: int | str) -> bool:
        return await self._run(self._delete_message_sync, message_id)

    def _delete_turn_by_message_sync(self, session_id: str, message_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            return message_sql.delete_turn_by_message(
                conn,
                session_id,
                message_id,
                json_loads=_json_loads,
            )

    async def delete_turn_by_message(self, session_id: str, message_id: int) -> dict[str, Any]:
        return await self._run(self._delete_turn_by_message_sync, session_id, message_id)

    def _get_last_message_sync(
        self, session_id: str, role: str | None = None
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            return message_sql.get_last_message(conn, session_id, role, json_loads=_json_loads)

    async def get_last_message(
        self, session_id: str, role: str | None = None
    ) -> dict[str, Any] | None:
        return await self._run(self._get_last_message_sync, session_id, role)

    def _serialize_message(self, row: sqlite3.Row) -> dict[str, Any]:
        return message_sql.serialize_message(row, json_loads=_json_loads)

    def _get_messages_sync(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return message_sql.get_messages(conn, session_id, json_loads=_json_loads)

    def _get_message_path_sync(self, session_id: str, leaf_message_id: int) -> list[dict[str, Any]]:
        """Return the chain of messages from the session root down to
        ``leaf_message_id`` (inclusive), in chronological order.

        Used by the turn runtime to build LLM context for a branched
        re-run: only ancestors of the new user message are included, so
        sibling branches at any depth are excluded.
        """
        with self._connect() as conn:
            return message_sql.get_message_path(
                conn,
                session_id,
                leaf_message_id,
                json_loads=_json_loads,
            )

    async def get_message_path(self, session_id: str, leaf_message_id: int) -> list[dict[str, Any]]:
        return await self._run(self._get_message_path_sync, session_id, int(leaf_message_id))

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        return await self._run(self._get_messages_sync, session_id)

    def _get_messages_for_context_sync(
        self, session_id: str, leaf_message_id: int | None = None
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return message_sql.get_messages_for_context(conn, session_id, leaf_message_id)

    async def get_messages_for_context(
        self, session_id: str, leaf_message_id: int | None = None
    ) -> list[dict[str, Any]]:
        return await self._run(self._get_messages_for_context_sync, session_id, leaf_message_id)

    # Imported conversations live in the same tables as native chats (so the
    # chat loop can re-open and continue them) but carry an ``imported_`` id
    # prefix. That prefix is the discriminator — it travels with the primary
    # key, so we filter on it instead of adding a column + migration.
    _SESSION_SUMMARY_SQL = """
        SELECT
            s.id,
            s.title,
            s.created_at,
            s.updated_at,
            s.compressed_summary,
            s.summary_up_to_msg_id,
            s.preferences_json,
            COUNT(m.id) AS message_count,
            COALESCE(
                (SELECT t.status FROM turns t WHERE t.session_id = s.id
                 ORDER BY t.updated_at DESC LIMIT 1),
                'idle'
            ) AS status,
            COALESCE(
                (SELECT t.id FROM turns t WHERE t.session_id = s.id AND t.status = 'running'
                 ORDER BY t.updated_at DESC LIMIT 1),
                ''
            ) AS active_turn_id,
            COALESCE(
                (SELECT t.capability FROM turns t WHERE t.session_id = s.id
                 ORDER BY t.updated_at DESC LIMIT 1),
                ''
            ) AS capability,
            COALESCE(
                (SELECT m2.content FROM messages m2
                 WHERE m2.session_id = s.id AND TRIM(COALESCE(m2.content, '')) != ''
                 ORDER BY m2.id DESC LIMIT 1),
                ''
            ) AS last_message
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id
        {where}
        GROUP BY s.id
        ORDER BY s.updated_at DESC
        LIMIT ? OFFSET ?
    """

    # ``ESCAPE '\'`` makes the underscore in ``imported_`` literal rather than
    # the LIKE single-char wildcard.
    _WHERE_NATIVE = r"WHERE s.id NOT LIKE 'imported\_%' ESCAPE '\'"
    _WHERE_IMPORTED = r"WHERE s.id LIKE 'imported\_%' ESCAPE '\'"

    def _list_session_summaries_sync(
        self, where_sql: str, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                self._SESSION_SUMMARY_SQL.format(where=where_sql),
                (limit, offset),
            ).fetchall()
        sessions = []
        for row in rows:
            payload = dict(row)
            payload["session_id"] = payload["id"]
            payload["preferences"] = _json_loads(payload.pop("preferences_json", ""), {})
            sessions.append(payload)
        return sessions

    def _list_sessions_sync(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        # Native chats only — imported histories surface under their own
        # Space category, not the regular history list.
        return self._list_session_summaries_sync(self._WHERE_NATIVE, limit, offset)

    def _list_imported_sessions_sync(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._list_session_summaries_sync(self._WHERE_IMPORTED, limit, offset)

    async def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return await self._run(self._list_sessions_sync, limit, offset)

    async def list_imported_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return await self._run(self._list_imported_sessions_sync, limit, offset)

    def _update_summary_sync(self, session_id: str, summary: str, up_to_msg_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE sessions
                SET compressed_summary = ?, summary_up_to_msg_id = ?, updated_at = updated_at
                WHERE id = ?
                """,
                (summary, max(0, int(up_to_msg_id)), session_id),
            )
            conn.commit()
        return cur.rowcount > 0

    async def update_summary(self, session_id: str, summary: str, up_to_msg_id: int) -> bool:
        return await self._run(self._update_summary_sync, session_id, summary, up_to_msg_id)

    def _update_session_preferences_sync(
        self, session_id: str, preferences: dict[str, Any]
    ) -> bool:
        with self._connect() as conn:
            current = conn.execute(
                "SELECT preferences_json FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if current is None:
                return False
            merged = {
                **_json_loads(current["preferences_json"], {}),
                **(preferences or {}),
            }
            cur = conn.execute(
                """
                UPDATE sessions
                SET preferences_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (_json_dumps(merged), time.time(), session_id),
            )
            conn.commit()
        return cur.rowcount > 0

    async def update_session_preferences(
        self, session_id: str, preferences: dict[str, Any]
    ) -> bool:
        return await self._run(self._update_session_preferences_sync, session_id, preferences)

    async def get_session_with_messages(self, session_id: str) -> dict[str, Any] | None:
        session = await self.get_session(session_id)
        if session is None:
            return None
        session["messages"] = await self.get_messages(session_id)
        session["active_turns"] = await self.list_active_turns(session_id)
        return session

    # ── Notebook entries ──────────────────────────────────────────────

    def _upsert_notebook_entries_sync(self, session_id: str, items: list[dict[str, Any]]) -> int:
        with self._connect() as conn:
            return notebook_sql.upsert_entries(
                conn,
                session_id,
                items,
                json_dumps=_json_dumps,
            )

    async def upsert_notebook_entries(self, session_id: str, items: list[dict[str, Any]]) -> int:
        return await self._run(self._upsert_notebook_entries_sync, session_id, items)

    @staticmethod
    def _serialize_notebook_entry(row: sqlite3.Row) -> dict[str, Any]:
        return notebook_sql.serialize_entry(row, json_loads=_json_loads)

    def _list_notebook_entries_sync(
        self,
        category_id: int | None,
        bookmarked: bool | None,
        is_correct: bool | None,
        limit: int,
        offset: int,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            return notebook_sql.list_entries(
                conn,
                category_id,
                bookmarked,
                is_correct,
                limit,
                offset,
                session_id,
                json_loads=_json_loads,
            )

    async def list_notebook_entries(
        self,
        category_id: int | None = None,
        bookmarked: bool | None = None,
        is_correct: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._run(
            self._list_notebook_entries_sync,
            category_id,
            bookmarked,
            is_correct,
            limit,
            offset,
            session_id,
        )

    def _get_notebook_entry_sync(self, entry_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            return notebook_sql.get_entry(conn, entry_id, json_loads=_json_loads)

    async def get_notebook_entry(self, entry_id: int) -> dict[str, Any] | None:
        return await self._run(self._get_notebook_entry_sync, entry_id)

    def _find_notebook_entry_sync(
        self,
        session_id: str,
        question_id: str,
        turn_id: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            return notebook_sql.find_entry(
                conn,
                session_id,
                question_id,
                turn_id,
                json_loads=_json_loads,
            )

    async def find_notebook_entry(
        self,
        session_id: str,
        question_id: str,
        turn_id: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._run(self._find_notebook_entry_sync, session_id, question_id, turn_id)

    def _update_notebook_entry_sync(self, entry_id: int, updates: dict[str, Any]) -> bool:
        with self._connect() as conn:
            return notebook_sql.update_entry(conn, entry_id, updates)

    async def update_notebook_entry(self, entry_id: int, updates: dict[str, Any]) -> bool:
        return await self._run(self._update_notebook_entry_sync, entry_id, updates)

    def _delete_notebook_entry_sync(self, entry_id: int) -> bool:
        with self._connect() as conn:
            return notebook_sql.delete_entry(conn, entry_id)

    async def delete_notebook_entry(self, entry_id: int) -> bool:
        return await self._run(self._delete_notebook_entry_sync, entry_id)

    # ── Notebook categories ────────────────────────────────────────

    def _create_category_sync(self, name: str) -> dict[str, Any]:
        with self._connect() as conn:
            return notebook_sql.create_category(conn, name)

    async def create_category(self, name: str) -> dict[str, Any]:
        return await self._run(self._create_category_sync, name)

    def _list_categories_sync(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return notebook_sql.list_categories(conn)

    async def list_categories(self) -> list[dict[str, Any]]:
        return await self._run(self._list_categories_sync)

    def _rename_category_sync(self, category_id: int, name: str) -> bool:
        with self._connect() as conn:
            return notebook_sql.rename_category(conn, category_id, name)

    async def rename_category(self, category_id: int, name: str) -> bool:
        return await self._run(self._rename_category_sync, category_id, name)

    def _delete_category_sync(self, category_id: int) -> bool:
        with self._connect() as conn:
            return notebook_sql.delete_category(conn, category_id)

    async def delete_category(self, category_id: int) -> bool:
        return await self._run(self._delete_category_sync, category_id)

    def _add_entry_to_category_sync(self, entry_id: int, category_id: int) -> bool:
        with self._connect() as conn:
            return notebook_sql.add_entry_to_category(conn, entry_id, category_id)

    async def add_entry_to_category(self, entry_id: int, category_id: int) -> bool:
        return await self._run(self._add_entry_to_category_sync, entry_id, category_id)

    def _remove_entry_from_category_sync(self, entry_id: int, category_id: int) -> bool:
        with self._connect() as conn:
            return notebook_sql.remove_entry_from_category(conn, entry_id, category_id)

    async def remove_entry_from_category(self, entry_id: int, category_id: int) -> bool:
        return await self._run(self._remove_entry_from_category_sync, entry_id, category_id)

    def _get_entry_categories_sync(self, entry_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return notebook_sql.get_entry_categories(conn, entry_id)

    async def get_entry_categories(self, entry_id: int) -> list[dict[str, Any]]:
        return await self._run(self._get_entry_categories_sync, entry_id)


_instances: dict[str, SQLiteSessionStore] = {}


def get_sqlite_session_store() -> SQLiteSessionStore:
    db_path = get_path_service().get_chat_history_db().resolve()
    key = str(db_path)
    if key not in _instances:
        _instances[key] = SQLiteSessionStore(db_path=db_path)
    return _instances[key]


__all__ = ["SQLiteSessionStore", "get_sqlite_session_store", "make_imported_session_id"]
