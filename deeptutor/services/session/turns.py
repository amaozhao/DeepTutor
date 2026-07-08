"""Turn and turn-event SQL helpers for SQLite session storage."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
import time
from typing import Any, Callable
import uuid

JsonDumps = Callable[[Any], str]
JsonLoads = Callable[[str | None, Any], Any]


@dataclass
class TurnRecord:
    id: str
    session_id: str
    capability: str
    status: str
    error: str
    created_at: float
    updated_at: float
    finished_at: float | None
    last_seq: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "turn_id": self.id,
            "session_id": self.session_id,
            "capability": self.capability,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "last_seq": self.last_seq,
        }


def serialize_turn(row: sqlite3.Row) -> dict[str, Any]:
    return TurnRecord(
        id=row["id"],
        session_id=row["session_id"],
        capability=row["capability"] or "",
        status=row["status"] or "running",
        error=row["error"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finished_at=row["finished_at"],
        last_seq=row["last_seq"] if "last_seq" in row.keys() else 0,
    ).to_dict()


def create_turn(conn: sqlite3.Connection, session_id: str, capability: str = "") -> dict[str, Any]:
    now = time.time()
    turn_id = f"turn_{int(now * 1000)}_{uuid.uuid4().hex[:10]}"
    session = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if session is None:
        raise ValueError(f"Session not found: {session_id}")
    active = conn.execute(
        """
        SELECT id
        FROM turns
        WHERE session_id = ? AND status = 'running'
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    if active is not None:
        raise RuntimeError(f"Session already has an active turn: {active['id']}")
    conn.execute(
        """
        INSERT INTO turns (id, session_id, capability, status, error, created_at, updated_at, finished_at)
        VALUES (?, ?, ?, 'running', '', ?, ?, NULL)
        """,
        (turn_id, session_id, capability or "", now, now),
    )
    conn.commit()
    return {
        "id": turn_id,
        "turn_id": turn_id,
        "session_id": session_id,
        "capability": capability or "",
        "status": "running",
        "error": "",
        "created_at": now,
        "updated_at": now,
        "finished_at": None,
        "last_seq": 0,
    }


def get_turn(conn: sqlite3.Connection, turn_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            t.*,
            COALESCE((SELECT MAX(seq) FROM turn_events te WHERE te.turn_id = t.id), 0) AS last_seq
        FROM turns t
        WHERE t.id = ?
        """,
        (turn_id,),
    ).fetchone()
    return serialize_turn(row) if row is not None else None


def get_active_turn(conn: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            t.*,
            COALESCE((SELECT MAX(seq) FROM turn_events te WHERE te.turn_id = t.id), 0) AS last_seq
        FROM turns t
        WHERE t.session_id = ? AND t.status = 'running'
        ORDER BY t.updated_at DESC
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    return serialize_turn(row) if row is not None else None


def list_active_turns(conn: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            t.*,
            COALESCE((SELECT MAX(seq) FROM turn_events te WHERE te.turn_id = t.id), 0) AS last_seq
        FROM turns t
        WHERE t.session_id = ? AND t.status = 'running'
        ORDER BY t.updated_at DESC
        """,
        (session_id,),
    ).fetchall()
    return [serialize_turn(row) for row in rows]


def update_turn_status(
    conn: sqlite3.Connection,
    turn_id: str,
    status: str,
    error: str = "",
) -> bool:
    now = time.time()
    finished_at = now if status in {"completed", "failed", "cancelled"} else None
    cur = conn.execute(
        """
        UPDATE turns
        SET status = ?, error = ?, updated_at = ?, finished_at = ?
        WHERE id = ?
        """,
        (status, error or "", now, finished_at, turn_id),
    )
    conn.commit()
    return cur.rowcount > 0


def append_turn_event(
    conn: sqlite3.Connection,
    turn_id: str,
    event: dict[str, Any],
    *,
    json_dumps: JsonDumps,
) -> dict[str, Any]:
    now = time.time()
    turn = conn.execute("SELECT id, session_id FROM turns WHERE id = ?", (turn_id,)).fetchone()
    if turn is None:
        raise ValueError(f"Turn not found: {turn_id}")
    provided_seq = int(event.get("seq") or 0)
    if provided_seq > 0:
        seq = provided_seq
    else:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) AS last_seq FROM turn_events WHERE turn_id = ?",
            (turn_id,),
        ).fetchone()
        seq = int(row["last_seq"]) + 1 if row else 1
    payload = dict(event)
    payload["seq"] = seq
    payload["turn_id"] = payload.get("turn_id") or turn_id
    payload["session_id"] = payload.get("session_id") or turn["session_id"]
    conn.execute(
        """
        INSERT OR REPLACE INTO turn_events (
            turn_id, seq, type, source, stage, content, metadata_json, timestamp, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            turn_id,
            seq,
            payload.get("type", ""),
            payload.get("source", ""),
            payload.get("stage", ""),
            payload.get("content", "") or "",
            json_dumps(payload.get("metadata", {})),
            float(payload.get("timestamp") or now),
            now,
        ),
    )
    conn.execute("UPDATE turns SET updated_at = ? WHERE id = ?", (now, turn_id))
    conn.commit()
    return payload


def get_turn_events(
    conn: sqlite3.Connection,
    turn_id: str,
    after_seq: int = 0,
    *,
    json_loads: JsonLoads,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT turn_id, seq, type, source, stage, content, metadata_json, timestamp
        FROM turn_events
        WHERE turn_id = ? AND seq > ?
        ORDER BY seq ASC
        """,
        (turn_id, max(0, int(after_seq))),
    ).fetchall()
    turn = conn.execute("SELECT session_id FROM turns WHERE id = ?", (turn_id,)).fetchone()
    session_id = turn["session_id"] if turn else ""
    return [
        {
            "type": row["type"],
            "source": row["source"] or "",
            "stage": row["stage"] or "",
            "content": row["content"] or "",
            "metadata": json_loads(row["metadata_json"], {}),
            "session_id": session_id,
            "turn_id": row["turn_id"],
            "seq": row["seq"],
            "timestamp": row["timestamp"],
        }
        for row in rows
    ]
