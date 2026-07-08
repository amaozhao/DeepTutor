"""Notebook-entry SQL helpers for SQLite session storage."""

from __future__ import annotations

import sqlite3
import time
from typing import Any, Callable

JsonDumps = Callable[[Any], str]
JsonLoads = Callable[[str | None, Any], Any]


def upsert_entries(
    conn: sqlite3.Connection,
    session_id: str,
    items: list[dict[str, Any]],
    *,
    json_dumps: JsonDumps,
) -> int:
    if not items:
        return 0
    now = time.time()
    if conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone() is None:
        raise ValueError(f"Session not found: {session_id}")
    upserted = 0
    for item in items:
        question = (item.get("question") or "").strip()
        question_id = (item.get("question_id") or "").strip()
        if not question or not question_id:
            continue
        turn_id = (item.get("turn_id") or "").strip()
        images_value = item.get("user_answer_images")
        images_json = json_dumps(images_value) if isinstance(images_value, list) else None
        if images_json is None:
            conn.execute(
                """
                INSERT INTO notebook_entries (
                    session_id, turn_id, question_id, question, question_type,
                    options_json, correct_answer, explanation, difficulty,
                    user_answer, user_answer_images_json, is_correct,
                    bookmarked, followup_session_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, 0, '', ?, ?)
                ON CONFLICT(session_id, turn_id, question_id) DO UPDATE SET
                    user_answer = excluded.user_answer,
                    is_correct = excluded.is_correct,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    turn_id,
                    question_id,
                    question,
                    item.get("question_type") or "",
                    json_dumps(item.get("options") or {}),
                    item.get("correct_answer") or "",
                    item.get("explanation") or "",
                    item.get("difficulty") or "",
                    item.get("user_answer") or "",
                    1 if item.get("is_correct") else 0,
                    now,
                    now,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO notebook_entries (
                    session_id, turn_id, question_id, question, question_type,
                    options_json, correct_answer, explanation, difficulty,
                    user_answer, user_answer_images_json, is_correct,
                    bookmarked, followup_session_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, ?)
                ON CONFLICT(session_id, turn_id, question_id) DO UPDATE SET
                    user_answer = excluded.user_answer,
                    user_answer_images_json = excluded.user_answer_images_json,
                    is_correct = excluded.is_correct,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    turn_id,
                    question_id,
                    question,
                    item.get("question_type") or "",
                    json_dumps(item.get("options") or {}),
                    item.get("correct_answer") or "",
                    item.get("explanation") or "",
                    item.get("difficulty") or "",
                    item.get("user_answer") or "",
                    images_json,
                    1 if item.get("is_correct") else 0,
                    now,
                    now,
                ),
            )
        upserted += 1
    conn.commit()
    return upserted


def serialize_entry(row: sqlite3.Row, *, json_loads: JsonLoads) -> dict[str, Any]:
    keys = set(row.keys())
    images: list[dict[str, Any]] = []
    if "user_answer_images_json" in keys:
        raw_images = json_loads(row["user_answer_images_json"], [])
        if isinstance(raw_images, list):
            images = [r for r in raw_images if isinstance(r, dict)]
    return {
        "id": int(row["id"]),
        "session_id": row["session_id"],
        "session_title": row["session_title"] or "" if "session_title" in keys else "",
        "turn_id": (row["turn_id"] or "") if "turn_id" in keys else "",
        "question_id": row["question_id"] or "",
        "question": row["question"],
        "question_type": row["question_type"] or "",
        "options": json_loads(row["options_json"], {}),
        "correct_answer": row["correct_answer"] or "",
        "explanation": row["explanation"] or "",
        "difficulty": row["difficulty"] or "",
        "user_answer": row["user_answer"] or "",
        "user_answer_images": images,
        "is_correct": bool(row["is_correct"]),
        "bookmarked": bool(row["bookmarked"]),
        "followup_session_id": row["followup_session_id"] or "",
        "ai_judgment": (row["ai_judgment"] or "") if "ai_judgment" in keys else "",
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
    }


def list_entries(
    conn: sqlite3.Connection,
    category_id: int | None,
    bookmarked: bool | None,
    is_correct: bool | None,
    limit: int,
    offset: int,
    session_id: str | None,
    *,
    json_loads: JsonLoads,
) -> dict[str, Any]:
    base = """
        SELECT
            n.id, n.session_id, COALESCE(s.title, '') AS session_title,
            n.turn_id, n.question_id, n.question, n.question_type, n.options_json,
            n.correct_answer, n.explanation, n.difficulty,
            n.user_answer, n.user_answer_images_json, n.is_correct, n.bookmarked,
            n.followup_session_id, n.ai_judgment, n.created_at, n.updated_at
        FROM notebook_entries n
        LEFT JOIN sessions s ON s.id = n.session_id
    """
    count_base = "SELECT COUNT(*) AS cnt FROM notebook_entries n"
    conditions: list[str] = []
    params: list[Any] = []
    if category_id is not None:
        join = " INNER JOIN notebook_entry_categories ec ON ec.entry_id = n.id"
        base += join
        count_base += join
        conditions.append("ec.category_id = ?")
        params.append(category_id)
    if bookmarked is not None:
        conditions.append("n.bookmarked = ?")
        params.append(1 if bookmarked else 0)
    if is_correct is not None:
        conditions.append("n.is_correct = ?")
        params.append(1 if is_correct else 0)
    if session_id is not None:
        conditions.append("n.session_id = ?")
        params.append(session_id)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    total_row = conn.execute(count_base + where, tuple(params)).fetchone()
    total = int(total_row["cnt"]) if total_row else 0
    rows = conn.execute(
        base + where + " ORDER BY n.created_at DESC LIMIT ? OFFSET ?",
        tuple(params) + (limit, offset),
    ).fetchall()
    items = [serialize_entry(row, json_loads=json_loads) for row in rows]
    return {"items": items, "total": total}


def get_entry(
    conn: sqlite3.Connection,
    entry_id: int,
    *,
    json_loads: JsonLoads,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            n.*, COALESCE(s.title, '') AS session_title
        FROM notebook_entries n
        LEFT JOIN sessions s ON s.id = n.session_id
        WHERE n.id = ?
        """,
        (entry_id,),
    ).fetchone()
    if row is None:
        return None
    entry = serialize_entry(row, json_loads=json_loads)
    cats = conn.execute(
        """
        SELECT c.id, c.name
        FROM notebook_categories c
        INNER JOIN notebook_entry_categories ec ON ec.category_id = c.id
        WHERE ec.entry_id = ?
        ORDER BY c.name
        """,
        (entry_id,),
    ).fetchall()
    entry["categories"] = [{"id": c["id"], "name": c["name"]} for c in cats]
    return entry


def find_entry(
    conn: sqlite3.Connection,
    session_id: str,
    question_id: str,
    turn_id: str | None,
    *,
    json_loads: JsonLoads,
) -> dict[str, Any] | None:
    if turn_id is not None:
        row = conn.execute(
            """
            SELECT n.*, COALESCE(s.title, '') AS session_title
            FROM notebook_entries n
            LEFT JOIN sessions s ON s.id = n.session_id
            WHERE n.session_id = ?
              AND n.turn_id = ?
              AND n.question_id = ?
            """,
            (session_id, turn_id, question_id),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT n.*, COALESCE(s.title, '') AS session_title
            FROM notebook_entries n
            LEFT JOIN sessions s ON s.id = n.session_id
            WHERE n.session_id = ? AND n.question_id = ?
            ORDER BY n.updated_at DESC, n.id DESC
            LIMIT 1
            """,
            (session_id, question_id),
        ).fetchone()
    return serialize_entry(row, json_loads=json_loads) if row is not None else None


def update_entry(conn: sqlite3.Connection, entry_id: int, updates: dict[str, Any]) -> bool:
    allowed = {
        "bookmarked",
        "followup_session_id",
        "user_answer",
        "is_correct",
        "ai_judgment",
    }
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        return False
    fields["updated_at"] = time.time()
    if "bookmarked" in fields:
        fields["bookmarked"] = 1 if fields["bookmarked"] else 0
    if "is_correct" in fields:
        fields["is_correct"] = 1 if fields["is_correct"] else 0
    set_clause = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [entry_id]
    cur = conn.execute(
        f"UPDATE notebook_entries SET {set_clause} WHERE id = ?",  # nosec B608
        tuple(values),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_entry(conn: sqlite3.Connection, entry_id: int) -> bool:
    cur = conn.execute("DELETE FROM notebook_entries WHERE id = ?", (entry_id,))
    conn.commit()
    return cur.rowcount > 0


def create_category(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    now = time.time()
    cur = conn.execute(
        "INSERT INTO notebook_categories (name, created_at) VALUES (?, ?)",
        (name.strip(), now),
    )
    conn.commit()
    return {"id": int(cur.lastrowid), "name": name.strip(), "created_at": now}


def list_categories(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.created_at,
               COUNT(ec.entry_id) AS entry_count
        FROM notebook_categories c
        LEFT JOIN notebook_entry_categories ec ON ec.category_id = c.id
        GROUP BY c.id
        ORDER BY c.name
        """,
    ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "created_at": float(row["created_at"]),
            "entry_count": int(row["entry_count"]),
        }
        for row in rows
    ]


def rename_category(conn: sqlite3.Connection, category_id: int, name: str) -> bool:
    cur = conn.execute(
        "UPDATE notebook_categories SET name = ? WHERE id = ?",
        (name.strip(), category_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_category(conn: sqlite3.Connection, category_id: int) -> bool:
    cur = conn.execute("DELETE FROM notebook_categories WHERE id = ?", (category_id,))
    conn.commit()
    return cur.rowcount > 0


def add_entry_to_category(conn: sqlite3.Connection, entry_id: int, category_id: int) -> bool:
    try:
        conn.execute(
            "INSERT OR IGNORE INTO notebook_entry_categories (entry_id, category_id) VALUES (?, ?)",
            (entry_id, category_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return False
    return True


def remove_entry_from_category(conn: sqlite3.Connection, entry_id: int, category_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM notebook_entry_categories WHERE entry_id = ? AND category_id = ?",
        (entry_id, category_id),
    )
    conn.commit()
    return cur.rowcount > 0


def get_entry_categories(conn: sqlite3.Connection, entry_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.id, c.name FROM notebook_categories c
        INNER JOIN notebook_entry_categories ec ON ec.category_id = c.id
        WHERE ec.entry_id = ?
        ORDER BY c.name
        """,
        (entry_id,),
    ).fetchall()
    return [{"id": row["id"], "name": row["name"]} for row in rows]
