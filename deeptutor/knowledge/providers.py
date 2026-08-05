"""Knowledge-base RAG provider validation helpers."""

from __future__ import annotations

import importlib
from pathlib import Path

from fastapi import HTTPException, UploadFile

from deeptutor.services.rag.factory import (
    GRAPHRAG_PROVIDER,
    LIGHTRAG_PROVIDER,
    PAGEINDEX_PROVIDER,
    normalize_provider_name,
)


def validate_registered_provider(raw_provider: str | None) -> str:
    """Resolve a requested provider to a known engine."""
    return normalize_provider_name(raw_provider)


def assert_provider_ready(provider: str) -> None:
    """Block creating/using a KB whose engine isn't ready."""
    if provider == PAGEINDEX_PROVIDER:
        pageindex_config = importlib.import_module(
            "deeptutor.services.rag.pipelines.pageindex.config"
        )
        if not pageindex_config.is_pageindex_configured():
            raise HTTPException(
                status_code=400,
                detail=(
                    "PageIndex API key is not configured. Add it under "
                    "Knowledge → RAG pipeline settings before creating a PageIndex "
                    "knowledge base."
                ),
            )

    if provider == GRAPHRAG_PROVIDER:
        graphrag_config = importlib.import_module(
            "deeptutor.services.rag.pipelines.graphrag.config"
        )
        if not graphrag_config.is_graphrag_available():
            raise HTTPException(
                status_code=400,
                detail=(
                    "GraphRAG is not installed. Run "
                    "`pip install 'deeptutor[graphrag]'` on the server before "
                    "creating a GraphRAG knowledge base."
                ),
            )

    if provider == LIGHTRAG_PROVIDER:
        lightrag_config = importlib.import_module(
            "deeptutor.services.rag.pipelines.lightrag.config"
        )
        if not lightrag_config.is_lightrag_available():
            raise HTTPException(
                status_code=400,
                detail=(
                    "LightRAG is not installed. Run "
                    "`pip install 'deeptutor[rag-lightrag]'` on the server before "
                    "creating a LightRAG knowledge base."
                ),
            )


def enforce_provider_formats(provider: str, files: list[UploadFile]) -> None:
    """Reject files PageIndex's document endpoint does not accept, up front."""
    if provider != PAGEINDEX_PROVIDER:
        return

    supported_extensions = importlib.import_module(
        "deeptutor.services.rag.pipelines.pageindex.pipeline"
    ).SUPPORTED_EXTENSIONS
    unsupported = [
        f.filename
        for f in files
        if f.filename
        and not f.filename.lower().endswith(".zip")
        and Path(f.filename).suffix.lower() not in supported_extensions
    ]
    if unsupported:
        supported = ", ".join(sorted(supported_extensions))
        raise HTTPException(
            status_code=400,
            detail=(
                f"PageIndex knowledge bases accept: {supported}. "
                f"Unsupported: {', '.join(unsupported[:5])}."
            ),
        )
