"""Active session-store selection."""

from __future__ import annotations

from deeptutor.services.pocketbase_client import is_pocketbase_enabled
from deeptutor.services.session.pocketbase_store import PocketBaseSessionStore
from deeptutor.services.session.protocol import SessionStoreProtocol
from deeptutor.services.session.sqlite_store import get_sqlite_session_store


def get_session_store() -> SessionStoreProtocol:
    """
    Return the active session store backend.

    When integrations.pocketbase_url is configured, returns a
    PocketBaseSessionStore. Otherwise falls back to the local
    SQLiteSessionStore (default, zero-config behaviour).
    """
    if is_pocketbase_enabled():
        return PocketBaseSessionStore()
    return get_sqlite_session_store()
