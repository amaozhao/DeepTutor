"""Turn-scoped chat-loop capabilities.

Each capability keeps feature-specific behavior in its own subpackage while
this package exposes the generic loop protocol and registry lazily.
"""

from __future__ import annotations

import importlib

__all__ = [
    "LOOP_CAPABILITIES",
    "KnowledgeCapability",
    "LoopCapability",
    "PromptBlock",
    "active_loop_capabilities",
    "all_loop_capabilities",
    "any_exclusive_capability_active",
    "capability_tool_owners",
]


def __getattr__(name: str):
    if name in {"KnowledgeCapability", "LoopCapability", "PromptBlock"}:
        module = importlib.import_module(f"{__name__}.protocol")
        return getattr(module, name)
    if name in {
        "LOOP_CAPABILITIES",
        "active_loop_capabilities",
        "all_loop_capabilities",
        "any_exclusive_capability_active",
        "capability_tool_owners",
    }:
        module = importlib.import_module(f"{__name__}.registry")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
