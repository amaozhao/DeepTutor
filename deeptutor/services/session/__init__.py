"""
Session Management Module
=========================

Provides unified session management for all agent modules.

Usage:
    from deeptutor.services.session import BaseSessionManager

    class MySessionManager(BaseSessionManager):
        def __init__(self):
            super().__init__("my_module")

        def _get_session_id_prefix(self) -> str:
            return "my_"

        def _get_default_title(self) -> str:
            return "New My Session"

        # ... implement other abstract methods
"""

from .base_session_manager import BaseSessionManager
from .sqlite_store import SQLiteSessionStore, get_sqlite_session_store, reset_sqlite_session_stores
from .turn_runtime import TurnRuntimeManager, get_turn_runtime_manager, reset_turn_runtime_managers


def reset_session_services() -> None:
    reset_turn_runtime_managers()
    reset_sqlite_session_stores()

__all__ = [
    "BaseSessionManager",
    "SQLiteSessionStore",
    "TurnRuntimeManager",
    "get_sqlite_session_store",
    "get_turn_runtime_manager",
    "reset_session_services",
]
