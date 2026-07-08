"""Runtime orchestration and registry helpers."""

import importlib

from .mode import RunMode, get_mode, is_cli, is_server, set_mode

__all__ = [
    "ChatOrchestrator",
    "RunMode",
    "get_mode",
    "is_cli",
    "is_server",
    "set_mode",
]


def __getattr__(name: str):
    if name == "ChatOrchestrator":
        return importlib.import_module(f"{__name__}.orchestrator").ChatOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
