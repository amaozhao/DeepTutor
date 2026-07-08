"""SQLite schema and migrations for session storage."""

from __future__ import annotations

import sqlite3


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New conversation',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            compressed_summary TEXT DEFAULT '',
            summary_up_to_msg_id INTEGER DEFAULT 0,
            preferences_json TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            capability TEXT DEFAULT '',
            events_json TEXT DEFAULT '',
            attachments_json TEXT DEFAULT '',
            metadata_json TEXT DEFAULT '{}',
            created_at REAL NOT NULL,
            -- Edit-branching: NULL for the first message in a session;
            -- otherwise the immediately preceding message on the path
            -- this row continues. Siblings (same parent) are alternate
            -- branches the user can switch between.
            parent_message_id INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session_created
            ON messages(session_id, created_at, id);
        -- ``idx_messages_parent`` is created after the parent_message_id
        -- migration runs. Creating it here fails on legacy DBs that need
        -- ALTER TABLE first.

        CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
            ON sessions(updated_at DESC);

        CREATE TABLE IF NOT EXISTS turns (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            capability TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'running',
            error TEXT DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            finished_at REAL
        );

        CREATE INDEX IF NOT EXISTS idx_turns_session_updated
            ON turns(session_id, updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_turns_session_status
            ON turns(session_id, status, updated_at DESC);

        CREATE TABLE IF NOT EXISTS turn_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL,
            type TEXT NOT NULL,
            source TEXT DEFAULT '',
            stage TEXT DEFAULT '',
            content TEXT DEFAULT '',
            metadata_json TEXT DEFAULT '',
            timestamp REAL NOT NULL,
            created_at REAL NOT NULL,
            UNIQUE(turn_id, seq)
        );

        CREATE INDEX IF NOT EXISTS idx_turn_events_turn_seq
            ON turn_events(turn_id, seq);

        CREATE TABLE IF NOT EXISTS notebook_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            turn_id TEXT NOT NULL DEFAULT '',
            question_id TEXT NOT NULL,
            question TEXT NOT NULL,
            question_type TEXT DEFAULT '',
            options_json TEXT DEFAULT '{}',
            correct_answer TEXT DEFAULT '',
            explanation TEXT DEFAULT '',
            difficulty TEXT DEFAULT '',
            user_answer TEXT DEFAULT '',
            user_answer_images_json TEXT DEFAULT '[]',
            is_correct INTEGER DEFAULT 0,
            bookmarked INTEGER DEFAULT 0,
            followup_session_id TEXT DEFAULT '',
            ai_judgment TEXT DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(session_id, turn_id, question_id)
        );

        CREATE INDEX IF NOT EXISTS idx_notebook_entries_session
            ON notebook_entries(session_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_notebook_entries_bookmarked
            ON notebook_entries(bookmarked, created_at DESC);

        CREATE TABLE IF NOT EXISTS notebook_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notebook_entry_categories (
            entry_id INTEGER NOT NULL REFERENCES notebook_entries(id) ON DELETE CASCADE,
            category_id INTEGER NOT NULL REFERENCES notebook_categories(id) ON DELETE CASCADE,
            PRIMARY KEY (entry_id, category_id)
        );
        """
    )
    _migrate_sessions(conn)
    _migrate_messages(conn)
    _migrate_notebook_entries_add_turn_id(conn)
    _migrate_notebook_entries_add_user_answer_images(conn)
    _migrate_notebook_entries_add_ai_judgment(conn)
    conn.commit()


def _migrate_sessions(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "preferences_json" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN preferences_json TEXT DEFAULT '{}'")
    if "kind" in columns:
        try:
            conn.execute("ALTER TABLE sessions DROP COLUMN kind")
        except sqlite3.OperationalError:
            # Older SQLite builds may not support DROP COLUMN. The application
            # no longer reads or writes this legacy field.
            pass


def _migrate_messages(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
    if "metadata_json" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN metadata_json TEXT DEFAULT '{}'")
    if "parent_message_id" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN parent_message_id INTEGER")
        sessions_rows = conn.execute("SELECT id FROM sessions").fetchall()
        for srow in sessions_rows:
            prev_id: int | None = None
            msg_rows = conn.execute(
                "SELECT id FROM messages WHERE session_id = ? ORDER BY id ASC",
                (srow[0],),
            ).fetchall()
            for mrow in msg_rows:
                if prev_id is not None:
                    conn.execute(
                        "UPDATE messages SET parent_message_id = ? WHERE id = ?",
                        (prev_id, mrow[0]),
                    )
                prev_id = mrow[0]
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(session_id, parent_message_id)"
    )


def _migrate_notebook_entries_add_turn_id(conn: sqlite3.Connection) -> None:
    notebook_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(notebook_entries)").fetchall()
    }
    if not notebook_cols:
        return
    if "turn_id" not in notebook_cols:
        conn.execute("ALTER TABLE notebook_entries ADD COLUMN turn_id TEXT NOT NULL DEFAULT ''")

    needs_rebuild = False
    for idx_row in conn.execute("PRAGMA index_list(notebook_entries)").fetchall():
        idx_name = idx_row[1]
        if not idx_name.startswith("sqlite_autoindex_notebook_entries_"):
            continue
        cols = [r[2] for r in conn.execute(f"PRAGMA index_info({idx_name})").fetchall()]
        if cols == ["session_id", "question_id"]:
            needs_rebuild = True
            break
    if not needs_rebuild:
        return
    conn.executescript(
        """
        CREATE TABLE notebook_entries_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            turn_id TEXT NOT NULL DEFAULT '',
            question_id TEXT NOT NULL,
            question TEXT NOT NULL,
            question_type TEXT DEFAULT '',
            options_json TEXT DEFAULT '{}',
            correct_answer TEXT DEFAULT '',
            explanation TEXT DEFAULT '',
            difficulty TEXT DEFAULT '',
            user_answer TEXT DEFAULT '',
            is_correct INTEGER DEFAULT 0,
            bookmarked INTEGER DEFAULT 0,
            followup_session_id TEXT DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(session_id, turn_id, question_id)
        );

        INSERT INTO notebook_entries_new (
            id, session_id, turn_id, question_id, question, question_type,
            options_json, correct_answer, explanation, difficulty,
            user_answer, is_correct, bookmarked, followup_session_id,
            created_at, updated_at
        )
        SELECT
            id, session_id, COALESCE(turn_id, ''), question_id, question,
            question_type, options_json, correct_answer, explanation,
            difficulty, user_answer, is_correct, bookmarked,
            followup_session_id, created_at, updated_at
        FROM notebook_entries;

        DROP TABLE notebook_entries;
        ALTER TABLE notebook_entries_new RENAME TO notebook_entries;

        CREATE INDEX IF NOT EXISTS idx_notebook_entries_session
            ON notebook_entries(session_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_notebook_entries_bookmarked
            ON notebook_entries(bookmarked, created_at DESC);
        """
    )


def _migrate_notebook_entries_add_user_answer_images(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(notebook_entries)").fetchall()}
    if not cols:
        return
    if "user_answer_images_json" not in cols:
        conn.execute(
            "ALTER TABLE notebook_entries ADD COLUMN user_answer_images_json TEXT DEFAULT '[]'"
        )


def _migrate_notebook_entries_add_ai_judgment(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(notebook_entries)").fetchall()}
    if not cols:
        return
    if "ai_judgment" not in cols:
        conn.execute("ALTER TABLE notebook_entries ADD COLUMN ai_judgment TEXT DEFAULT ''")
