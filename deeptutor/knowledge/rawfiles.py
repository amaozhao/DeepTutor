"""Raw document file operations for knowledge bases."""

from __future__ import annotations

import mimetypes
from pathlib import Path
import shutil

from fastapi import HTTPException

from deeptutor.knowledge.uploads import safe_join_raw, sanitize_rel_subdir


def list_raw_files(raw_dir: Path) -> list[dict]:
    """List files and folders under a KB raw directory."""
    if not raw_dir.exists() or not raw_dir.is_dir():
        return []

    files = []
    for entry in sorted(raw_dir.rglob("*"), key=lambda p: str(p).lower()):
        rel = entry.relative_to(raw_dir).as_posix()
        if entry.is_dir():
            files.append({"name": rel, "type": "folder"})
            continue
        if not entry.is_file():
            continue
        try:
            stat = entry.stat()
        except OSError:
            continue
        media_type, _ = mimetypes.guess_type(entry.name)
        files.append(
            {
                "name": rel,
                "type": "file",
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "mime_type": media_type,
            }
        )
    return files


def create_raw_folder(raw_dir: Path, path: str) -> str:
    """Create a safe subfolder under ``raw_dir`` and return its relative path."""
    subdir = sanitize_rel_subdir(path)
    if not subdir:
        raise HTTPException(status_code=400, detail="Folder name is required")
    target = safe_join_raw(raw_dir, subdir)
    target.mkdir(parents=True, exist_ok=True)
    return subdir


def move_raw_path(raw_dir: Path, source: str, dest_folder: str = "") -> str:
    """Move a raw file/folder to another safe folder under ``raw_dir``."""
    source_rel = sanitize_rel_subdir(source)
    if not source_rel:
        raise HTTPException(status_code=400, detail="Source path is required")
    src = safe_join_raw(raw_dir, source_rel)
    if not src.exists():
        raise HTTPException(status_code=404, detail="Source not found")

    dest_folder_rel = sanitize_rel_subdir(dest_folder)
    dest_dir = safe_join_raw(raw_dir, dest_folder_rel) if dest_folder_rel else raw_dir.resolve()
    dest = dest_dir / src.name

    if dest.resolve() == src.resolve():
        return source_rel
    if src.is_dir() and dest_dir.resolve().is_relative_to(src.resolve()):
        raise HTTPException(status_code=400, detail="Cannot move a folder into itself")
    if dest.exists():
        raise HTTPException(
            status_code=409,
            detail=f"'{src.name}' already exists in the target folder",
        )

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    return dest.relative_to(raw_dir.resolve()).as_posix()
