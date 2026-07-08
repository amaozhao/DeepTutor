"""Knowledge-base configuration routes mounted under knowledge."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from deeptutor.knowledge.providers import validate_registered_provider
from deeptutor.services.config import get_kb_config_service
from deeptutor.services.rag.factory import DEFAULT_PROVIDER
from deeptutor.services.rag.index_probe import has_ready_provider_index

logger = logging.getLogger(__name__)
router = APIRouter()

_kb_base_dir_resolver: Callable[[], Path] | None = None


def set_kb_base_dir_resolver(resolver: Callable[[], Path]) -> None:
    """Set the owning router's KB base-dir resolver."""
    global _kb_base_dir_resolver
    _kb_base_dir_resolver = resolver


def _current_kb_base_dir() -> Path:
    if _kb_base_dir_resolver is None:  # pragma: no cover - router wiring invariant
        raise RuntimeError("KB base-dir resolver is not configured")
    return _kb_base_dir_resolver()


@router.get("/configs")
async def get_all_kb_configs():
    """Get all knowledge base configurations from centralized config file."""
    try:
        service = get_kb_config_service()
        return service.get_all_configs()
    except Exception as exc:
        logger.error("Error getting KB configs: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{kb_name}/config")
async def get_kb_config(kb_name: str):
    """Get configuration for a specific knowledge base."""
    try:
        service = get_kb_config_service()
        config = service.get_kb_config(kb_name)
        return {"kb_name": kb_name, "config": config}
    except Exception as exc:
        logger.error("Error getting config for KB '%s': %s", kb_name, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/{kb_name}/config")
async def update_kb_config(kb_name: str, config: dict):
    """Update configuration for a specific knowledge base."""
    try:
        config = dict(config or {})
        if "rag_provider" in config:
            requested_provider = validate_registered_provider(config.get("rag_provider"))
            service = get_kb_config_service()
            current_config = service.get_kb_config(kb_name)
            current_provider = validate_registered_provider(
                current_config.get("rag_provider") or DEFAULT_PROVIDER
            )
            if requested_provider != current_provider:
                kb_dir = _current_kb_base_dir() / kb_name
                if kb_dir.exists() and has_ready_provider_index(kb_dir, current_provider):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Knowledge base '{kb_name}' already has a ready "
                            f"{current_provider} index. Provider changes require "
                            "an explicit re-index/migration instead of a silent config edit."
                        ),
                    )
                config["needs_reindex"] = True
                config.setdefault("status", "needs_reindex")
                config["progress"] = {
                    "stage": "needs_reindex",
                    "message": (
                        f"Provider changed from {current_provider} to {requested_provider}; "
                        "re-index this knowledge base before use."
                    ),
                    "percent": 0,
                    "timestamp": datetime.now().isoformat(),
                }
            config["rag_provider"] = requested_provider
        else:
            service = get_kb_config_service()

        service.set_kb_config(kb_name, config)
        return {"status": "success", "kb_name": kb_name, "config": service.get_kb_config(kb_name)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error updating config for KB '%s': %s", kb_name, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/configs/sync")
async def sync_configs_from_metadata():
    """Sync all KB configurations from their metadata.json files to centralized config."""
    try:
        service = get_kb_config_service()
        service.sync_all_from_metadata(_current_kb_base_dir())
        return {"status": "success", "message": "Configurations synced from metadata files"}
    except Exception as exc:
        logger.error("Error syncing configs: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
