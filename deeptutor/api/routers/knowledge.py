"""
Knowledge Base API Router
=========================

Handles knowledge base CRUD operations, file uploads, and initialization.
"""

from datetime import datetime
import logging
import mimetypes
from pathlib import Path
import traceback
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from deeptutor.api.routers import knowledge_config as knowledge_config_router
from deeptutor.api.routers import knowledge_linked as knowledge_linked_router
from deeptutor.api.routers import knowledge_links as knowledge_links_router
from deeptutor.api.routers import knowledge_progress as knowledge_progress_router
from deeptutor.api.routers import rag as rag_router
from deeptutor.api.utils.task_id_manager import TaskIDManager
from deeptutor.api.utils.task_log_stream import get_task_stream_manager
from deeptutor.knowledge.add_documents import remove_raw_document
from deeptutor.knowledge.initializer import KnowledgeBaseInitializer
from deeptutor.knowledge.kb_types import is_connected_kb
from deeptutor.knowledge.manager import KnowledgeBaseManager
from deeptutor.knowledge.naming import validate_knowledge_base_name
from deeptutor.knowledge.progress_tracker import ProgressStage, ProgressTracker
from deeptutor.knowledge.providers import (
    assert_provider_ready as _assert_provider_ready,
)
from deeptutor.knowledge.providers import (
    enforce_provider_formats as _enforce_provider_formats,
)
from deeptutor.knowledge.providers import (
    validate_registered_provider as _validate_registered_provider,
)
from deeptutor.knowledge.rawfiles import create_raw_folder, list_raw_files, move_raw_path
from deeptutor.knowledge.tasks import (
    run_initialization_task,
    run_reindex_task,
    run_upload_processing_task,
)
from deeptutor.knowledge.tasks import (
    set_kb_manager_resolver as _set_task_kb_manager_resolver,
)
from deeptutor.knowledge.uploads import (
    safe_join_raw as _safe_join_raw,
)
from deeptutor.knowledge.uploads import (
    save_uploaded_files as _save_uploaded_files,
)
from deeptutor.knowledge.uploads import (
    validate_upload_batch as _validate_upload_batch,
)
from deeptutor.multi_user.context import get_current_user
from deeptutor.multi_user.knowledge_access import (
    assert_writable,
    current_kb_base_dir,
    current_kb_manager,
    manager_for_resource,
    resolve_kb,
)
from deeptutor.multi_user.knowledge_access import (
    list_visible_knowledge_bases as list_visible_kb_access,
)
from deeptutor.services.config import PROJECT_ROOT, load_config_with_main
from deeptutor.services.rag.factory import (
    DEFAULT_PROVIDER,
    provider_uses_embedding_versions,
)
from deeptutor.services.rag.file_routing import FileTypeRouter
from deeptutor.utils.document_extractor import (
    MAX_EXTRACTED_CHARS_PER_DOC,
    DocumentExtractionError,
    extract_text_from_path,
)
from deeptutor.utils.document_validator import DocumentValidator
from deeptutor.utils.error_utils import format_exception_message

# Initialize logger with config
config = load_config_with_main("main.yaml", PROJECT_ROOT)
log_dir = config.get("paths", {}).get("user_log_dir") or config.get("logging", {}).get("log_dir")
logger = logging.getLogger(__name__)

router = APIRouter()
_set_task_kb_manager_resolver(lambda: get_kb_manager())
knowledge_config_router.set_kb_base_dir_resolver(lambda: _current_kb_base_dir())
knowledge_linked_router.set_dependencies(
    writable_kb=lambda kb_name: _writable_kb(kb_name),
    load_kb_entry=lambda manager, kb_name: _load_kb_entry_or_404(manager, kb_name),
    assert_not_connected=lambda kb_name, kb_entry: _assert_not_connected_kb(kb_name, kb_entry),
    assert_writable_or_409=lambda kb_name, kb_entry: _assert_kb_writable_or_409(
        kb_name, kb_entry
    ),
    build_task_id=lambda task_type, task_key_prefix: _build_unique_task_id(
        task_type, task_key_prefix
    ),
    upload_task=lambda: run_upload_processing_task,
)
knowledge_links_router.set_kb_manager_resolver(lambda: get_kb_manager())
knowledge_progress_router.set_dependencies(
    kb_base_dir=lambda: _current_kb_base_dir(),
    writable_kb=lambda kb_name: _writable_kb(kb_name),
)
router.include_router(rag_router.router)
router.include_router(knowledge_config_router.router)
router.include_router(knowledge_linked_router.router)
router.include_router(knowledge_links_router.router)
router.include_router(knowledge_progress_router.router)

_kb_base_dir = PROJECT_ROOT / "data" / "knowledge_bases"
DEFAULT_KB_ALIASES = {"", "default", "current", "selected", "默认", "默认知识库", "当前知识库"}

# Lazy initialization
kb_manager = None


def get_kb_manager():
    """Get KnowledgeBaseManager instance (lazy init)"""
    if kb_manager is not None:
        return kb_manager
    return current_kb_manager()


def _overridden_kb_manager() -> KnowledgeBaseManager | None:
    """Return the legacy/test manager when the route-level getter is patched.

    Production multi-user access control goes through ``assert_writable`` and
    ``resolve_kb``. Older tests and single-module integrations patch
    ``get_kb_manager`` directly, so we keep that seam without weakening the
    normal write guard.
    """
    manager = get_kb_manager()
    if kb_manager is not None or manager is not current_kb_manager():
        return manager
    return None


def _current_kb_base_dir() -> Path:
    manager = _overridden_kb_manager()
    if manager is not None:
        return Path(manager.base_dir)
    return current_kb_base_dir()


def _writable_kb(kb_name: str) -> tuple[KnowledgeBaseManager, str, Path]:
    manager = _overridden_kb_manager()
    if manager is not None:
        resolved_name = _resolve_registered_kb_name(manager, kb_name)
        return manager, resolved_name, Path(manager.base_dir)
    resource = assert_writable(kb_name)
    return manager_for_resource(resource), resource.name, resource.base_dir


class KnowledgeBaseInfo(BaseModel):
    id: str | None = None
    name: str
    is_default: bool
    statistics: dict
    metadata: dict | None = None
    path: str | None = None
    status: str | None = None
    progress: dict | None = None
    source: str | None = None
    assigned: bool = False
    read_only: bool = False
    provenance_label: str | None = None
    available: bool = True


class SupportedFileTypesInfo(BaseModel):
    """Upload constraints exposed to the web client."""

    extensions: list[str]
    accept: str
    max_file_size_bytes: int


IMAGE_ACCEPT_MIME_TYPES = {
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}


def _build_unique_task_id(task_type: str, task_key_prefix: str) -> str:
    task_manager = TaskIDManager.get_instance()
    task_key = f"{task_key_prefix}_{datetime.now().isoformat()}_{uuid4().hex[:8]}"
    return task_manager.generate_task_id(task_type, task_key)


def _resolve_registered_kb_name(manager: KnowledgeBaseManager, kb_name: str | None) -> str:
    """Resolve route-level default aliases to the configured default KB."""
    requested = str(kb_name or "").strip()
    kb_names = manager.list_knowledge_bases()
    if requested and requested in kb_names:
        return requested

    if requested.lower() in DEFAULT_KB_ALIASES:
        default_kb = manager.get_default()
        if default_kb and default_kb in kb_names:
            return default_kb
        raise HTTPException(status_code=404, detail="No default knowledge base is configured")

    raise HTTPException(status_code=404, detail=f"Knowledge base '{requested}' not found")


def _load_kb_entry_or_404(manager: KnowledgeBaseManager, kb_name: str) -> dict:
    manager.config = manager._load_config()
    kb_entry = manager.config.get("knowledge_bases", {}).get(kb_name)
    if kb_entry is None:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")
    return kb_entry


def _assert_not_connected_kb(kb_name: str, kb_entry: dict) -> None:
    """Block writes to connected KBs (Obsidian vaults, linked indexes).

    They are read-only pointers to the user's external files — we never write
    into or re-index them.
    """
    if is_connected_kb(kb_entry):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Knowledge base '{kb_name}' is connected to an external folder and is "
                "read-only. Uploads and re-indexing are not available for it."
            ),
        )


def _assert_kb_writable_or_409(kb_name: str, kb_entry: dict) -> None:
    _assert_not_connected_kb(kb_name, kb_entry)
    if bool(kb_entry.get("needs_reindex", False)):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Knowledge base '{kb_name}' uses legacy index format and needs reindex "
                "before accepting incremental uploads."
            ),
        )


def _matching_index_is_valid(kb_name: str, matching_version: dict | None) -> bool:
    """Return whether a matching active index can safely satisfy retrieval."""
    if not matching_version:
        return False
    try:
        from deeptutor.services.rag.index_probe import inspect_provider_version
        from deeptutor.services.rag.pipelines.llamaindex.storage import (
            validate_storage_embeddings,
        )

        probe = inspect_provider_version(matching_version, DEFAULT_PROVIDER)
        if not probe.ready:
            logger.warning(
                "Matching index for KB '%s' is not provider-ready; forcing re-index: %s",
                kb_name,
                probe.failure_summary or probe.diagnostics,
            )
            return False
        validate_storage_embeddings(Path(str(matching_version["storage_path"])))
        return True
    except Exception as exc:
        logger.warning(
            "Matching index for KB '%s' is invalid; forcing re-index: %s",
            kb_name,
            exc,
        )
        return False


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        manager = get_kb_manager()
        config_exists = manager.config_file.exists()
        kb_count = len(manager.list_knowledge_bases())
        return {
            "status": "ok",
            "config_file": str(manager.config_file),
            "config_exists": config_exists,
            "base_dir": str(manager.base_dir),
            "base_dir_exists": manager.base_dir.exists(),
            "knowledge_bases_count": kb_count,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


@router.get("/supported-file-types", response_model=SupportedFileTypesInfo)
async def get_supported_file_types():
    """Return the current upload policy so the web client stays in sync."""
    extensions = sorted(FileTypeRouter.get_supported_extensions())
    accept_items = extensions + [
        mime
        for extension, mime in sorted(IMAGE_ACCEPT_MIME_TYPES.items())
        if extension in FileTypeRouter.IMAGE_EXTENSIONS
    ]
    return SupportedFileTypesInfo(
        extensions=extensions,
        accept=",".join(dict.fromkeys(accept_items)),
        max_file_size_bytes=DocumentValidator.MAX_FILE_SIZE,
    )


@router.get("/default")
async def get_default_kb():
    """Get the default knowledge base."""
    try:
        manager = get_kb_manager()
        default_kb = manager.get_default()
        return {"default_kb": default_kb}
    except Exception as e:
        logger.error(f"Error getting default KB: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/default/{kb_name}")
async def set_default_kb(kb_name: str):
    """Set the default knowledge base."""
    try:
        manager, kb_name, _ = _writable_kb(kb_name)

        # Verify KB exists
        if kb_name not in manager.list_knowledge_bases():
            raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")

        manager.set_default(kb_name)
        return {"status": "success", "default_kb": kb_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting default KB: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=list[KnowledgeBaseInfo])
async def list_knowledge_bases():
    """List all available knowledge bases with their details."""
    try:
        manager = get_kb_manager()
        kb_names = manager.list_knowledge_bases()
        access_items = list_visible_kb_access()
        access_by_id = {str(item.get("id") or ""): item for item in access_items}
        own_prefix = "admin:kb:" if get_current_user().is_admin else "user:kb:"

        logger.debug(f"Found {len(kb_names)} knowledge bases: {kb_names}")

        result = []
        errors = []

        for name in kb_names:
            try:
                info = manager.get_info(name)
                logger.debug(f"Successfully got info for KB '{name}': {info.get('statistics', {})}")
                result.append(
                    KnowledgeBaseInfo(
                        id=f"{own_prefix}{info['name']}",
                        name=info["name"],
                        is_default=info["is_default"],
                        statistics=info.get("statistics", {}),
                        metadata=info.get("metadata"),
                        path=info.get("path"),
                        status=info.get("status"),
                        progress=info.get("progress"),
                        source="admin" if get_current_user().is_admin else "user",
                        assigned=False,
                        read_only=False,
                        provenance_label=access_by_id.get(f"{own_prefix}{info['name']}", {}).get(
                            "provenance_label"
                        ),
                    )
                )
            except Exception as e:
                error_msg = f"Error getting info for KB '{name}': {e}"
                errors.append(error_msg)
                logger.warning(f"{error_msg}\n{traceback.format_exc()}")
                try:
                    kb_dir = manager.base_dir / name
                    if kb_dir.exists():
                        logger.debug(f"KB '{name}' directory exists, creating error fallback info")
                        fallback_progress = {
                            "stage": "error",
                            "message": "Failed to load knowledge base info.",
                            "error": error_msg,
                        }
                        result.append(
                            KnowledgeBaseInfo(
                                id=f"{own_prefix}{name}",
                                name=name,
                                is_default=name == manager.get_default(),
                                statistics={
                                    "raw_documents": 0,
                                    "images": 0,
                                    "content_lists": 0,
                                    "rag_initialized": False,
                                },
                                metadata={"name": name, "last_error": error_msg},
                                path=str(kb_dir),
                                status="error",
                                progress=fallback_progress,
                                source="admin" if get_current_user().is_admin else "user",
                            )
                        )
                except Exception as fallback_err:
                    logger.error(f"Fallback also failed for KB '{name}': {fallback_err}")

        if errors and not result:
            error_detail = f"Failed to load knowledge bases. Errors: {'; '.join(errors)}"
            logger.error(error_detail)
            raise HTTPException(status_code=500, detail=error_detail)

        if errors:
            logger.warning(
                f"Some KBs had errors, returning {len(result)} results. Errors: {errors}"
            )

        logger.debug(f"Returning {len(result)} knowledge bases")
        if not get_current_user().is_admin:
            own_ids = {item.id for item in result}
            for access in access_items:
                if access.get("source") != "admin" or access.get("id") in own_ids:
                    continue
                if not access.get("available", True):
                    result.append(
                        KnowledgeBaseInfo(
                            id=str(access.get("id") or ""),
                            name=str(access.get("name") or ""),
                            is_default=False,
                            statistics={},
                            metadata={},
                            path=None,
                            status="unavailable",
                            progress=None,
                            source="admin",
                            assigned=True,
                            read_only=True,
                            provenance_label=str(access.get("provenance_label") or ""),
                            available=False,
                        )
                    )
                    continue
                resource = resolve_kb(str(access.get("id") or access.get("name") or ""))
                assigned_manager = manager_for_resource(resource)
                try:
                    info = assigned_manager.get_info(resource.name)
                    result.append(
                        KnowledgeBaseInfo(
                            id=resource.id,
                            name=info["name"],
                            is_default=False,
                            statistics=info.get("statistics", {}),
                            metadata=info.get("metadata"),
                            path=None,
                            status=info.get("status"),
                            progress=info.get("progress"),
                            source="admin",
                            assigned=True,
                            read_only=True,
                            provenance_label=str(access.get("provenance_label") or ""),
                        )
                    )
                except Exception as exc:
                    error_msg = f"Error getting assigned KB '{resource.name}': {exc}"
                    result.append(
                        KnowledgeBaseInfo(
                            id=resource.id,
                            name=resource.name,
                            is_default=False,
                            statistics={},
                            metadata={"name": resource.name, "last_error": error_msg},
                            status="error",
                            progress={
                                "stage": "error",
                                "message": "Failed to load assigned knowledge base info.",
                                "error": error_msg,
                            },
                            source="admin",
                            assigned=True,
                            read_only=True,
                            provenance_label=str(access.get("provenance_label") or ""),
                        )
                    )
        return result
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error listing knowledge bases: {e}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to list knowledge bases: {e!s}")


@router.get("/{kb_name}")
async def get_knowledge_base_details(kb_name: str):
    """Get detailed info for a specific KB."""
    try:
        resource = resolve_kb(kb_name)
        manager = manager_for_resource(resource)
        info = manager.get_info(resource.name)
        info.update(
            {
                "id": resource.id,
                "source": resource.source,
                "assigned": resource.assigned,
                "read_only": resource.read_only,
            }
        )
        if resource.assigned:
            info.pop("path", None)
        return info
    except HTTPException:
        raise
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _resolve_kb_raw_dir(kb_name: str) -> Path:
    """Resolve the raw/ directory for a KB, validating that it exists."""
    manager = _overridden_kb_manager()
    if manager is not None:
        resolved_name = _resolve_registered_kb_name(manager, kb_name)
        return manager.get_knowledge_base_path(resolved_name) / "raw"
    resource = resolve_kb(kb_name)
    manager = manager_for_resource(resource)
    kb_path = manager.get_knowledge_base_path(resource.name)
    return kb_path / "raw"


def _resolve_kb_raw_file_or_404(kb_name: str, filename: str) -> Path:
    """Resolve a raw KB file while preventing traversal outside raw/."""
    raw_dir = _resolve_kb_raw_dir(kb_name)
    if not raw_dir.exists():
        raise HTTPException(status_code=404, detail="File not found")

    target = _safe_join_raw(raw_dir, filename)

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return target


@router.get("/{kb_name}/files")
async def list_kb_raw_files(kb_name: str):
    """List raw documents under <kb>/raw/, recursing into folders.

    ``name`` is the POSIX path relative to ``raw/`` so the web client can
    rebuild the folder tree. Folders (including empty ones) are returned as
    ``type: "folder"`` entries so user-created/uploaded structure shows even
    before it holds any files. Folders are purely organizational and have no
    effect on indexing or retrieval.
    """
    return {"files": list_raw_files(_resolve_kb_raw_dir(kb_name))}


class CreateFolderPayload(BaseModel):
    path: str


class MoveFilePayload(BaseModel):
    source: str
    dest_folder: str = ""


@router.post("/{kb_name}/folders")
async def create_kb_folder(kb_name: str, payload: CreateFolderPayload):
    """Create an (organizational) folder under <kb>/raw/. No retrieval effect."""
    manager, kb_name, _ = _writable_kb(kb_name)
    _assert_kb_writable_or_409(kb_name, _load_kb_entry_or_404(manager, kb_name))
    raw_dir = manager.get_knowledge_base_path(kb_name) / "raw"
    return {"status": "ok", "path": create_raw_folder(raw_dir, payload.path)}


@router.post("/{kb_name}/files/move")
async def move_kb_file(kb_name: str, payload: MoveFilePayload):
    """Move a file/folder between organizational folders (display only).

    Moving never re-indexes: folders don't affect retrieval, so this is a pure
    filesystem relocation under ``raw/``.
    """
    manager, kb_name, _ = _writable_kb(kb_name)
    _assert_kb_writable_or_409(kb_name, _load_kb_entry_or_404(manager, kb_name))
    raw_dir = manager.get_knowledge_base_path(kb_name) / "raw"
    return {"status": "ok", "path": move_raw_path(raw_dir, payload.source, payload.dest_folder)}


@router.get("/{kb_name}/file-preview-text/{filename:path}")
async def serve_kb_raw_file_text_preview(kb_name: str, filename: str):
    """Serve extracted plain text for a raw KB document preview."""
    target = _resolve_kb_raw_file_or_404(kb_name, filename)
    try:
        text = extract_text_from_path(
            target,
            max_bytes=DocumentValidator.MAX_FILE_SIZE,
            max_chars=MAX_EXTRACTED_CHARS_PER_DOC,
        )
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc

    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")


@router.get("/{kb_name}/files/{filename:path}")
async def serve_kb_raw_file(kb_name: str, filename: str):
    """Serve a single raw document for inline preview / download.

    Resolution is sandboxed to the KB's raw/ directory; any path that
    escapes via traversal yields 403.
    """
    target = _resolve_kb_raw_file_or_404(kb_name, filename)
    media_type, _ = mimetypes.guess_type(target.name)
    return FileResponse(
        target,
        media_type=media_type or "application/octet-stream",
        filename=target.name,
        content_disposition_type="inline",
    )


@router.delete("/{kb_name}/files/{filename:path}")
async def delete_kb_file(kb_name: str, filename: str):
    """Remove a single raw document from a knowledge base."""
    manager, kb_name, _ = _writable_kb(kb_name)
    _assert_kb_writable_or_409(kb_name, _load_kb_entry_or_404(manager, kb_name))
    target = _resolve_kb_raw_file_or_404(kb_name, filename)

    removal = remove_raw_document(Path(manager.get_knowledge_base_path(kb_name)), target)
    return {
        "status": "ok",
        "path": removal.rel_path,
        "was_indexed": removal.was_indexed,
    }


@router.delete("/{kb_name}")
async def delete_knowledge_base(kb_name: str):
    """Delete a knowledge base."""
    try:
        manager, resolved_name, _ = _writable_kb(kb_name)
        success = manager.delete_knowledge_base(resolved_name, confirm=True)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete knowledge base")
        logger.info(f"KB '{kb_name}' deleted")
        return {"message": f"Knowledge base '{kb_name}' deleted successfully"}
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_name}/upload")
async def upload_files(
    kb_name: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    rag_provider: str = Form(None),
    rel_paths: list[str] = Form(None),
):
    """Upload files to a knowledge base and process them in background."""
    try:
        manager, kb_name, kb_base_dir = _writable_kb(kb_name)
        kb_path = manager.get_knowledge_base_path(kb_name)
        raw_dir = kb_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        requested_provider = None
        if rag_provider is not None and str(rag_provider).strip():
            requested_provider = _validate_registered_provider(rag_provider)

        kb_entry = _load_kb_entry_or_404(manager, kb_name)
        _assert_kb_writable_or_409(kb_name, kb_entry)
        kb_provider = _validate_registered_provider(
            kb_entry.get("rag_provider") or DEFAULT_PROVIDER
        )
        if requested_provider and requested_provider != kb_provider:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Requested provider '{requested_provider}' does not match KB provider '{kb_provider}'. "
                    "A knowledge base is locked to the engine it was created with."
                ),
            )
        _assert_provider_ready(kb_provider)
        _enforce_provider_formats(kb_provider, files)
        allowed_extensions = FileTypeRouter.get_supported_extensions()
        # ``.zip`` is accepted as an upload container; its members are
        # validated against ``allowed_extensions`` during extraction and the
        # archive itself is never indexed (``safe_extract_zip`` skips ``.zip``).
        upload_extensions = allowed_extensions | {".zip"}
        _validate_upload_batch(files, allowed_extensions=upload_extensions, rel_paths=rel_paths)
        uploaded_files, uploaded_file_paths = _save_uploaded_files(
            files, raw_dir, allowed_extensions=upload_extensions, rel_paths=rel_paths
        )
        task_id = _build_unique_task_id("kb_upload", kb_name)
        get_task_stream_manager().ensure_task(task_id)

        logger.info(f"Uploading {len(uploaded_files)} files to KB '{kb_name}'")

        manager.update_kb_status(
            name=kb_name,
            status="processing",
            progress={
                "stage": "starting",
                "message": f"Processing {len(uploaded_files)} uploaded file(s)...",
                "percent": 0,
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
            },
        )

        background_tasks.add_task(
            run_upload_processing_task,
            kb_name=kb_name,
            base_dir=str(kb_base_dir),
            uploaded_file_paths=uploaded_file_paths,
            task_id=task_id,
            rag_provider=kb_provider,
        )

        return {
            "message": f"Uploaded {len(uploaded_files)} files. Processing in background.",
            "files": uploaded_files,
            "task_id": task_id,
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_name}' not found")
    except Exception as e:
        # Unexpected failure (Server error)
        formatted_error = format_exception_message(e)
        raise HTTPException(status_code=500, detail=formatted_error) from e


@router.post("/create")
async def create_knowledge_base(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    files: list[UploadFile] = File(...),
    rag_provider: str = Form(DEFAULT_PROVIDER),
    rel_paths: list[str] = Form(None),
):
    """Create a new knowledge base and initialize it with files."""
    try:
        try:
            name = validate_knowledge_base_name(name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        manager = get_kb_manager()
        kb_base_dir = _current_kb_base_dir()
        if name in manager.list_knowledge_bases():
            raise HTTPException(status_code=400, detail=f"Knowledge base '{name}' already exists")

        rag_provider = _validate_registered_provider(rag_provider)
        _assert_provider_ready(rag_provider)
        _enforce_provider_formats(rag_provider, files)
        allowed_extensions = FileTypeRouter.get_supported_extensions()
        _validate_upload_batch(files, allowed_extensions=allowed_extensions, rel_paths=rel_paths)

        logger.info(f"Creating KB: {name} (provider={rag_provider})")
        task_id = _build_unique_task_id("kb_init", name)
        get_task_stream_manager().ensure_task(task_id)

        # Register KB to kb_config.json immediately with "initializing" status
        # This ensures the KB appears in the list right away
        manager.update_kb_status(
            name=name,
            status="initializing",
            progress={
                "stage": "initializing",
                "message": "Initializing knowledge base...",
                "percent": 0,
                "current": 0,
                "total": len(files),
                "task_id": task_id,
            },
        )
        # Also store rag_provider in config (reload and update)
        manager.config = manager._load_config()
        if name in manager.config.get("knowledge_bases", {}):
            manager.config["knowledge_bases"][name]["rag_provider"] = rag_provider
            manager.config["knowledge_bases"][name]["needs_reindex"] = False
            manager._save_config()

        progress_tracker = ProgressTracker(name, kb_base_dir)

        initializer = KnowledgeBaseInitializer(
            kb_name=name,
            base_dir=str(kb_base_dir),
            progress_tracker=progress_tracker,
            rag_provider=rag_provider,
        )

        initializer.create_directory_structure()
        progress_tracker.task_id = task_id

        manager = get_kb_manager()
        if name not in manager.list_knowledge_bases():
            logger.warning(f"KB {name} not found in config, registering manually")
            initializer._register_to_config()

        uploaded_files, _ = _save_uploaded_files(
            files, initializer.raw_dir, allowed_extensions=allowed_extensions, rel_paths=rel_paths
        )

        progress_tracker.update(
            ProgressStage.PROCESSING_DOCUMENTS,
            f"Saved {len(uploaded_files)} files, preparing to process...",
            current=0,
            total=len(uploaded_files),
        )

        background_tasks.add_task(run_initialization_task, initializer, task_id)

        logger.info(f"KB '{name}' created, processing {len(uploaded_files)} files in background")

        return {
            "message": f"Knowledge base '{name}' created. Processing {len(uploaded_files)} files in background.",
            "name": name,
            "files": uploaded_files,
            "task_id": task_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create KB: {e}")
        logger.debug(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_name}/reindex")
async def reindex_knowledge_base(
    kb_name: str,
    background_tasks: BackgroundTasks,
):
    """Re-index ``kb_name`` through its bound RAG provider.

    LlamaIndex still keys versions by the active embedding model. The other
    providers keep synthetic provider-keyed versions, so they should rebuild
    without requiring an embedding-signature precheck.
    """
    try:
        manager, kb_name, kb_base_dir = _writable_kb(kb_name)
        kb_entry = _load_kb_entry_or_404(manager, kb_name)
        _assert_not_connected_kb(kb_name, kb_entry)
        force_reindex = str(kb_entry.get("status") or "").lower() == "error"
        kb_provider = _validate_registered_provider(
            kb_entry.get("rag_provider") or DEFAULT_PROVIDER
        )
        _assert_provider_ready(kb_provider)

        kb_dir = kb_base_dir / kb_name
        signature_hash = kb_provider
        if provider_uses_embedding_versions(kb_provider):
            from deeptutor.services.rag.embedding_signature import signature_from_embedding_config
            from deeptutor.services.rag.index_versioning import (
                find_matching_version,
            )

            signature = signature_from_embedding_config()
            if signature is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "No embedding model is configured. Set up the embedding "
                        "profile in Settings before re-indexing."
                    ),
                )

            signature_hash = signature.hash()
            matching_version = find_matching_version(kb_dir, signature)
            matching_valid = _matching_index_is_valid(kb_name, matching_version)
            if (
                matching_version
                and matching_version.get("layout") == "flat"
                and matching_valid
                and not force_reindex
            ):
                return {
                    "message": (
                        f"Knowledge base '{kb_name}' already has an index for the "
                        "active embedding configuration; no reindex needed."
                    ),
                    "task_id": None,
                    "signature": signature_hash,
                    "noop": True,
                }

        task_id = _build_unique_task_id("kb_reindex", kb_name)
        get_task_stream_manager().ensure_task(task_id)

        manager.update_kb_status(
            name=kb_name,
            status="initializing",
            progress={
                "stage": "starting",
                "message": "Queueing re-index...",
                "percent": 0,
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
            },
        )

        background_tasks.add_task(
            run_reindex_task,
            kb_name=kb_name,
            base_dir=str(kb_base_dir),
            task_id=task_id,
            signature_hash=signature_hash,
        )

        return {
            "message": f"Re-indexing '{kb_name}' in the background.",
            "task_id": task_id,
            "signature": signature_hash,
            "noop": False,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start reindex for '{kb_name}': {e}")
        raise HTTPException(status_code=500, detail=format_exception_message(e))


@router.post("/{kb_name}/retry")
async def retry_knowledge_base(
    kb_name: str,
    background_tasks: BackgroundTasks,
):
    """Retry a failed KB initialization/indexing run from its stored raw files."""
    try:
        manager, resolved_name, _ = _writable_kb(kb_name)
        kb_entry = _load_kb_entry_or_404(manager, resolved_name)
        status = str(kb_entry.get("status") or "").lower()
        progress = kb_entry.get("progress") if isinstance(kb_entry.get("progress"), dict) else {}
        progress_stage = str(progress.get("stage") or "").lower()
        if status != "error" and progress_stage != "error":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Knowledge base '{resolved_name}' is not in an error state. "
                    "Use re-index when you want to rebuild a healthy knowledge base."
                ),
            )
        return await reindex_knowledge_base(resolved_name, background_tasks)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry KB '{kb_name}': {e}")
        raise HTTPException(status_code=500, detail=format_exception_message(e))
