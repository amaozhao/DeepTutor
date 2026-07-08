"""Chat module exports."""

from __future__ import annotations

import importlib

__all__ = ["AgenticChatPipeline", "ChatAgent", "SessionManager"]


def __getattr__(name: str):
    if name == "AgenticChatPipeline":
        return importlib.import_module(f"{__name__}.agentic_pipeline").AgenticChatPipeline
    if name == "ChatAgent":
        return importlib.import_module(f"{__name__}.chat_agent").ChatAgent
    if name == "SessionManager":
        return importlib.import_module(f"{__name__}.session_manager").SessionManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
