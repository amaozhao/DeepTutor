"""Routes for linked folders attached to writable knowledge bases."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from deeptutor.api.utils.task_log_stream import get_task_stream_manager
from deeptutor.knowledge.providers import validate_registered_provider
from deeptutor.multi_user.knowledge_access import manager_for_resource, resolve_kb
from deeptutor.services.rag.factory import DEFAULT_PROVIDER

logger = logging.getLogger(__name__)
router = APIRouter()

_writable_kb: Callable[[str], tuple[Any, str, Path]] | None = None
_load_kb_entry: Callable[[Any, str], dict] | None = None
_assert_not_connected: Callable[[str, dict], None] | None = None
_assert_writable_or_409: Callable[[str, dict], None] | None = None
_build_task_id: Callable[[str, str], str] | None = None
_upload_task: Callable[[], Callable[..., Any]] | None = None


def set_dependencies(
    *,
    writable_kb: Callable[[str], tuple[Any, str, Path]],
    load_kb_entry: Callable[[Any, str], dict],
    assert_not_connected: Callable[[str, dict], None],
    assert_writable_or_409: Callable[[str, dict], None],
    build_task_id: Callable[[str, str], str],
    upload_task: Callable[[], Callable[..., Any]],
) -> None:
    """Wire shared knowledge-router helpers without importing the owning router."""
    global _writable_kb
    global _load_kb_entry
    global _assert_not_connected
    global _assert_writable_or_409
    global _build_task_id
    global _upload_task
    _writable_kb = writable_kb
    _load_kb_entry = load_kb_entry
    _assert_not_connected = assert_not_connected
    _assert_writable_or_409 = assert_writable_or_409
    _build_task_id = build_task_id
    _upload_task = upload_task


def _deps() -> tuple[
    Callable[[str], tuple[Any, str, Path]],
    Callable[[Any, str], dict],
    Callable[[str, dict], None],
    Callable[[str, dict], None],
    Callable[[str, str], str],
    Callable[[], Callable[..., Any]],
]:
    if (
        _writable_kb is None
        or _load_kb_entry is None
        or _assert_not_connected is None
        or _assert_writable_or_409 is None
        or _build_task_id is None
        or _upload_task is None
    ):  # pragma: no cover - router wiring invariant
        raise RuntimeError("Linked-folder router dependencies are not configured")
    return (
        _writable_kb,
        _load_kb_entry,
        _assert_not_connected,
        _assert_writable_or_409,
        _build_task_id,
        _upload_task,
    )


class LinkFolderRequest(BaseModel):
    """Request model for linking a local folder to a KB."""

    folder_path: str


class LinkedFolderInfo(BaseModel):
    """Response model for linked folder information."""

    id: str
    path: str
    added_at: str
    file_count: int


@router.post("/{kb_name}/link-folder", response_model=LinkedFolderInfo)
async def link_folder(kb_name: str, request: LinkFolderRequest):
    """
    Link a local folder to a knowledge base.

    This allows syncing documents from a local folder (which can be synced
    with SharePoint, Google Drive, OneLake, etc.) to the KB.
    """
    writable_kb, load_kb_entry, assert_not_connected, *_ = _deps()
    try:
        manager, resolved_name, _ = writable_kb(kb_name)
        assert_not_connected(resolved_name, load_kb_entry(manager, resolved_name))
        folder_info = manager.link_folder(resolved_name, request.folder_path)
        logger.info("Linked folder '%s' to KB '%s'", request.folder_path, kb_name)
        return LinkedFolderInfo(**folder_info)
    except HTTPException:
        raise
    except ValueError as exc:
        error_msg = str(exc)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg) from exc
        raise HTTPException(status_code=400, detail=error_msg) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{kb_name}/linked-folders", response_model=list[LinkedFolderInfo])
async def get_linked_folders(kb_name: str):
    """Get list of linked folders for a knowledge base."""
    try:
        resource = resolve_kb(kb_name)
        manager = manager_for_resource(resource)
        folders = manager.get_linked_folders(resource.name)
        return [LinkedFolderInfo(**folder) for folder in folders]
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail=f"Knowledge base '{kb_name}' not found"
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{kb_name}/linked-folders/{folder_id}")
async def unlink_folder(kb_name: str, folder_id: str):
    """Unlink a folder from a knowledge base."""
    writable_kb = _deps()[0]
    try:
        manager, resolved_name, _ = writable_kb(kb_name)
        success = manager.unlink_folder(resolved_name, folder_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Folder '{folder_id}' not found")
        logger.info("Unlinked folder '%s' from KB '%s'", folder_id, kb_name)
        return {"message": "Folder unlinked successfully", "folder_id": folder_id}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail=f"Knowledge base '{kb_name}' not found"
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{kb_name}/sync-folder/{folder_id}")
async def sync_folder(kb_name: str, folder_id: str, background_tasks: BackgroundTasks):
    """Sync new or modified files from a linked folder to the knowledge base."""
    (
        writable_kb,
        load_kb_entry,
        _assert_not_connected,
        assert_writable_or_409,
        build_task_id,
        upload_task,
    ) = _deps()
    try:
        manager, resolved_name, kb_base_dir = writable_kb(kb_name)
        kb_entry = load_kb_entry(manager, resolved_name)
        assert_writable_or_409(resolved_name, kb_entry)
        kb_provider = validate_registered_provider(kb_entry.get("rag_provider") or DEFAULT_PROVIDER)

        folders = manager.get_linked_folders(resolved_name)
        folder_info = next((folder for folder in folders if folder["id"] == folder_id), None)
        if not folder_info:
            raise HTTPException(status_code=404, detail=f"Linked folder '{folder_id}' not found")

        folder_path = folder_info["path"]
        changes = manager.detect_folder_changes(resolved_name, folder_id)
        files_to_process = changes["new_files"] + changes["modified_files"]
        if not files_to_process:
            return {"message": "No new or modified files to sync", "files": [], "file_count": 0}

        logger.info(
            "Syncing %s files from folder '%s' to KB '%s'",
            len(files_to_process),
            folder_path,
            resolved_name,
        )
        task_id = build_task_id("kb_upload", f"{resolved_name}_folder_{folder_id}")
        get_task_stream_manager().ensure_task(task_id)

        manager.update_kb_status(
            name=resolved_name,
            status="processing",
            progress={
                "stage": "starting",
                "message": f"Syncing {len(files_to_process)} file(s) from linked folder...",
                "percent": 0,
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
            },
        )

        background_tasks.add_task(
            upload_task(),
            kb_name=resolved_name,
            base_dir=str(kb_base_dir),
            uploaded_file_paths=files_to_process,
            task_id=task_id,
            rag_provider=kb_provider,
            folder_id=folder_id,
        )

        return {
            "message": f"Syncing {len(files_to_process)} files from linked folder",
            "folder_path": folder_path,
            "new_files": changes["new_count"],
            "modified_files": changes["modified_count"],
            "file_count": len(files_to_process),
            "task_id": task_id,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail=f"Knowledge base '{kb_name}' not found"
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
