"""Knowledge-base RAG provider validation helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile

from deeptutor.services.rag.factory import (
    GRAPHRAG_PROVIDER,
    LIGHTRAG_PROVIDER,
    PAGEINDEX_PROVIDER,
    normalize_provider_name,
)
from deeptutor.services.rag.pipelines.graphrag.config import is_graphrag_available
from deeptutor.services.rag.pipelines.lightrag.config import is_lightrag_available
from deeptutor.services.rag.pipelines.pageindex.config import is_pageindex_configured
from deeptutor.services.rag.pipelines.pageindex.pipeline import SUPPORTED_EXTENSIONS


def validate_registered_provider(raw_provider: str | None) -> str:
    """Resolve a requested provider to a known engine."""
    return normalize_provider_name(raw_provider)


def assert_provider_ready(provider: str) -> None:
    """Block creating/using a KB whose engine isn't ready."""
    if provider == PAGEINDEX_PROVIDER:
        if not is_pageindex_configured():
            raise HTTPException(
                status_code=400,
                detail=(
                    "PageIndex API key is not configured. Add it under "
                    "Knowledge → RAG pipeline settings before creating a PageIndex "
                    "knowledge base."
                ),
            )

    if provider == GRAPHRAG_PROVIDER:
        if not is_graphrag_available():
            raise HTTPException(
                status_code=400,
                detail=(
                    "GraphRAG is not installed. Run "
                    "`pip install 'deeptutor[graphrag]'` on the server before "
                    "creating a GraphRAG knowledge base."
                ),
            )

    if provider == LIGHTRAG_PROVIDER:
        if not is_lightrag_available():
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

    unsupported = [
        f.filename
        for f in files
        if f.filename
        and not f.filename.lower().endswith(".zip")
        and Path(f.filename).suffix.lower() not in SUPPORTED_EXTENSIONS
    ]
    if unsupported:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=(
                f"PageIndex knowledge bases accept: {supported}. "
                f"Unsupported: {', '.join(unsupported[:5])}."
            ),
        )
