"""Upload and raw-folder path helpers for knowledge bases."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import tempfile
import zipfile

from fastapi import HTTPException, UploadFile

from deeptutor.utils.archive_extractor import ArchiveTooLargeError, safe_extract_zip
from deeptutor.utils.document_validator import DocumentValidator
from deeptutor.utils.error_utils import format_exception_message

logger = logging.getLogger(__name__)

BYTES_PER_GB = 1024**3
BYTES_PER_MB = 1024**2
_BAD_PATH_CHARS = re.compile(r'[\\:*?"<>|\x00-\x1f]')


def format_bytes_human_readable(size_bytes: int) -> str:
    """Format bytes into a short human-readable string."""
    if size_bytes >= BYTES_PER_GB:
        return f"{size_bytes / BYTES_PER_GB:.1f} GB"
    if size_bytes >= BYTES_PER_MB:
        return f"{size_bytes / BYTES_PER_MB:.1f} MB"
    return f"{size_bytes} bytes"


def sanitize_path_segment(segment: str) -> str:
    """Sanitize a single folder/file path segment for safe filesystem use."""
    cleaned = _BAD_PATH_CHARS.sub("", segment).strip().strip(".")
    return cleaned[:128]


def sanitize_rel_subdir(rel_path: str | None) -> str:
    """Return a safe POSIX relative subdirectory path."""
    if not rel_path:
        return ""
    parts: list[str] = []
    for raw_seg in str(rel_path).replace("\\", "/").split("/"):
        seg = raw_seg.strip()
        if seg in ("", "."):
            continue
        if seg == "..":
            raise HTTPException(status_code=400, detail="Invalid folder path")
        safe = sanitize_path_segment(seg)
        if safe:
            parts.append(safe)
    return "/".join(parts)


def safe_join_raw(raw_dir: Path, rel_path: str) -> Path:
    """Resolve ``rel_path`` under ``raw_dir``, rejecting traversal."""
    target = (raw_dir / rel_path).resolve()
    try:
        target.relative_to(raw_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    return target


def get_upload_file_size(file: UploadFile) -> int | None:
    """Best-effort byte size detection without consuming the uploaded stream."""
    try:
        current_position = file.file.tell()
        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(current_position)
        return size
    except Exception:
        return None


def save_zip_archive(
    file: UploadFile,
    sanitized_filename: str,
    target_dir: Path,
    allowed_extensions: set[str] | None,
) -> list[Path]:
    """Safely expand an uploaded ``.zip`` into ``target_dir``."""
    file.file.seek(0)
    max_size = DocumentValidator.MAX_FILE_SIZE
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            written = 0
            for chunk in iter(lambda: file.file.read(8192), b""):
                written += len(chunk)
                if written > max_size:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Archive '{sanitized_filename}' exceeds maximum size limit of "
                            f"{format_bytes_human_readable(max_size)}"
                        ),
                    )
                tmp.write(chunk)

        try:
            result = safe_extract_zip(
                tmp_path, target_dir, allowed_extensions=allowed_extensions or set()
            )
        except ArchiveTooLargeError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Rejected archive '{sanitized_filename}': {exc}",
            ) from exc
        except zipfile.BadZipFile as exc:
            raise HTTPException(
                status_code=400,
                detail=f"'{sanitized_filename}' is not a valid zip archive.",
            ) from exc

        if not result.extracted:
            raise HTTPException(
                status_code=400,
                detail=f"Archive '{sanitized_filename}' contained no supported files.",
            )
        return result.extracted
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def save_uploaded_files(
    files: list[UploadFile],
    target_dir: Path,
    allowed_extensions: set[str] | None = None,
    kb_name: str | None = None,
    rel_paths: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Save uploaded files to a KB ``raw/`` directory."""
    uploaded_files: list[str] = []
    uploaded_file_paths: list[str] = []
    written_file_paths: list[Path] = []

    from deeptutor.services.pocketbase_client import is_pocketbase_enabled

    pb_sync = is_pocketbase_enabled() and bool(kb_name)

    try:
        for idx, file in enumerate(files):
            file_path = None
            original_filename = file.filename or "upload"
            try:
                sanitized_filename = DocumentValidator.validate_upload_safety(
                    original_filename,
                    get_upload_file_size(file),
                    allowed_extensions=allowed_extensions,
                )
                file.filename = sanitized_filename

                rel = (
                    rel_paths[idx].replace("\\", "/")
                    if rel_paths and idx < len(rel_paths) and rel_paths[idx]
                    else ""
                )
                subdir = sanitize_rel_subdir(rel.rsplit("/", 1)[0]) if "/" in rel else ""
                dest_dir = target_dir / subdir if subdir else target_dir
                if subdir:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                rel_name = f"{subdir}/{sanitized_filename}" if subdir else sanitized_filename

                if Path(sanitized_filename).suffix.lower() == ".zip":
                    for dest in save_zip_archive(
                        file, sanitized_filename, dest_dir, allowed_extensions
                    ):
                        written_file_paths.append(dest)
                        uploaded_files.append(dest.relative_to(target_dir).as_posix())
                        uploaded_file_paths.append(str(dest))
                        if pb_sync and kb_name:
                            try:
                                upload_file_to_pb(kb_name, dest.name, dest)
                            except Exception as pb_exc:
                                logger.debug(
                                    "PocketBase file upload failed for '%s': %s",
                                    dest.name,
                                    pb_exc,
                                )
                    continue

                file_path = dest_dir / sanitized_filename
                max_size = DocumentValidator.MAX_FILE_SIZE
                written_bytes = 0

                file.file.seek(0)
                with open(file_path, "wb") as buffer:
                    for chunk in iter(lambda: file.file.read(8192), b""):
                        written_bytes += len(chunk)
                        if written_bytes > max_size:
                            size_str = format_bytes_human_readable(max_size)
                            raise HTTPException(
                                status_code=400,
                                detail=(
                                    f"File '{sanitized_filename}' exceeds maximum size "
                                    f"limit of {size_str}"
                                ),
                            )
                        buffer.write(chunk)

                DocumentValidator.validate_upload_safety(
                    sanitized_filename, written_bytes, allowed_extensions=allowed_extensions
                )
                written_file_paths.append(file_path)
                uploaded_files.append(rel_name)
                uploaded_file_paths.append(str(file_path))

                if pb_sync and kb_name:
                    try:
                        upload_file_to_pb(kb_name, sanitized_filename, file_path)
                    except Exception as pb_exc:
                        logger.debug(
                            "PocketBase file upload failed for '%s': %s",
                            sanitized_filename,
                            pb_exc,
                        )
            except Exception as exc:
                if file_path and file_path.exists():
                    try:
                        os.unlink(file_path)
                    except OSError:
                        pass

                error_message = (
                    f"Validation failed for file '{original_filename}': "
                    f"{format_exception_message(exc)}"
                )
                logger.error(error_message, exc_info=True)
                raise HTTPException(status_code=400, detail=error_message) from exc
    except Exception:
        for written_path in written_file_paths:
            if written_path.exists():
                try:
                    os.unlink(written_path)
                except OSError:
                    pass
        raise

    return uploaded_files, uploaded_file_paths


def validate_upload_batch(
    files: list[UploadFile],
    allowed_extensions: set[str] | None = None,
    rel_paths: list[str] | None = None,
) -> list[dict[str, int | str | None]]:
    """Validate upload metadata before mutating KB state or writing files."""
    validated: list[dict[str, int | str | None]] = []
    seen_names: set[str] = set()

    for idx, file in enumerate(files):
        original_filename = file.filename or "upload"
        size_bytes = get_upload_file_size(file)
        try:
            sanitized_filename = DocumentValidator.validate_upload_safety(
                original_filename,
                size_bytes,
                allowed_extensions=allowed_extensions,
            )
        except Exception as exc:
            error_message = (
                f"Validation failed for file '{original_filename}': "
                f"{format_exception_message(exc)}"
            )
            raise HTTPException(status_code=400, detail=error_message) from exc

        rel = (
            rel_paths[idx].replace("\\", "/")
            if rel_paths and idx < len(rel_paths) and rel_paths[idx]
            else ""
        )
        subdir = sanitize_rel_subdir(rel.rsplit("/", 1)[0]) if "/" in rel else ""
        duplicate_key = f"{subdir}/{sanitized_filename}" if subdir else sanitized_filename

        if duplicate_key in seen_names:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Duplicate filename after sanitization: '{duplicate_key}'. "
                    "Rename one of the files and try again."
                ),
            )

        seen_names.add(duplicate_key)
        validated.append(
            {
                "original_filename": original_filename,
                "sanitized_filename": sanitized_filename,
                "path": duplicate_key,
                "size_bytes": size_bytes,
            }
        )

    return validated


def upload_file_to_pb(kb_name: str, filename: str, file_path: Path) -> None:
    """Upload a single file to the PocketBase knowledge_bases record."""
    try:
        from deeptutor.services.pocketbase_client import get_pb_client

        pb = get_pb_client()
        records = pb.collection("knowledge_bases").get_full_list(
            query_params={"filter": f'kb_name="{kb_name}"'}
        )
        if not records:
            logger.debug("PocketBase KB record not found for '%s', skipping file upload", kb_name)
            return
        with open(file_path, "rb") as fh:
            pb.collection("knowledge_bases").update(
                records[0].id,
                body={"kb_name": kb_name},
                files={"raw_files": (filename, fh)},
            )
        logger.debug("Uploaded '%s' to PocketBase KB '%s'", filename, kb_name)
    except Exception as exc:
        logger.debug("upload_file_to_pb failed: %s", exc)
