"""Routes for connecting external knowledge sources."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from deeptutor.services.rag.factory import DEFAULT_PROVIDER
from deeptutor.services.rag.linked_kb import assert_path_allowed, probe_linked_folder

logger = logging.getLogger(__name__)
router = APIRouter()

_manager_resolver: Callable[[], Any] | None = None


def set_kb_manager_resolver(resolver: Callable[[], Any]) -> None:
    """Set the owning router's KB manager resolver."""
    global _manager_resolver
    _manager_resolver = resolver


def _get_kb_manager() -> Any:
    if _manager_resolver is None:  # pragma: no cover - router wiring invariant
        raise RuntimeError("KB manager resolver is not configured")
    return _manager_resolver()


class ConnectObsidianRequest(BaseModel):
    name: str
    vault_path: str


@router.post("/connect-obsidian")
async def connect_obsidian_vault(payload: ConnectObsidianRequest):
    """Connect an existing Obsidian vault as a knowledge base."""
    name = (payload.name or "").strip()
    vault_path = (payload.vault_path or "").strip()
    if not name or not vault_path:
        raise HTTPException(status_code=400, detail="Both name and vault_path are required.")
    try:
        folder = assert_path_allowed(vault_path)
        manager = _get_kb_manager()
        entry = manager.register_obsidian_vault(name, str(folder))
        return {"status": "connected", "name": name, "vault_path": entry["vault_path"]}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error connecting Obsidian vault: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class ProbeFolderRequest(BaseModel):
    folder_path: str
    rag_provider: str = DEFAULT_PROVIDER


class ConnectFolderRequest(BaseModel):
    name: str
    folder_path: str
    rag_provider: str = DEFAULT_PROVIDER


@router.post("/probe-folder")
async def probe_linked_folder_route(payload: ProbeFolderRequest):
    """Inspect a local folder for a ready engine index before linking it."""
    folder_path = (payload.folder_path or "").strip()
    if not folder_path:
        raise HTTPException(status_code=400, detail="folder_path is required.")
    try:
        folder = assert_path_allowed(folder_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = probe_linked_folder(str(folder), payload.rag_provider)
    return result.to_dict()


@router.post("/connect-folder")
async def connect_linked_folder_route(payload: ConnectFolderRequest):
    """Mount an existing engine index as a read-only linked knowledge base."""
    name = (payload.name or "").strip()
    folder_path = (payload.folder_path or "").strip()
    if not name or not folder_path:
        raise HTTPException(status_code=400, detail="Both name and folder_path are required.")
    try:
        folder = assert_path_allowed(folder_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = probe_linked_folder(str(folder), payload.rag_provider)
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error or "Folder is not linkable.")

    stats = {
        "embedding_model": result.embedding.index_model,
        "doc_count": result.doc_count,
    }
    try:
        manager = _get_kb_manager()
        entry = manager.register_linked_kb(
            name,
            str(folder),
            result.provider,
            stats=stats,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error connecting linked folder: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "status": "connected",
        "name": name,
        "external_path": entry["external_path"],
        "rag_provider": entry["rag_provider"],
        "warnings": result.warnings,
    }


class ProbeLightRagServerRequest(BaseModel):
    server_url: str
    api_key: str = ""


class ConnectLightRagServerRequest(BaseModel):
    name: str
    server_url: str
    api_key: str = ""
    search_mode: str = ""


@router.post("/probe-lightrag-server")
async def probe_lightrag_server_route(payload: ProbeLightRagServerRequest):
    """Test-connect to an external LightRAG server before binding a KB to it."""
    from deeptutor.services.rag.pipelines.lightrag_server.probe import probe_server

    server_url = (payload.server_url or "").strip()
    if not server_url:
        raise HTTPException(status_code=400, detail="server_url is required.")
    result = await probe_server(server_url, payload.api_key or "")
    return result.to_dict()


@router.post("/connect-lightrag-server")
async def connect_lightrag_server_route(payload: ConnectLightRagServerRequest):
    """Connect an external LightRAG server as a retrieval-only knowledge base."""
    from deeptutor.services.rag.pipelines.lightrag_server.config import SUPPORTED_MODES
    from deeptutor.services.rag.pipelines.lightrag_server.probe import probe_server

    name = (payload.name or "").strip()
    server_url = (payload.server_url or "").strip()
    if not name or not server_url:
        raise HTTPException(status_code=400, detail="Both name and server_url are required.")

    result = await probe_server(server_url, payload.api_key or "")
    if not result.ok:
        raise HTTPException(
            status_code=400, detail=result.error or "Could not connect to the LightRAG server."
        )

    search_mode = (payload.search_mode or "").strip().lower()
    if search_mode and search_mode not in SUPPORTED_MODES:
        search_mode = ""

    try:
        manager = _get_kb_manager()
        entry = manager.register_lightrag_server_kb(
            name,
            result.base_url,
            api_key=payload.api_key or "",
            search_mode=search_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error connecting LightRAG server: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "status": "connected",
        "name": name,
        "server_url": entry["server_url"],
        "rag_provider": entry["rag_provider"],
    }
