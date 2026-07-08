"""Background tasks for knowledge-base indexing workflows."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
import logging
from pathlib import Path
import traceback as _tb
from typing import Any

from deeptutor.api.utils.task_id_manager import TaskIDManager
from deeptutor.api.utils.task_log_stream import capture_task_logs, get_task_stream_manager
from deeptutor.knowledge.add_documents import DocumentAdder
from deeptutor.knowledge.initializer import KnowledgeBaseInitializer
from deeptutor.knowledge.progress_tracker import ProgressStage, ProgressTracker
from deeptutor.services.file_io import atomic_write_json
from deeptutor.services.rag.file_routing import FileTypeRouter
from deeptutor.services.rag.service import RAGService

logger = logging.getLogger(__name__)

_kb_manager_resolver: Callable[[], Any] | None = None


def set_kb_manager_resolver(resolver: Callable[[], Any]) -> None:
    """Set the route layer's active KB manager resolver."""
    global _kb_manager_resolver
    _kb_manager_resolver = resolver


def _get_kb_manager() -> Any:
    if _kb_manager_resolver is None:  # pragma: no cover - wiring invariant
        raise RuntimeError("KB manager resolver is not configured")
    return _kb_manager_resolver()


def _task_log(task_id: str, message: str, level: str = "info") -> None:
    manager = get_task_stream_manager()
    manager.ensure_task(task_id)
    manager.emit_log(task_id, message)

    log_method = getattr(logger, level, None)
    if callable(log_method):
        log_method("[%s] %s", task_id, message)
    else:
        logger.info("[%s] %s", task_id, message)


async def run_initialization_task(initializer: KnowledgeBaseInitializer, task_id: str) -> None:
    """Background task for knowledge base initialization."""
    task_manager = TaskIDManager.get_instance()
    task_stream_manager = get_task_stream_manager()
    task_stream_manager.ensure_task(task_id)

    with capture_task_logs(task_id):
        try:
            if not initializer.progress_tracker:
                initializer.progress_tracker = ProgressTracker(
                    initializer.kb_name, initializer.base_dir
                )

            initializer.progress_tracker.task_id = task_id

            _task_log(task_id, f"Initializing knowledge base '{initializer.kb_name}'")

            await initializer.process_documents()
            _task_log(task_id, "Document processing complete")
            _task_log(task_id, "Finalizing initialization")
            indexed_count = len(
                FileTypeRouter.collect_supported_files(initializer.raw_dir, recursive=True)
            )

            initializer.progress_tracker.update(
                ProgressStage.COMPLETED,
                "Knowledge base initialization complete!",
                current=1,
                total=1,
                indexed_count=indexed_count,
                index_changed=True,
                index_action="create",
            )

            manager = _get_kb_manager()
            manager.update_kb_status(
                name=initializer.kb_name,
                status="ready",
                progress={
                    "stage": "completed",
                    "message": "Knowledge base initialization complete!",
                    "percent": 100,
                    "current": 1,
                    "total": 1,
                    "task_id": task_id,
                    "timestamp": datetime.now().isoformat(),
                    "indexed_count": indexed_count,
                    "index_changed": True,
                    "index_action": "create",
                },
            )

            _task_log(
                task_id, f"Knowledge base '{initializer.kb_name}' initialized", level="success"
            )
            task_manager.update_task_status(task_id, "completed")
            task_stream_manager.emit_complete(
                task_id, f"Knowledge base '{initializer.kb_name}' initialization complete"
            )
        except Exception as exc:
            error_msg = str(exc)
            trace = _tb.format_exc()

            _task_log(task_id, f"Initialization failed: {error_msg}", level="error")
            _task_log(task_id, f"Stack trace:\n{trace}", level="error")

            task_manager.update_task_status(task_id, "error", error=error_msg)

            manager = _get_kb_manager()
            manager.update_kb_status(
                name=initializer.kb_name,
                status="error",
                progress={
                    "stage": "error",
                    "message": f"Initialization failed: {error_msg}",
                    "percent": 0,
                    "error": error_msg,
                    "task_id": task_id,
                    "timestamp": datetime.now().isoformat(),
                },
            )

            if initializer.progress_tracker:
                initializer.progress_tracker.update(
                    ProgressStage.ERROR, f"Initialization failed: {error_msg}", error=error_msg
                )
            task_stream_manager.emit_failed(task_id, error_msg, details=trace)


async def run_upload_processing_task(
    kb_name: str,
    base_dir: str,
    uploaded_file_paths: list[str],
    task_id: str,
    rag_provider: str | None = None,
    folder_id: str | None = None,
) -> None:
    """Process uploaded files for a knowledge base in the background."""
    task_manager = TaskIDManager.get_instance()
    task_stream_manager = get_task_stream_manager()
    task_stream_manager.ensure_task(task_id)

    progress_tracker = ProgressTracker(kb_name, Path(base_dir))
    progress_tracker.task_id = task_id

    with capture_task_logs(task_id):
        try:
            _task_log(task_id, f"Processing {len(uploaded_file_paths)} file(s) for KB '{kb_name}'")
            progress_tracker.update(
                ProgressStage.PROCESSING_DOCUMENTS,
                f"Processing {len(uploaded_file_paths)} files...",
                current=0,
                total=len(uploaded_file_paths),
            )

            adder = DocumentAdder(
                kb_name=kb_name,
                base_dir=base_dir,
                progress_tracker=progress_tracker,
                rag_provider=rag_provider,
            )

            staged_files = adder.add_documents(uploaded_file_paths, allow_duplicates=False)
            _task_log(task_id, f"Staged {len(staged_files)} new file(s)")

            if not staged_files:
                _task_log(task_id, "No new files to process (all duplicates or invalid)")
                progress_tracker.update(
                    ProgressStage.COMPLETED,
                    "No new files to process (all duplicates or invalid)",
                    current=0,
                    total=0,
                )
                task_manager.update_task_status(task_id, "completed")
                task_stream_manager.emit_complete(
                    task_id, "No new files to process (all duplicates or invalid)"
                )
                return

            index_result = await adder.process_new_documents(staged_files)
            processed_files = index_result.processed_files
            _task_log(task_id, f"Indexed {index_result.processed_count} file(s)")

            if index_result.has_failures:
                failure_summary = index_result.failure_summary()
                error_msg = (
                    f"Indexed {index_result.processed_count}/{len(staged_files)} file(s); "
                    f"{index_result.failed_count} failed: {failure_summary}"
                )
                _task_log(task_id, error_msg, level="error")
                for failure in index_result.failures:
                    _task_log(
                        task_id,
                        f"Failed to index {failure.file_path.name}: {failure.error}",
                        level="error",
                    )
                progress_tracker.update(
                    ProgressStage.ERROR,
                    f"Processing failed: {error_msg}",
                    current=index_result.processed_count,
                    total=len(staged_files),
                    error=error_msg,
                    indexed_count=index_result.processed_count,
                    index_changed=index_result.processed_count > 0,
                    index_action="upload",
                )
                task_manager.update_task_status(task_id, "error", error=error_msg)
                task_stream_manager.emit_failed(
                    task_id,
                    error_msg,
                    details="\n".join(
                        f"{failure.file_path}: {failure.error}" for failure in index_result.failures
                    ),
                )
                return

            adder.update_metadata(index_result.processed_count)

            if folder_id and processed_files:
                try:
                    manager = _get_kb_manager()
                    manager.update_folder_sync_state(
                        kb_name, folder_id, [str(path) for path in processed_files]
                    )
                    _task_log(task_id, f"Updated folder sync state: {folder_id}")
                except Exception as sync_err:
                    _task_log(
                        task_id, f"Folder sync state update failed: {sync_err}", level="warning"
                    )

            num_processed = index_result.processed_count
            progress_tracker.update(
                ProgressStage.COMPLETED,
                f"Successfully processed {num_processed} files!",
                current=num_processed,
                total=num_processed,
                indexed_count=num_processed,
                index_changed=num_processed > 0,
                index_action="upload",
            )

            _task_log(
                task_id, f"Processed {num_processed} file(s) for '{kb_name}'", level="success"
            )
            task_manager.update_task_status(task_id, "completed")
            task_stream_manager.emit_complete(
                task_id, f"Successfully processed {num_processed} files for '{kb_name}'"
            )
        except Exception as exc:
            error_msg = f"Upload processing failed (KB '{kb_name}'): {exc}"
            trace = _tb.format_exc()
            _task_log(task_id, error_msg, level="error")
            _task_log(task_id, f"Stack trace:\n{trace}", level="error")

            task_manager.update_task_status(task_id, "error", error=error_msg)

            progress_tracker.update(
                ProgressStage.ERROR, f"Processing failed: {error_msg}", error=error_msg
            )
            task_stream_manager.emit_failed(task_id, error_msg, details=trace)


async def run_reindex_task(kb_name: str, base_dir: str, task_id: str, signature_hash: str) -> None:
    """Re-index a KB's raw documents against the currently-active embedding config."""
    task_manager = TaskIDManager.get_instance()
    task_stream_manager = get_task_stream_manager()
    task_stream_manager.ensure_task(task_id)

    with capture_task_logs(task_id):
        try:
            base_path = Path(base_dir)
            kb_dir = base_path / kb_name
            raw_dir = kb_dir / "raw"
            if not raw_dir.is_dir():
                raise FileNotFoundError(f"KB '{kb_name}' has no `raw/` directory; cannot reindex.")
            file_paths = [
                str(path)
                for path in FileTypeRouter.collect_supported_files(raw_dir, recursive=True)
            ]
            if not file_paths:
                raise ValueError(f"KB '{kb_name}' has no source files in `raw/` to reindex.")

            _task_log(
                task_id,
                f"Re-indexing '{kb_name}' ({len(file_paths)} files) against signature {signature_hash}",
            )

            progress_tracker = ProgressTracker(kb_name, base_path)
            progress_tracker.task_id = task_id
            progress_tracker.update(
                ProgressStage.PROCESSING_DOCUMENTS,
                f"Re-indexing {len(file_paths)} document(s) with the active embedding model...",
                current=0,
                total=len(file_paths),
            )

            rag_service = RAGService(kb_base_dir=str(base_path), provider=None)

            def _on_progress(batch_num: int, total_batches: int) -> None:
                progress_tracker.update(
                    ProgressStage.PROCESSING_DOCUMENTS,
                    f"Embedding batches: {batch_num}/{total_batches}",
                    current=batch_num,
                    total=total_batches,
                )

            success = await rag_service.initialize(
                kb_name=kb_name,
                file_paths=file_paths,
                progress_callback=_on_progress,
            )
            if not success:
                raise RuntimeError(f"Re-index found no valid documents to index in '{kb_name}'.")

            completed_at = datetime.now().isoformat()
            metadata_file = kb_dir / "metadata.json"
            try:
                metadata = {}
                if metadata_file.exists():
                    with open(metadata_file, encoding="utf-8") as handle:
                        loaded_metadata = json.load(handle)
                    if isinstance(loaded_metadata, dict):
                        metadata = loaded_metadata
                metadata["last_updated"] = completed_at
                metadata["last_indexed_at"] = completed_at
                metadata["last_indexed_count"] = len(file_paths)
                metadata["last_indexed_action"] = "reindex"
                atomic_write_json(metadata_file, metadata)
            except Exception as meta_err:
                logger.warning(
                    "Failed to update re-index metadata for '%s': %s",
                    kb_name,
                    meta_err,
                )

            manager = _get_kb_manager()
            manager.update_kb_status(
                name=kb_name,
                status="ready",
                progress={
                    "stage": "completed",
                    "message": "Re-index complete",
                    "percent": 100,
                    "current": len(file_paths),
                    "total": len(file_paths),
                    "task_id": task_id,
                    "timestamp": completed_at,
                    "indexed_count": len(file_paths),
                    "index_changed": True,
                    "index_action": "reindex",
                },
            )
            kb_entry = manager.config.get("knowledge_bases", {}).get(kb_name) or {}
            mutated = False
            if kb_entry.get("needs_reindex"):
                kb_entry["needs_reindex"] = False
                mutated = True
            if kb_entry.get("embedding_mismatch"):
                kb_entry.pop("embedding_mismatch", None)
                mutated = True
            if mutated:
                manager._save_config()

            _task_log(task_id, f"Re-index of '{kb_name}' complete", level="success")
            task_manager.update_task_status(task_id, "completed")
            task_stream_manager.emit_complete(task_id, f"Re-index of '{kb_name}' complete")
        except Exception as exc:
            error_msg = str(exc)
            trace = _tb.format_exc()
            _task_log(task_id, f"Re-index failed: {error_msg}", level="error")
            _task_log(task_id, f"Stack trace:\n{trace}", level="error")
            task_manager.update_task_status(task_id, "error", error=error_msg)
            try:
                ProgressTracker(kb_name, Path(base_dir)).update(
                    ProgressStage.ERROR,
                    f"Re-index failed: {error_msg}",
                    error=error_msg,
                )
            except Exception:
                pass
            task_stream_manager.emit_failed(task_id, error_msg, details=trace)
