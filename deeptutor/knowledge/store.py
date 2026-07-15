"""kb_config.json storage helpers."""

from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import sys

from deeptutor.knowledge.kb_types import is_connected_kb
from deeptutor.services.embedding import get_embedding_config
from deeptutor.services.rag import embedding_signature
from deeptutor.services.rag.factory import (
    DEFAULT_PROVIDER,
    KNOWN_PROVIDERS,
    has_ready_provider_index,
    normalize_provider_name,
    provider_uses_embedding_versions,
)
from deeptutor.services.rag.index_probe import inspect_kb_versions, inspect_provider_version
from deeptutor.services.rag.index_versioning import find_matching_version

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None

logger = logging.getLogger(__name__)


@contextmanager
def _file_lock_shared(file_handle):
    if sys.platform == "win32":
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            file_handle.seek(0)
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _file_lock_exclusive(file_handle):
    if sys.platform == "win32":
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            file_handle.seek(0)
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


def _get_embedding_fingerprint() -> tuple[str, int] | None:
    try:
        cfg = get_embedding_config()
        return (cfg.model, cfg.dim)
    except Exception:
        return None


def _reconcile_embedding_flags(
    knowledge_bases: dict,
    base_dir: Path | None = None,
    embedding_fingerprint=_get_embedding_fingerprint,
) -> bool:
    fp = embedding_fingerprint()
    signature = embedding_signature.signature_from_embedding_config()
    changed = False

    if signature is None and not fp:
        return False

    for kb_name, kb_entry in knowledge_bases.items():
        if not isinstance(kb_entry, dict) or is_connected_kb(kb_entry):
            continue

        provider = normalize_provider_name(kb_entry.get("rag_provider"))
        kb_dir = (base_dir / kb_name) if base_dir is not None else None
        if not provider_uses_embedding_versions(provider):
            if kb_dir is not None:
                versions = inspect_kb_versions(kb_dir, provider)
                kb_entry["index_versions"] = versions
                if has_ready_provider_index(kb_dir, provider):
                    had_embedding_mismatch = bool(kb_entry.get("embedding_mismatch"))
                    if kb_entry.get("embedding_mismatch"):
                        kb_entry.pop("embedding_mismatch", None)
                        changed = True
                    if had_embedding_mismatch and kb_entry.get("needs_reindex"):
                        kb_entry["needs_reindex"] = False
                        changed = True
            continue

        matched = False
        if kb_dir is not None and signature is not None:
            matched_entry = find_matching_version(kb_dir, signature)
            matched = (
                matched_entry is not None
                and inspect_provider_version(matched_entry, DEFAULT_PROVIDER).ready
            )

        if matched:
            if kb_entry.get("needs_reindex"):
                kb_entry["needs_reindex"] = False
                changed = True
            if kb_entry.get("embedding_mismatch"):
                kb_entry.pop("embedding_mismatch", None)
                changed = True
            if kb_dir is not None:
                kb_entry["index_versions"] = inspect_kb_versions(kb_dir, provider)
            continue

        stored_model = kb_entry.get("embedding_model")
        versions = []
        has_ready_version = False
        if kb_dir is not None:
            versions = inspect_kb_versions(kb_dir, provider)
            has_ready_version = any(bool(version.get("ready")) for version in versions)
            kb_entry["index_versions"] = versions

        if not has_ready_version and not stored_model:
            continue

        current_model = fp[0] if fp else ""
        current_dim = fp[1] if fp else 0
        stored_dim = kb_entry.get("embedding_dim")
        mismatch = (stored_model and stored_model != current_model) or (
            stored_dim is not None and current_dim and stored_dim != current_dim
        )
        if has_ready_version:
            mismatch = True

        if mismatch and not kb_entry.get("embedding_mismatch"):
            kb_entry["embedding_mismatch"] = True
            if not kb_entry.get("needs_reindex"):
                kb_entry["needs_reindex"] = True
            changed = True
        elif not mismatch and kb_entry.get("embedding_mismatch"):
            kb_entry.pop("embedding_mismatch", None)
            changed = True

    return changed


def save_config(config_file: Path, config: dict) -> None:
    with open(config_file, "w", encoding="utf-8") as f:
        with _file_lock_exclusive(f):
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())


def load_config(
    config_file: Path,
    base_dir: Path,
    embedding_fingerprint=_get_embedding_fingerprint,
) -> dict:
    if not config_file.exists():
        return {"knowledge_bases": {}}

    try:
        with open(config_file, encoding="utf-8") as f:
            with _file_lock_shared(f):
                content = f.read()
                if not content.strip():
                    return {"knowledge_bases": {}}
                config = json.loads(content)

        if "knowledge_bases" not in config:
            config["knowledge_bases"] = {}

        if "default" in config:
            del config["default"]

        knowledge_bases = config.get("knowledge_bases", {})
        config_changed = False
        for kb_name, kb_entry in knowledge_bases.items():
            if not isinstance(kb_entry, dict) or is_connected_kb(kb_entry):
                continue

            raw_provider = kb_entry.get("rag_provider")
            provider = normalize_provider_name(raw_provider)
            if kb_entry.get("rag_provider") != provider:
                kb_entry["rag_provider"] = provider
                config_changed = True

            raw_provider_text = str(raw_provider or "").strip().lower()
            if raw_provider_text and raw_provider_text not in KNOWN_PROVIDERS:
                if not kb_entry.get("needs_reindex", False):
                    kb_entry["needs_reindex"] = True
                    config_changed = True

            kb_dir = base_dir / kb_name
            legacy_storage = kb_dir / "rag_storage"
            has_llamaindex_index = has_ready_provider_index(kb_dir, DEFAULT_PROVIDER)
            if (
                provider == DEFAULT_PROVIDER
                and legacy_storage.exists()
                and legacy_storage.is_dir()
                and not has_llamaindex_index
            ):
                if not kb_entry.get("needs_reindex", False):
                    kb_entry["needs_reindex"] = True
                    config_changed = True
                if kb_entry.get("status") == "ready":
                    kb_entry["status"] = "needs_reindex"
                    config_changed = True

        if _reconcile_embedding_flags(knowledge_bases, base_dir, embedding_fingerprint):
            config_changed = True

        if config_changed:
            try:
                save_config(config_file, config)
            except Exception as save_err:
                logger.warning(f"Failed to persist normalized KB config: {save_err}")

        return config
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Error loading config: {e}")
        return {"knowledge_bases": {}}
