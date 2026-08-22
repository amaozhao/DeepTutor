"""RAG pipeline factory.

Selects a KB's index/retrieve engine by provider name. Three pipelines ship
today:

* ``llamaindex`` (default) — local vector retrieval with hybrid BM25 fusion.
* ``pageindex``           — PageIndex Cloud (deployment credential + MCP tools).
* ``pageindex-oss``       — local PageIndex library using the active chat LLM.
* ``graphrag``            — local knowledge-graph retrieval (microsoft/graphrag);
                            optional dependency, ``pip install 'deeptutor[graphrag]'``.
* ``lightrag``            — graph + vector retrieval (HKUDS/LightRAG, multimodal
                            via RAG-Anything); optional dependency,
                            ``pip install 'deeptutor[rag-lightrag]'``.
* ``lightrag-server``     — retrieval offloaded to an external, standalone
                            LightRAG server the user runs. No local index: each
                            KB is a connection pointer queried over HTTP.
* ``ima``                 — retrieval offloaded to a Tencent IMA knowledge base
                            the user curates in IMA. No local index: each KB is
                            a connection pointer queried over IMA's OpenAPI.

A KB is bound to one provider at creation time; later adds and retrieval always
go through that same pipeline (enforced upstream in the knowledge router).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_PROVIDER = "llamaindex"
PAGEINDEX_PROVIDER = "pageindex"
PAGEINDEX_OSS_PROVIDER = "pageindex-oss"
GRAPHRAG_PROVIDER = "graphrag"
LIGHTRAG_PROVIDER = "lightrag"
LIGHTRAG_SERVER_PROVIDER = "lightrag-server"
IMA_PROVIDER = "ima"

# Providers the factory can instantiate. Unknown / legacy strings fall back to
# the default with a re-index hint upstream.
KNOWN_PROVIDERS = frozenset(
    {
        DEFAULT_PROVIDER,
        PAGEINDEX_PROVIDER,
        PAGEINDEX_OSS_PROVIDER,
        GRAPHRAG_PROVIDER,
        LIGHTRAG_PROVIDER,
        LIGHTRAG_SERVER_PROVIDER,
        IMA_PROVIDER,
    }
)

# Cached pipeline instances keyed by (kb_base_dir, provider).
_PIPELINE_CACHE: Dict[Tuple[Optional[str], str], Any] = {}

_PIPELINE_IMPORTS = {
    DEFAULT_PROVIDER: (
        "deeptutor.services.rag.pipelines.llamaindex.pipeline",
        "LlamaIndexPipeline",
        "LlamaIndex",
    ),
    PAGEINDEX_PROVIDER: (
        "deeptutor.services.rag.pipelines.pageindex.pipeline",
        "PageIndexPipeline",
        "PageIndex",
    ),
    PAGEINDEX_OSS_PROVIDER: (
        "deeptutor.services.rag.pipelines.pageindex.pipeline",
        "PageIndexPipeline",
        "PageIndex OSS",
    ),
    GRAPHRAG_PROVIDER: (
        "deeptutor.services.rag.pipelines.graphrag.pipeline",
        "GraphRagPipeline",
        "GraphRAG",
    ),
    LIGHTRAG_PROVIDER: (
        "deeptutor.services.rag.pipelines.lightrag.pipeline",
        "LightRagPipeline",
        "LightRAG",
    ),
    LIGHTRAG_SERVER_PROVIDER: (
        "deeptutor.services.rag.pipelines.lightrag_server.pipeline",
        "LightRagServerPipeline",
        "LightRAG server",
    ),
    IMA_PROVIDER: (
        "deeptutor.services.rag.pipelines.ima.pipeline",
        "ImaPipeline",
        "Tencent IMA",
    ),
}


def _index_probe():
    return importlib.import_module("deeptutor.services.rag.index_probe")


def normalize_provider_name(name: Optional[str] = None) -> str:
    """Return a known provider name, falling back to the default.

    Unknown / removed provider strings collapse to the default so a stale config
    never selects a pipeline that no longer exists.
    """
    candidate = (name or "").strip().lower()
    return candidate if candidate in KNOWN_PROVIDERS else DEFAULT_PROVIDER


def provider_uses_embedding_versions(provider: Optional[str]) -> bool:
    """Whether this provider's index versions are keyed by embedding signature.

    Today only the LlamaIndex pipeline uses DeepTutor's active embedding
    signature to select/read index versions. PageIndex, GraphRAG and LightRAG
    write synthetic provider signatures (``pageindex``/``graphrag``/``lightrag``)
    and should not be marked stale merely because the active embedding profile
    changed.
    """
    return normalize_provider_name(provider) == DEFAULT_PROVIDER


def version_matches_provider(entry: dict[str, Any], provider: Optional[str]) -> bool:
    """Return True when a version-list entry belongs to ``provider``."""
    resolved = normalize_provider_name(provider)
    entry_provider = str(entry.get("provider") or "").strip().lower()
    signature = str(entry.get("signature") or "").strip().lower()

    if resolved == DEFAULT_PROVIDER:
        return entry_provider in {"", DEFAULT_PROVIDER} and signature not in {
            PAGEINDEX_PROVIDER,
            PAGEINDEX_OSS_PROVIDER,
            GRAPHRAG_PROVIDER,
            LIGHTRAG_PROVIDER,
            LIGHTRAG_SERVER_PROVIDER,
            IMA_PROVIDER,
        }

    return entry_provider == resolved or signature == resolved


def has_ready_provider_index(kb_dir: str | Path, provider: Optional[str]) -> bool:
    """Return whether ``kb_dir`` has a ready index for ``provider``."""
    return _index_probe().has_ready_provider_index(kb_dir, provider)


def version_has_provider_output(entry: dict[str, Any], provider: Optional[str]) -> bool:
    """Return True when a version entry is ready and has real provider output."""
    return _index_probe().inspect_provider_version(entry, provider).ready


def provider_failure_summary(
    kb_dir: str | Path,
    provider: Optional[str],
    *,
    limit: int = 3,
) -> str:
    """Return a short provider-specific failure summary, when available."""
    return _index_probe().provider_failure_summary(kb_dir, provider, limit=limit)


def _build_pipeline(provider: str, kb_base_dir: Optional[str], **kwargs: Any):
    module_name, class_name, display_name = _PIPELINE_IMPORTS[provider]
    try:
        pipeline_type = getattr(importlib.import_module(module_name), class_name)
    except ModuleNotFoundError as exc:  # pragma: no cover - optional provider
        raise RuntimeError(f"{display_name} pipeline is unavailable") from exc
    if provider in {PAGEINDEX_PROVIDER, PAGEINDEX_OSS_PROVIDER}:
        kwargs.setdefault("provider", provider)
    if kb_base_dir is not None:
        kwargs.setdefault("kb_base_dir", kb_base_dir)
    return pipeline_type(**kwargs)


def get_pipeline(
    name: str = DEFAULT_PROVIDER,
    kb_base_dir: Optional[str] = None,
    **kwargs: Any,
):
    """Return a pipeline instance for ``name`` (cached when no custom kwargs)."""
    provider = normalize_provider_name(name)

    if kwargs:
        # Custom kwargs (e.g. an injected client/loader): build a fresh instance
        # and skip the cache so overrides are honoured.
        return _build_pipeline(provider, kb_base_dir, **kwargs)

    cache_key = (kb_base_dir, provider)
    if cache_key not in _PIPELINE_CACHE:
        _PIPELINE_CACHE[cache_key] = _build_pipeline(provider, kb_base_dir)
    return _PIPELINE_CACHE[cache_key]


def list_pipelines() -> List[Dict[str, Any]]:
    """Describe the available pipelines for the UI provider picker."""
    try:
        pageindex_config = importlib.import_module(
            "deeptutor.services.rag.pipelines.pageindex.config"
        )
        pageindex_ready = pageindex_config.is_pageindex_configured()
    except Exception:
        pageindex_ready = False

    try:
        pageindex_client = importlib.import_module(
            "deeptutor.services.rag.pipelines.pageindex.client"
        )
        pageindex_client.resolve_oss_sdk_config()
        pageindex_oss_ready, pageindex_oss_reason = True, ""
    except Exception as exc:
        pageindex_oss_ready = False
        pageindex_oss_reason = str(exc)

    try:
        ima_config = importlib.import_module("deeptutor.services.rag.pipelines.ima.config")
        ima_ready = ima_config.is_ima_configured()
    except Exception:
        ima_ready = False

    try:
        graphrag_config = importlib.import_module(
            "deeptutor.services.rag.pipelines.graphrag.config"
        )
        graphrag_ready = graphrag_config.is_graphrag_available()
        graphrag_modes = list(graphrag_config.SUPPORTED_MODES)
        graphrag_default_mode = graphrag_config.DEFAULT_MODE
    except Exception:
        graphrag_ready, graphrag_modes, graphrag_default_mode = False, [], ""

    try:
        lightrag_config = importlib.import_module(
            "deeptutor.services.rag.pipelines.lightrag.config"
        )
        lightrag_ready = lightrag_config.is_lightrag_available()
        lightrag_modes = list(lightrag_config.SUPPORTED_MODES)
        lightrag_default_mode = lightrag_config.DEFAULT_MODE
    except Exception:
        lightrag_ready, lightrag_modes, lightrag_default_mode = False, [], ""

    try:
        lightrag_server_config = importlib.import_module(
            "deeptutor.services.rag.pipelines.lightrag_server.config"
        )
        lightrag_server_modes = list(lightrag_server_config.SUPPORTED_MODES)
        lightrag_server_default_mode = lightrag_server_config.DEFAULT_MODE
    except Exception:
        lightrag_server_modes, lightrag_server_default_mode = [], ""

    return [
        {
            "id": DEFAULT_PROVIDER,
            "name": "LlamaIndex",
            "description": "Local vector retrieval with hybrid BM25/vector fusion. Works out of the box.",
            "configured": True,
            "requires_api_key": False,
        },
        {
            "id": PAGEINDEX_PROVIDER,
            "name": "PageIndex Cloud",
            "description": "Hosted, vectorless engine: the chat agent reads documents through PageIndex SDK tools. Requires an API key; PDF, Office, text and Markdown formats.",
            "configured": pageindex_ready,
            "requires_api_key": True,
        },
        {
            "id": PAGEINDEX_OSS_PROVIDER,
            "name": "PageIndex OSS",
            "description": "Local, chunkless and vectorless document indexing. Uses the active LLM and accepts PDF files.",
            "configured": pageindex_oss_ready,
            "requires_api_key": False,
            "readiness_reason": pageindex_oss_reason,
        },
        {
            "id": GRAPHRAG_PROVIDER,
            "name": "GraphRAG",
            "description": "Local knowledge-graph retrieval (global/local/drift/basic). Needs `pip install 'deeptutor[graphrag]'`; indexing is LLM-heavy.",
            "configured": graphrag_ready,
            "requires_api_key": False,
            "modes": graphrag_modes,
            "default_mode": graphrag_default_mode,
        },
        {
            "id": LIGHTRAG_PROVIDER,
            "name": "LightRAG",
            "description": "Graph + vector retrieval with multimodal parsing (naive/local/global/hybrid/mix). Needs `pip install 'deeptutor[rag-lightrag]'`; indexing is LLM-heavy.",
            "configured": lightrag_ready,
            "requires_api_key": False,
            "modes": lightrag_modes,
            "default_mode": lightrag_default_mode,
        },
        {
            "id": LIGHTRAG_SERVER_PROVIDER,
            "name": "LightRAG Server",
            "description": "Retrieval offloaded to an external, standalone LightRAG server you run. No local index — connect a KB to its URL and query it over HTTP (naive/local/global/hybrid/mix).",
            # Always available: it's a thin HTTP client with no install or global
            # credential. The endpoint is configured per-KB at connect time.
            "configured": True,
            "requires_api_key": False,
            "modes": lightrag_server_modes,
            "default_mode": lightrag_server_default_mode,
        },
        {
            "id": IMA_PROVIDER,
            "name": "Tencent IMA",
            "description": (
                "Retrieval offloaded to a knowledge base you keep in Tencent IMA. "
                "No local index and no copy — connect a KB to its IMA library and "
                "query it over IMA's OpenAPI. Chat can also browse the library's "
                "documents, read a full source, search your IMA notes, and (when "
                "you ask) collect a web page or save a note. Uploading files still "
                "happens in IMA itself. Requires an IMA Client ID and API key."
            ),
            # A thin HTTPS client with no install; readiness is only about the
            # account credentials. The library id stays per-KB, set at connect
            # time, and a KB may pin its own credentials to reach another account.
            "configured": ima_ready,
            "requires_api_key": True,
        },
    ]


__all__ = [
    "DEFAULT_PROVIDER",
    "PAGEINDEX_PROVIDER",
    "PAGEINDEX_OSS_PROVIDER",
    "GRAPHRAG_PROVIDER",
    "LIGHTRAG_PROVIDER",
    "LIGHTRAG_SERVER_PROVIDER",
    "IMA_PROVIDER",
    "KNOWN_PROVIDERS",
    "get_pipeline",
    "has_ready_provider_index",
    "list_pipelines",
    "normalize_provider_name",
    "provider_failure_summary",
    "provider_uses_embedding_versions",
    "version_has_provider_output",
    "version_matches_provider",
]
