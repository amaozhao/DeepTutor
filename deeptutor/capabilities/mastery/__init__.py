"""Mastery path loop capability."""

from __future__ import annotations

import importlib

__all__ = ["MASTERY_TOOL_NAMES", "MASTERY_TOOL_TYPES", "MasteryLoopCapability"]


def __getattr__(name: str):
    if name == "MasteryLoopCapability":
        module = importlib.import_module(f"{__name__}.loop")
        return module.MasteryLoopCapability
    if name in {"MASTERY_TOOL_NAMES", "MASTERY_TOOL_TYPES"}:
        module = importlib.import_module(f"{__name__}.tools")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
