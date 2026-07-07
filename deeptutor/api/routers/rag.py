"""RAG provider and pipeline settings routes mounted under knowledge."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from deeptutor.services.rag.linked_kb import LINKABLE_PROVIDERS

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/rag-providers")
async def get_rag_providers():
    """Get list of available RAG providers with the active per-engine mode."""
    try:
        from deeptutor.services.config import get_kb_config_service
        from deeptutor.services.rag.service import RAGService

        providers = RAGService.list_providers()
        kb_config = get_kb_config_service()
        for provider in providers:
            modes = provider.get("modes") or []
            if modes:
                stored = kb_config.get_provider_mode(provider["id"])
                if stored in modes:
                    provider["default_mode"] = stored
            provider["linkable"] = provider.get("id") in LINKABLE_PROVIDERS
        return {"providers": providers}
    except Exception as exc:
        logger.error("Error getting RAG providers: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class ProviderModeUpdate(BaseModel):
    """Set an engine's global default retrieval mode."""

    mode: str


@router.put("/rag-providers/{provider}/mode")
async def set_rag_provider_mode(provider: str, payload: ProviderModeUpdate):
    """Persist the default retrieval mode for a mode-aware engine."""
    from deeptutor.services.config import get_kb_config_service
    from deeptutor.services.rag.service import RAGService

    entry = next((p for p in RAGService.list_providers() if p["id"] == provider), None)
    modes = (entry or {}).get("modes") or []
    if entry is None or not modes:
        raise HTTPException(status_code=404, detail=f"No retrieval modes for engine '{provider}'.")

    mode = (payload.mode or "").strip().lower()
    if mode not in modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{payload.mode}' for {provider}. Choose one of: {', '.join(modes)}.",
        )

    get_kb_config_service().set_provider_mode(provider, mode)
    return {"provider": provider, "mode": mode}


class PageIndexConfigUpdate(BaseModel):
    # Tri-state api_key: omit/None keeps the stored key, "" clears it, any other
    # value replaces it so the masked UI never round-trips the real secret.
    api_key: str | None = None
    api_base_url: str | None = None


def _pageindex_config_payload() -> dict:
    """PageIndex pipeline settings for the UI, with the API key redacted."""
    from deeptutor.services.config import get_runtime_settings_service

    settings = get_runtime_settings_service().load_pageindex()
    return {
        "api_base_url": settings.get("api_base_url") or "",
        "api_key_set": bool(settings.get("api_key")),
        "configured": bool(settings.get("api_key")),
    }


@router.get("/rag-pipelines/pageindex/config")
async def get_pageindex_pipeline_config():
    """Read the PageIndex credential state."""
    try:
        return _pageindex_config_payload()
    except Exception as exc:
        logger.error("Error reading PageIndex config: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/rag-pipelines/pageindex/config")
async def update_pageindex_pipeline_config(payload: PageIndexConfigUpdate):
    """Persist the PageIndex API key / base URL."""
    try:
        from deeptutor.services.config import get_runtime_settings_service
        from deeptutor.services.rag.pipelines.pageindex.config import DEFAULT_API_BASE_URL

        service = get_runtime_settings_service()
        current = service.load_pageindex(include_process_overrides=False)

        api_key = current.get("api_key", "")
        if payload.api_key is not None:
            api_key = payload.api_key.strip()

        api_base_url = current.get("api_base_url") or DEFAULT_API_BASE_URL
        if payload.api_base_url is not None and payload.api_base_url.strip():
            api_base_url = payload.api_base_url.strip()

        service.save_pageindex({"api_key": api_key, "api_base_url": api_base_url})

        try:
            from deeptutor.services.mcp import get_mcp_manager

            await get_mcp_manager().reload()
        except Exception:
            logger.warning("MCP reload after PageIndex config change failed", exc_info=True)

        return _pageindex_config_payload()
    except Exception as exc:
        logger.error("Error updating PageIndex config: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class LlamaIndexConfigUpdate(BaseModel):
    """Partial update for the LlamaIndex engine knobs."""

    retrieval_profile: str | None = None
    top_k: int | None = None
    vector_top_k_multiplier: int | None = None
    bm25_top_k_multiplier: int | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None


@router.get("/rag-pipelines/llamaindex/config")
async def get_llamaindex_pipeline_config():
    """Read the LlamaIndex engine's retrieval and chunking knobs."""
    try:
        from deeptutor.services.config import get_runtime_settings_service

        return get_runtime_settings_service().load_llamaindex()
    except Exception as exc:
        logger.error("Error reading LlamaIndex config: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/rag-pipelines/llamaindex/config")
async def update_llamaindex_pipeline_config(payload: LlamaIndexConfigUpdate):
    """Persist the LlamaIndex engine knobs."""
    try:
        from deeptutor.services.config import get_runtime_settings_service

        service = get_runtime_settings_service()
        current = service.load_llamaindex(include_process_overrides=False)
        updates = payload.model_dump(exclude_none=True)
        return service.save_llamaindex({**current, **updates})
    except Exception as exc:
        logger.error("Error updating LlamaIndex config: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class GraphRagConfigUpdate(BaseModel):
    """Partial update for GraphRAG query knobs."""

    response_type: str | None = None
    community_level: int | None = None
    dynamic_community_selection: bool | None = None


@router.get("/rag-pipelines/graphrag/config")
async def get_graphrag_pipeline_config():
    """Read GraphRAG's query knobs."""
    try:
        from deeptutor.services.config import get_runtime_settings_service

        return get_runtime_settings_service().load_graphrag()
    except Exception as exc:
        logger.error("Error reading GraphRAG config: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/rag-pipelines/graphrag/config")
async def update_graphrag_pipeline_config(payload: GraphRagConfigUpdate):
    """Persist GraphRAG's query knobs."""
    try:
        from deeptutor.services.config import get_runtime_settings_service

        service = get_runtime_settings_service()
        current = service.load_graphrag()
        updates = payload.model_dump(exclude_none=True)
        return service.save_graphrag({**current, **updates})
    except Exception as exc:
        logger.error("Error updating GraphRAG config: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class LightRagConfigUpdate(BaseModel):
    """Partial update for LightRAG query knobs."""

    top_k: int | None = None
    response_type: str | None = None


@router.get("/rag-pipelines/lightrag/config")
async def get_lightrag_pipeline_config():
    """Read LightRAG's query knobs."""
    try:
        from deeptutor.services.config import get_runtime_settings_service

        return get_runtime_settings_service().load_lightrag()
    except Exception as exc:
        logger.error("Error reading LightRAG config: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/rag-pipelines/lightrag/config")
async def update_lightrag_pipeline_config(payload: LightRagConfigUpdate):
    """Persist LightRAG's query knobs."""
    try:
        from deeptutor.services.config import get_runtime_settings_service

        service = get_runtime_settings_service()
        current = service.load_lightrag()
        updates = payload.model_dump(exclude_none=True)
        return service.save_lightrag({**current, **updates})
    except Exception as exc:
        logger.error("Error updating LightRAG config: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/rag-pipelines/{provider}/preflight")
async def get_rag_pipeline_preflight(provider: str):
    """Check whether ``provider`` can run in the current environment."""
    try:
        from deeptutor.services.rag.preflight import engine_preflight

        return engine_preflight(provider)
    except Exception as exc:
        logger.error("Error running preflight for '%s': %s", provider, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


_ENGINE_MODEL_KINDS = ("llm", "embedding")


def _model_options_payload(kinds: list[str]) -> dict:
    """Secret-free model options per kind for the engine page picker."""
    from deeptutor.services.config import get_model_catalog_service

    catalog = get_model_catalog_service().load()
    services = catalog.get("services", {})
    out: dict = {}
    for kind in kinds:
        svc = services.get(kind) or {}
        options = []
        for profile in svc.get("profiles", []) or []:
            pid = profile.get("id")
            pname = profile.get("name") or pid
            for model in profile.get("models", []) or []:
                detail = ""
                if kind == "embedding" and model.get("dimension"):
                    detail = f"{model.get('dimension')}d"
                options.append(
                    {
                        "profile_id": pid,
                        "profile_name": pname,
                        "model_id": model.get("id"),
                        "label": model.get("name") or model.get("model") or model.get("id"),
                        "model": model.get("model") or "",
                        "detail": detail,
                    }
                )
        out[kind] = {
            "active": {
                "profile_id": svc.get("active_profile_id"),
                "model_id": svc.get("active_model_id"),
            },
            "options": options,
        }
    return out


@router.get("/rag-pipelines/model-options")
async def get_rag_model_options(kinds: str = "llm,embedding"):
    """List configured models for the requested model kinds."""
    try:
        requested = [
            k.strip() for k in kinds.split(",") if k.strip() in _ENGINE_MODEL_KINDS
        ] or list(_ENGINE_MODEL_KINDS)
        return _model_options_payload(requested)
    except Exception as exc:
        logger.error("Error reading model options: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class ActiveModelUpdate(BaseModel):
    """Switch the globally-active model for a kind."""

    kind: str
    profile_id: str
    model_id: str


@router.put("/rag-pipelines/active-model")
async def set_rag_active_model(payload: ActiveModelUpdate):
    """Set the active model for an engine's required kind."""
    if payload.kind not in _ENGINE_MODEL_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model kind '{payload.kind}'. Choose one of: {', '.join(_ENGINE_MODEL_KINDS)}.",
        )
    try:
        from deeptutor.services.config import get_model_catalog_service

        service = get_model_catalog_service()
        catalog = service.load()
        svc = (catalog.get("services") or {}).get(payload.kind)
        if not svc:
            raise HTTPException(status_code=404, detail=f"No '{payload.kind}' models configured.")
        profile = next(
            (p for p in svc.get("profiles", []) if p.get("id") == payload.profile_id), None
        )
        if profile is None:
            raise HTTPException(status_code=400, detail="Unknown profile for this kind.")
        if not any(m.get("id") == payload.model_id for m in profile.get("models", [])):
            raise HTTPException(status_code=400, detail="Unknown model for this profile.")
        svc["active_profile_id"] = payload.profile_id
        svc["active_model_id"] = payload.model_id
        service.apply(catalog)
        return _model_options_payload([payload.kind])[payload.kind]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error setting active model: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
