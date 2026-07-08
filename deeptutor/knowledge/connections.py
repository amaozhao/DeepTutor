"""Connected knowledge-base entry builders."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from deeptutor.knowledge.kb_types import (
    LIGHTRAG_SERVER_KB_TYPE,
    LINKED_KB_TYPE,
    OBSIDIAN_KB_TYPE,
    SUBAGENT_KB_TYPE,
)
from deeptutor.services.rag.factory import LIGHTRAG_SERVER_PROVIDER, normalize_provider_name


def register_obsidian_vault(
    knowledge_bases: dict, name: str, vault_path: str, description: str = ""
) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("Knowledge base name is required.")
    vault = Path(vault_path).expanduser()
    if not vault.is_dir():
        raise ValueError(f"Vault path is not a directory: {vault_path}")
    if name in knowledge_bases:
        raise ValueError(f"A knowledge base named '{name}' already exists.")

    now = datetime.now().isoformat()
    entry = {
        "path": name,
        "type": OBSIDIAN_KB_TYPE,
        "vault_path": str(vault.resolve()),
        "description": description or f"Obsidian vault: {name}",
        "status": "ready",
        "created_at": now,
        "updated_at": now,
    }
    knowledge_bases[name] = entry
    return entry


def register_linked_kb(
    knowledge_bases: dict,
    name: str,
    external_path: str,
    provider: str,
    *,
    description: str = "",
    stats: dict | None = None,
) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("Knowledge base name is required.")
    provider = normalize_provider_name(provider)
    folder = Path(external_path).expanduser()
    if not folder.is_dir():
        raise ValueError(f"Folder path is not a directory: {external_path}")
    if name in knowledge_bases:
        raise ValueError(f"A knowledge base named '{name}' already exists.")

    now = datetime.now().isoformat()
    entry: dict[str, Any] = {
        "path": name,
        "type": LINKED_KB_TYPE,
        "external_path": str(folder.resolve()),
        "rag_provider": provider,
        "description": description or f"Linked {provider} index: {name}",
        "status": "ready",
        "needs_reindex": False,
        "created_at": now,
        "updated_at": now,
    }
    for key in ("embedding_model", "embedding_dim", "embedding_signature"):
        if stats and stats.get(key) is not None:
            entry[key] = stats[key]
    if stats and stats.get("doc_count") is not None:
        entry["last_indexed_count"] = stats["doc_count"]
        entry["last_indexed_action"] = "link"
    knowledge_bases[name] = entry
    return entry


def register_subagent_connection(
    knowledge_bases: dict,
    name: str,
    agent_kind: str,
    *,
    cwd: str = "",
    partner_id: str = "",
    description: str = "",
) -> dict:
    name = (name or "").strip()
    agent_kind = (agent_kind or "").strip()
    partner_id = (partner_id or "").strip()
    if not name:
        raise ValueError("Connection name is required.")
    if not agent_kind:
        raise ValueError("agent_kind is required.")

    resolved_cwd = ""
    if cwd:
        folder = Path(cwd).expanduser()
        if not folder.is_dir():
            raise ValueError(f"Working directory is not a directory: {cwd}")
        resolved_cwd = str(folder.resolve())

    if name in knowledge_bases:
        raise ValueError(f"A knowledge base named '{name}' already exists.")

    now = datetime.now().isoformat()
    entry = {
        "path": name,
        "type": SUBAGENT_KB_TYPE,
        "agent_kind": agent_kind,
        "cwd": resolved_cwd,
        "partner_id": partner_id,
        "description": description or f"Connected subagent: {name}",
        "status": "ready",
        "created_at": now,
        "updated_at": now,
    }
    knowledge_bases[name] = entry
    return entry


def register_lightrag_server_kb(
    knowledge_bases: dict,
    name: str,
    server_url: str,
    *,
    api_key: str = "",
    search_mode: str = "",
    description: str = "",
) -> dict:
    name = (name or "").strip()
    server_url = (server_url or "").strip().rstrip("/")
    if not name:
        raise ValueError("Knowledge base name is required.")
    if not server_url:
        raise ValueError("LightRAG server URL is required.")
    if name in knowledge_bases:
        raise ValueError(f"A knowledge base named '{name}' already exists.")

    now = datetime.now().isoformat()
    entry: dict[str, Any] = {
        "path": name,
        "type": LIGHTRAG_SERVER_KB_TYPE,
        "rag_provider": LIGHTRAG_SERVER_PROVIDER,
        "server_url": server_url,
        "api_key": (api_key or "").strip(),
        "description": description or f"LightRAG server: {name}",
        "status": "ready",
        "needs_reindex": False,
        "created_at": now,
        "updated_at": now,
    }
    search_mode = (search_mode or "").strip().lower()
    if search_mode:
        entry["search_mode"] = search_mode
    knowledge_bases[name] = entry
    return entry
