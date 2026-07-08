#!/usr/bin/env python
"""Knowledge base package exports (lazy-loaded)."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "DocumentAdder",
    "KnowledgeBaseInitializer",
    "KnowledgeBaseManager",
]


def __getattr__(name: str) -> Any:
    if name == "DocumentAdder":
        return importlib.import_module(f"{__name__}.add_documents").DocumentAdder
    if name == "KnowledgeBaseInitializer":
        return importlib.import_module(f"{__name__}.initializer").KnowledgeBaseInitializer
    if name == "KnowledgeBaseManager":
        return importlib.import_module(f"{__name__}.manager").KnowledgeBaseManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
