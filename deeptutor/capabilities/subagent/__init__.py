"""Subagent capability exports."""

from __future__ import annotations

import importlib

__all__ = [
    "SubagentCapability",
    "ConsultSubagentTool",
    "SUBAGENT_TOOL_NAMES",
    "SUBAGENT_TOOL_TYPES",
    "connection_for_turn",
]


def __getattr__(name: str):
    if name == "connection_for_turn":
        return importlib.import_module(f"{__name__}.binding").connection_for_turn
    if name == "SubagentCapability":
        return importlib.import_module(f"{__name__}.capability").SubagentCapability
    if name in {"ConsultSubagentTool", "SUBAGENT_TOOL_NAMES", "SUBAGENT_TOOL_TYPES"}:
        module = importlib.import_module(f"{__name__}.tools")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
