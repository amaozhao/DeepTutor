"""
Session Management Module
=========================

Provides unified session management for all agent modules.
"""

from __future__ import annotations

import importlib

__all__ = [
    "BaseSessionManager",
    "SessionStoreProtocol",
    "SQLiteSessionStore",
    "TurnRuntimeManager",
    "get_session_store",
    "get_sqlite_session_store",
    "get_turn_runtime_manager",
    "make_imported_session_id",
]


def __getattr__(name: str):
    if name == "BaseSessionManager":
        module = importlib.import_module(f"{__name__}.base_session_manager")
        return module.BaseSessionManager
    if name == "SessionStoreProtocol":
        module = importlib.import_module(f"{__name__}.protocol")
        return module.SessionStoreProtocol
    if name in {"SQLiteSessionStore", "get_sqlite_session_store", "make_imported_session_id"}:
        module = importlib.import_module(f"{__name__}.sqlite_store")
        return getattr(module, name)
    if name == "get_session_store":
        module = importlib.import_module(f"{__name__}.store")
        return module.get_session_store
    if name in {"TurnRuntimeManager", "get_turn_runtime_manager"}:
        module = importlib.import_module(f"{__name__}.turn_runtime")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
