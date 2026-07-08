"""Knowledge-base metadata and info projections."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deeptutor.knowledge.kb_types import external_root_of
from deeptutor.services.rag.embedding_signature import signature_from_embedding_config
from deeptutor.services.rag.factory import normalize_provider_name, provider_uses_embedding_versions
from deeptutor.services.rag.index_probe import (
    inspect_kb_versions,
    inspect_provider_version,
    provider_failure_summary,
)
from deeptutor.services.rag.index_versioning import find_matching_version


def embedding_fields(kb_config: dict) -> dict:
    fields = {}
    for key in ("embedding_model", "embedding_dim"):
        val = kb_config.get(key)
        if val is not None:
            fields[key] = val
    if kb_config.get("embedding_mismatch"):
        fields["embedding_mismatch"] = True
    return fields


def get_metadata(kb_name: str, kb_config: dict) -> dict:
    if not kb_config:
        return {}

    metadata = {
        "name": kb_name,
        "description": kb_config.get("description", f"Knowledge base: {kb_name}"),
        "rag_provider": normalize_provider_name(kb_config.get("rag_provider")),
        "needs_reindex": bool(kb_config.get("needs_reindex", False)),
        "created_at": kb_config.get("created_at"),
        "last_updated": kb_config.get("updated_at"),
        "last_indexed_at": kb_config.get("last_indexed_at"),
        "last_indexed_count": kb_config.get("last_indexed_count"),
        "last_indexed_action": kb_config.get("last_indexed_action"),
        "type": kb_config.get("type"),
        "vault_path": kb_config.get("vault_path"),
        "external_path": kb_config.get("external_path"),
        "server_url": kb_config.get("server_url"),
        "agent_kind": kb_config.get("agent_kind"),
        "cwd": kb_config.get("cwd"),
        "partner_id": kb_config.get("partner_id"),
    }
    metadata.update(embedding_fields(kb_config))
    return {key: value for key, value in metadata.items() if value is not None}


def _count_files(kb_dir: Path, dir_exists: bool) -> tuple[int, int, int]:
    if not dir_exists:
        return 0, 0, 0

    raw_count = 0
    images_count = 0
    content_lists_count = 0

    raw_dir = kb_dir / "raw"
    images_dir = kb_dir / "images"
    content_list_dir = kb_dir / "content_list"

    try:
        raw_count = (
            len([path for path in raw_dir.rglob("*") if path.is_file()]) if raw_dir.is_dir() else 0
        )
    except Exception:
        pass

    try:
        images_count = len([path for path in images_dir.iterdir() if path.is_file()])
    except Exception:
        pass

    try:
        content_lists_count = len(list(content_list_dir.glob("*.json")))
    except Exception:
        pass

    return raw_count, images_count, content_lists_count


def get_info(base_dir: Path, kb_name: str, kb_config: dict, is_default: bool) -> dict:
    external = external_root_of(kb_config)
    kb_dir = Path(external).expanduser() if external else base_dir / kb_name

    status = kb_config.get("status")
    progress = kb_config.get("progress")
    rag_provider = normalize_provider_name(kb_config.get("rag_provider"))
    needs_reindex = bool(kb_config.get("needs_reindex", False))

    live_status = status in {"initializing", "processing"}
    if live_status and isinstance(progress, dict):
        live_status = progress.get("stage") not in {"completed", "error"}
    effective_needs_reindex = needs_reindex and not live_status

    dir_exists = kb_dir.exists()
    index_versions: list[dict[str, Any]] = []
    has_ready_provider = False
    if dir_exists:
        index_versions = inspect_kb_versions(kb_dir, rag_provider)
        has_ready_provider = any(bool(version.get("ready")) for version in index_versions)
    provider_error_summary = provider_failure_summary(kb_dir, rag_provider) if dir_exists else ""

    if effective_needs_reindex:
        status = "needs_reindex"
    elif status == "ready" and not has_ready_provider and provider_error_summary:
        status = "error"
        progress = {
            "stage": "error",
            "message": "Previous indexing failed.",
            "error": provider_error_summary,
        }
    elif (
        status in {"processing", "initializing"}
        and has_ready_provider
        and not (isinstance(progress, dict) and progress.get("stage") == "error")
    ):
        status = "ready"
        progress = None
    elif not status and dir_exists:
        rag_storage_dir = kb_dir / "rag_storage"
        if has_ready_provider:
            status = "ready"
        elif rag_storage_dir.exists() and any(rag_storage_dir.iterdir()):
            status = "needs_reindex"
            effective_needs_reindex = True
        else:
            status = "unknown"
    elif not status:
        status = "unknown"

    metadata = get_metadata(kb_name, kb_config)
    metadata.pop("cwd", None)
    metadata.pop("partner_id", None)
    metadata["needs_reindex"] = effective_needs_reindex
    if kb_config.get("last_error"):
        metadata["last_error"] = kb_config.get("last_error")
    if kb_config.get("last_error_at"):
        metadata["last_error_at"] = kb_config.get("last_error_at")

    raw_count, images_count, content_lists_count = _count_files(kb_dir, dir_exists)

    kb_probe_dir = kb_dir if dir_exists else None
    rag_initialized = has_ready_provider
    active_signature = signature_from_embedding_config()
    if provider_uses_embedding_versions(rag_provider):
        matched_entry = (
            find_matching_version(kb_probe_dir, active_signature)
            if (kb_probe_dir and active_signature)
            else None
        )
        active_match = (
            inspect_provider_version(matched_entry, rag_provider).ready if matched_entry else False
        )
    else:
        active_match = rag_initialized

    return {
        "name": kb_name,
        "path": str(kb_dir),
        "is_default": is_default,
        "metadata": {key: value for key, value in metadata.items() if value is not None},
        "status": status,
        "progress": progress,
        "statistics": {
            "raw_documents": raw_count,
            "images": images_count,
            "content_lists": content_lists_count,
            "rag_initialized": rag_initialized,
            "rag_provider": rag_provider,
            "needs_reindex": effective_needs_reindex,
            "index_versions": index_versions,
            "active_signature": active_signature.hash() if active_signature else None,
            "active_match": active_match,
            "status": status,
            "progress": progress,
        },
    }
