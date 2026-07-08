"""Agents package exports.

Note: ``co_writer`` and ``book`` are independent top-level modules under
``deeptutor/`` (e.g. ``deeptutor.co_writer``, ``deeptutor.book``). They
still inherit from :class:`BaseAgent` defined here but are not part of
the ``deeptutor.agents`` package.

Usage:
    from deeptutor.agents.base_agent import BaseAgent

    class MyAgent(BaseAgent):
        async def process(self, *args, **kwargs):
            ...
"""

from __future__ import annotations

import importlib

__all__ = ["BaseAgent", "ChatAgent", "SessionManager"]


def __getattr__(name: str):
    if name == "BaseAgent":
        value = importlib.import_module(f"{__name__}.base_agent").BaseAgent
    elif name == "ChatAgent":
        value = importlib.import_module(f"{__name__}.chat.chat_agent").ChatAgent
    elif name == "SessionManager":
        value = importlib.import_module(f"{__name__}.chat.session_manager").SessionManager
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value
