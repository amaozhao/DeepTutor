"""Message and import SQL helpers for SQLite session storage."""

from __future__ import annotations

import sqlite3
import time
from typing import Any, Callable

JsonDumps = Callable[[Any], str]
JsonLoads = Callable[[str | None, Any], Any]


def add_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str,
    capability: str,
    events: list[dict[str, Any]] | None,
    attachments: list[dict[str, Any]] | None,
    metadata: dict[str, Any] | None,
    parent_message_id: int | str | None,
    *,
    json_dumps: JsonDumps,
) -> int:
    now = time.time()
    session = conn.execute("SELECT id, title FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if session is None:
        raise ValueError(f"Session not found: {session_id}")
    cur = conn.execute(
        """
        INSERT INTO messages (
            session_id, role, content, capability, events_json,
            attachments_json, metadata_json, created_at, parent_message_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            role,
            content or "",
            capability or "",
            json_dumps(events or []),
            json_dumps(attachments or []),
            json_dumps(metadata or {}),
            now,
            int(parent_message_id) if parent_message_id is not None else None,
        ),
    )
    conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    conn.commit()
    return int(cur.lastrowid)


def last_message_id(conn: sqlite3.Connection, session_id: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return int(row["id"]) if row is not None else None


def backfill_import_meta(
    conn: sqlite3.Connection,
    session_id: str,
    current_prefs_json: str | None,
    incoming_prefs: dict[str, Any],
    *,
    json_dumps: JsonDumps,
    json_loads: JsonLoads,
) -> bool:
    incoming_import = (incoming_prefs or {}).get("import") or {}
    if not incoming_import:
        return False
    prefs = json_loads(current_prefs_json, {})
    if not isinstance(prefs, dict):
        prefs = {}
    meta = dict(prefs.get("import") or {})
    changed = False
    for key in ("agent_id", "agent_name", "source_cwd"):
        value = incoming_import.get(key)
        if value and meta.get(key) != value:
            meta[key] = value
            changed = True
    if not changed:
        return False
    prefs["import"] = meta
    conn.execute(
        "UPDATE sessions SET preferences_json = ? WHERE id = ?",
        (json_dumps(prefs), session_id),
    )
    return True


def import_session(
    conn: sqlite3.Connection,
    session_id: str,
    title: str,
    created_at: float,
    updated_at: float,
    preferences: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    json_dumps: JsonDumps,
    json_loads: JsonLoads,
) -> dict[str, Any]:
    existing = conn.execute(
        "SELECT preferences_json FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if existing is not None:
        updated = backfill_import_meta(
            conn,
            session_id,
            existing["preferences_json"],
            preferences,
            json_dumps=json_dumps,
            json_loads=json_loads,
        )
        if updated:
            conn.commit()
        return {
            "session_id": session_id,
            "imported": False,
            "updated": updated,
            "message_count": 0,
        }
    safe_title = (title or "").strip()[:100] or "Imported conversation"
    conn.execute(
        """
        INSERT INTO sessions (
            id, title, created_at, updated_at,
            compressed_summary, summary_up_to_msg_id, preferences_json
        ) VALUES (?, ?, ?, ?, '', 0, ?)
        """,
        (session_id, safe_title, created_at, updated_at, json_dumps(preferences or {})),
    )
    prev_id: int | None = None
    count = 0
    for msg in messages:
        cur = conn.execute(
            """
            INSERT INTO messages (
                session_id, role, content, capability, events_json,
                attachments_json, metadata_json, created_at, parent_message_id
            ) VALUES (?, ?, ?, '', '[]', '[]', ?, ?, ?)
            """,
            (
                session_id,
                msg.get("role") or "user",
                msg.get("content") or "",
                json_dumps(msg.get("metadata") or {}),
                float(msg.get("created_at") or created_at),
                prev_id,
            ),
        )
        prev_id = int(cur.lastrowid)
        count += 1
    conn.commit()
    return {"session_id": session_id, "imported": True, "message_count": count}


def delete_message(conn: sqlite3.Connection, message_id: int | str) -> bool:
    cur = conn.execute("DELETE FROM messages WHERE id = ?", (int(message_id),))
    conn.commit()
    return cur.rowcount > 0


def delete_turn_by_message(
    conn: sqlite3.Connection,
    session_id: str,
    message_id: int,
    *,
    json_loads: JsonLoads,
) -> dict[str, Any]:
    msg = conn.execute(
        """
        SELECT id, session_id, role, attachments_json, created_at
        FROM messages
        WHERE id = ?
        """,
        (int(message_id),),
    ).fetchone()
    if msg is None or msg["session_id"] != session_id:
        return {
            "deleted": False,
            "attachment_ids": [],
            "turn_id": None,
            "was_running": False,
        }

    role = msg["role"]
    paired_msg = None
    if role == "user":
        paired_msg = conn.execute(
            """
            SELECT id, session_id, role, attachments_json, created_at
            FROM messages
            WHERE session_id = ? AND role = 'assistant' AND id > ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (session_id, int(message_id)),
        ).fetchone()
    elif role == "assistant":
        paired_msg = conn.execute(
            """
            SELECT id, session_id, role, attachments_json, created_at
            FROM messages
            WHERE session_id = ? AND role = 'user' AND id < ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id, int(message_id)),
        ).fetchone()

    user_msg = msg if role == "user" else paired_msg
    turn_id = None
    was_running = False
    if user_msg is not None:
        user_created_at = user_msg["created_at"]
        turn_row = conn.execute(
            """
            SELECT id, status
            FROM turns
            WHERE session_id = ? AND created_at >= ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (session_id, user_created_at),
        ).fetchone()
        if turn_row is not None:
            turn_id = turn_row["id"]
            was_running = turn_row["status"] == "running"

    if was_running:
        return {
            "deleted": False,
            "attachment_ids": [],
            "turn_id": turn_id,
            "was_running": True,
        }

    attachment_ids: list[str] = []
    for candidate in [msg, paired_msg]:
        if candidate is not None:
            attachments = json_loads(candidate["attachments_json"], [])
            for attachment in attachments:
                attachment_id = attachment.get("id") or attachment.get("attachment_id")
                if attachment_id:
                    attachment_ids.append(attachment_id)

    if turn_id is not None:
        conn.execute("DELETE FROM turn_events WHERE turn_id = ?", (turn_id,))
        conn.execute("DELETE FROM turns WHERE id = ?", (turn_id,))

    ids_to_delete = [int(message_id)]
    if paired_msg is not None:
        ids_to_delete.append(int(paired_msg["id"]))
    conn.execute(
        f"DELETE FROM messages WHERE id IN ({','.join('?' * len(ids_to_delete))})",  # nosec B608
        tuple(ids_to_delete),
    )

    session_row = conn.execute(
        "SELECT summary_up_to_msg_id FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if session_row is not None:
        summary_up_to = int(session_row["summary_up_to_msg_id"])
        if any(mid <= summary_up_to for mid in ids_to_delete):
            conn.execute(
                "UPDATE sessions SET summary_up_to_msg_id = 0 WHERE id = ?",
                (session_id,),
            )

    conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (time.time(), session_id))
    conn.commit()
    return {
        "deleted": True,
        "attachment_ids": attachment_ids,
        "turn_id": turn_id,
        "was_running": was_running,
    }


def serialize_message(row: sqlite3.Row, *, json_loads: JsonLoads) -> dict[str, Any]:
    row_keys = row.keys()
    parent_id = row["parent_message_id"] if "parent_message_id" in row_keys else None
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "role": row["role"],
        "content": row["content"],
        "capability": row["capability"] or "",
        "events": json_loads(row["events_json"], []),
        "attachments": json_loads(row["attachments_json"], []),
        "metadata": json_loads(row["metadata_json"], {}),
        "created_at": row["created_at"],
        "parent_message_id": int(parent_id) if parent_id is not None else None,
    }


def get_last_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str | None,
    *,
    json_loads: JsonLoads,
) -> dict[str, Any] | None:
    if role is None:
        row = conn.execute(
            """
            SELECT id, session_id, role, content, capability, events_json,
                   attachments_json, metadata_json, created_at, parent_message_id
            FROM messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id, session_id, role, content, capability, events_json,
                   attachments_json, metadata_json, created_at, parent_message_id
            FROM messages
            WHERE session_id = ? AND role = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id, role),
        ).fetchone()
    return serialize_message(row, json_loads=json_loads) if row is not None else None


def get_messages(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    json_loads: JsonLoads,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, session_id, role, content, capability, events_json,
               attachments_json, metadata_json, created_at, parent_message_id
        FROM messages
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,),
    ).fetchall()
    return [serialize_message(row, json_loads=json_loads) for row in rows]


def get_message_path(
    conn: sqlite3.Connection,
    session_id: str,
    leaf_message_id: int,
    *,
    json_loads: JsonLoads,
) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    current: int | None = int(leaf_message_id)
    safety = 10_000
    while current is not None and safety > 0:
        row = conn.execute(
            """
            SELECT id, session_id, role, content, capability, events_json,
                   attachments_json, metadata_json, created_at, parent_message_id
            FROM messages
            WHERE id = ? AND session_id = ?
            """,
            (current, session_id),
        ).fetchone()
        if row is None:
            break
        chain.append(serialize_message(row, json_loads=json_loads))
        parent = row["parent_message_id"]
        current = int(parent) if parent is not None else None
        safety -= 1
    chain.reverse()
    return chain


def get_messages_for_context(
    conn: sqlite3.Connection,
    session_id: str,
    leaf_message_id: int | None = None,
) -> list[dict[str, Any]]:
    if leaf_message_id is None:
        rows = conn.execute(
            """
            SELECT id, role, content
            FROM messages
            WHERE session_id = ?
              AND role IN ('user', 'assistant', 'system')
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"] or "",
            }
            for row in rows
        ]
    chain: list[dict[str, Any]] = []
    current: int | None = int(leaf_message_id)
    safety = 10_000
    while current is not None and safety > 0:
        row = conn.execute(
            """
            SELECT id, role, content, parent_message_id
            FROM messages
            WHERE id = ? AND session_id = ?
              AND role IN ('user', 'assistant', 'system')
            """,
            (current, session_id),
        ).fetchone()
        if row is None:
            break
        chain.append(
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"] or "",
            }
        )
        parent = row["parent_message_id"]
        current = int(parent) if parent is not None else None
        safety -= 1
    chain.reverse()
    return chain
