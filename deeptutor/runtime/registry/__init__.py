"""Runtime registries for capabilities and tools."""

from __future__ import annotations

import importlib

__all__ = [
    "CapabilityRegistry",
    "ToolRegistry",
    "get_capability_registry",
    "get_tool_registry",
]


def __getattr__(name: str):
    if name in {"CapabilityRegistry", "get_capability_registry"}:
        module = importlib.import_module(f"{__name__}.capability_registry")
        return getattr(module, name)
    if name in {"ToolRegistry", "get_tool_registry"}:
        module = importlib.import_module(f"{__name__}.tool_registry")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
