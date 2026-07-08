"""Agents package exports."""

from __future__ import annotations

import importlib

__all__ = ["BaseAgent", "ChatAgent", "SessionManager"]


def __getattr__(name: str):
    if name == "BaseAgent":
        return importlib.import_module(f"{__name__}.base_agent").BaseAgent
    if name == "ChatAgent":
        return importlib.import_module(f"{__name__}.chat.chat_agent").ChatAgent
    if name == "SessionManager":
        return importlib.import_module(f"{__name__}.chat.session_manager").SessionManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
