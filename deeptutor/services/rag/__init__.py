"""RAG service exports."""

from __future__ import annotations

import importlib

__all__ = [
    "RAGService",
    "FileTypeRouter",
    "FileClassification",
    "DocumentType",
    "get_pipeline",
    "list_pipelines",
    "normalize_provider_name",
    "DEFAULT_PROVIDER",
]


def __getattr__(name: str):
    if name in {
        "DEFAULT_PROVIDER",
        "get_pipeline",
        "list_pipelines",
        "normalize_provider_name",
    }:
        factory = importlib.import_module(f"{__name__}.factory")
        return getattr(factory, name)
    if name in {"DocumentType", "FileClassification", "FileTypeRouter"}:
        routing = importlib.import_module(f"{__name__}.file_routing")
        return getattr(routing, name)
    if name == "RAGService":
        service = importlib.import_module(f"{__name__}.service")
        return service.RAGService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
