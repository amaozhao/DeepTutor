"""Optional PostgreSQL state store for multi-replica SaaS deployments."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import secrets
from typing import Any, Callable

import psycopg
from psycopg.rows import dict_row

from deeptutor.services.config import load_shared_state_settings


def postgres_enabled() -> bool:
    settings = load_shared_state_settings()
    return bool(settings.get("provider") == "postgres" and settings.get("database_url"))


def _database_url() -> str:
    return str(load_shared_state_settings().get("database_url") or "")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}
    return {}


@contextmanager
def connect() -> Iterator[Any]:
    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        yield conn


_SCHEMA_READY = False


def reset_for_tests() -> None:
    global _SCHEMA_READY
    _SCHEMA_READY = False


def ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dt_users (
                username text PRIMARY KEY,
                record jsonb NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dt_auth_secrets (
                name text PRIMARY KEY,
                secret text NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dt_grants (
                user_id text PRIMARY KEY,
                record jsonb NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dt_usage_events (
                id bigserial PRIMARY KEY,
                event jsonb NOT NULL,
                event_time timestamptz NOT NULL,
                user_id text NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_dt_usage_events_user_time
            ON dt_usage_events (user_id, event_time)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dt_rate_hits (
                bucket text NOT NULL,
                hit_at double precision NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_dt_rate_hits_bucket_time
            ON dt_rate_hits (bucket, hit_at)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dt_invites (
                code text PRIMARY KEY,
                record jsonb NOT NULL
            )
            """
        )
    _SCHEMA_READY = True


def load_users() -> dict[str, dict[str, Any]]:
    ensure_schema()
    with connect() as conn:
        rows = _load_user_rows(conn)
    return {str(row["username"]): _dict(row["record"]) for row in rows}


def save_users(users: dict[str, dict[str, Any]]) -> None:
    ensure_schema()
    with connect() as conn:
        _lock(conn, "dt_users")
        _save_users(conn, users)


def update_users(mutator: Callable[[dict[str, dict[str, Any]]], Any]) -> Any:
    ensure_schema()
    with connect() as conn:
        _lock(conn, "dt_users")
        rows = _load_user_rows(conn)
        users = {str(row["username"]): _dict(row["record"]) for row in rows}
        result = mutator(users)
        _save_users(conn, users)
        return result


def _lock(conn: Any, key: str) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,))


def _load_user_rows(conn: Any) -> list[dict[str, Any]]:
    return list(conn.execute("SELECT username, record FROM dt_users ORDER BY username").fetchall())


def _save_users(conn: Any, users: dict[str, dict[str, Any]]) -> None:
    conn.execute("DELETE FROM dt_users")
    for username, record in users.items():
        conn.execute(
            "INSERT INTO dt_users (username, record) VALUES (%s, %s::jsonb)",
            (username, _json(record)),
        )


def load_or_create_auth_secret(seed: str = "") -> str:
    ensure_schema()
    with connect() as conn:
        row = conn.execute(
            "SELECT secret FROM dt_auth_secrets WHERE name = %s",
            ("jwt",),
        ).fetchone()
        if row and row.get("secret"):
            return str(row["secret"])
        secret = seed or secrets.token_hex(32)
        conn.execute(
            """
            INSERT INTO dt_auth_secrets (name, secret)
            VALUES (%s, %s)
            ON CONFLICT (name) DO NOTHING
            """,
            ("jwt", secret),
        )
        row = conn.execute(
            "SELECT secret FROM dt_auth_secrets WHERE name = %s",
            ("jwt",),
        ).fetchone()
        return str(row["secret"]) if row else secret


def load_grant(user_id: str) -> dict[str, Any] | None:
    ensure_schema()
    with connect() as conn:
        row = conn.execute(
            "SELECT record FROM dt_grants WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    return _dict(row["record"]) if row else None


def save_grant(user_id: str, grant: dict[str, Any]) -> None:
    ensure_schema()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO dt_grants (user_id, record)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (user_id) DO UPDATE SET record = EXCLUDED.record
            """,
            (user_id, _json(grant)),
        )


def delete_grant(user_id: str) -> None:
    ensure_schema()
    with connect() as conn:
        conn.execute("DELETE FROM dt_grants WHERE user_id = %s", (user_id,))


def record_usage_event(event: dict[str, Any]) -> None:
    ensure_schema()
    event_time = str(event.get("time") or datetime.now(timezone.utc).isoformat())
    user_id = str(event.get("user_id") or "")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO dt_usage_events (event, event_time, user_id)
            VALUES (%s::jsonb, %s, %s)
            """,
            (_json(event), event_time, user_id),
        )


def usage_events(user_id: str | None = None) -> list[dict[str, Any]]:
    ensure_schema()
    params: tuple[Any, ...] = ()
    where = ""
    if user_id:
        where = "WHERE user_id = %s"
        params = (user_id,)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT event FROM dt_usage_events {where} ORDER BY id",
            params,
        ).fetchall()
    return [_dict(row["event"]) for row in rows]


def allow_rate_hit(bucket: str, *, limit: int, window_seconds: int, now: float) -> bool:
    ensure_schema()
    cutoff = now - window_seconds
    with connect() as conn:
        _lock(conn, f"dt_rate_hits:{bucket}")
        conn.execute(
            "DELETE FROM dt_rate_hits WHERE bucket = %s AND hit_at <= %s", (bucket, cutoff)
        )
        row = conn.execute(
            "SELECT count(*) AS count FROM dt_rate_hits WHERE bucket = %s",
            (bucket,),
        ).fetchone()
        count = int(row["count"] if row else 0)
        if count >= limit:
            return False
        conn.execute(
            "INSERT INTO dt_rate_hits (bucket, hit_at) VALUES (%s, %s)",
            (bucket, now),
        )
        return True


def clear_rate_hits() -> None:
    ensure_schema()
    with connect() as conn:
        conn.execute("DELETE FROM dt_rate_hits")


def load_invites() -> dict[str, dict[str, Any]]:
    ensure_schema()
    with connect() as conn:
        rows = conn.execute("SELECT code, record FROM dt_invites ORDER BY code").fetchall()
    return {str(row["code"]): _dict(row["record"]) for row in rows}


def update_invites(mutator: Callable[[dict[str, dict[str, Any]]], Any]) -> Any:
    ensure_schema()
    with connect() as conn:
        _lock(conn, "dt_invites")
        rows = conn.execute("SELECT code, record FROM dt_invites ORDER BY code").fetchall()
        invites = {str(row["code"]): _dict(row["record"]) for row in rows}
        result = mutator(invites)
        conn.execute("DELETE FROM dt_invites")
        for code, record in invites.items():
            conn.execute(
                "INSERT INTO dt_invites (code, record) VALUES (%s, %s::jsonb)",
                (code, _json(record)),
            )
        return result


def health_status() -> dict[str, str]:
    try:
        ensure_schema()
        with connect() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    return {"status": "ok"}
