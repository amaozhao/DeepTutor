"""Linked-folder metadata helpers for knowledge bases."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path

from deeptutor.services.file_io import atomic_write_json
from deeptutor.services.rag.file_routing import FileTypeRouter


def _metadata_file(base_dir: Path, kb_name: str) -> Path:
    return base_dir / kb_name / "metadata.json"


def _load_metadata(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_metadata(path: Path, metadata: dict) -> None:
    atomic_write_json(path, metadata)


def link_folder(base_dir: Path, kb_name: str, folder_path: str) -> dict:
    folder = Path(folder_path).expanduser().resolve()
    if not folder.exists():
        raise ValueError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise ValueError(f"Path is not a directory: {folder}")

    files = FileTypeRouter.collect_supported_files(folder, recursive=True)
    folder_id = hashlib.md5(str(folder).encode(), usedforsecurity=False).hexdigest()[:8]  # noqa: S324

    metadata_file = _metadata_file(base_dir, kb_name)
    metadata = _load_metadata(metadata_file)
    linked_folders = metadata.setdefault("linked_folders", [])

    for item in linked_folders:
        if item.get("id") == folder_id:
            return item

    folder_info = {
        "id": folder_id,
        "path": str(folder),
        "added_at": datetime.now().isoformat(),
        "file_count": len(files),
    }
    linked_folders.append(folder_info)
    _save_metadata(metadata_file, metadata)
    return folder_info


def get_linked_folders(base_dir: Path, kb_name: str) -> list[dict]:
    metadata = _load_metadata(_metadata_file(base_dir, kb_name))
    linked_folders = metadata.get("linked_folders", [])
    return linked_folders if isinstance(linked_folders, list) else []


def unlink_folder(base_dir: Path, kb_name: str, folder_id: str) -> bool:
    metadata_file = _metadata_file(base_dir, kb_name)
    metadata = _load_metadata(metadata_file)
    linked = metadata.get("linked_folders", [])
    if not isinstance(linked, list):
        return False

    new_linked = [folder for folder in linked if folder.get("id") != folder_id]
    if len(new_linked) == len(linked):
        return False

    metadata["linked_folders"] = new_linked
    _save_metadata(metadata_file, metadata)
    return True


def scan_linked_folder(folder_path: str) -> list[str]:
    folder = Path(folder_path).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        return []
    return sorted(
        str(file_path)
        for file_path in FileTypeRouter.collect_supported_files(folder, recursive=True)
    )


def detect_folder_changes(base_dir: Path, kb_name: str, folder_id: str) -> dict:
    folders = get_linked_folders(base_dir, kb_name)
    folder_info = next((folder for folder in folders if folder.get("id") == folder_id), None)
    if not folder_info:
        raise ValueError(f"Linked folder not found: {folder_id}")

    folder_path = Path(folder_info["path"]).expanduser().resolve()
    synced_files = folder_info.get("synced_files", {})
    if not isinstance(synced_files, dict):
        synced_files = {}

    new_files = []
    modified_files = []
    for file_path in FileTypeRouter.collect_supported_files(folder_path, recursive=True):
        file_str = str(file_path)
        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        if file_str not in synced_files:
            new_files.append(file_str)
            continue
        try:
            if file_mtime > datetime.fromisoformat(synced_files[file_str]):
                modified_files.append(file_str)
        except Exception:
            modified_files.append(file_str)

    return {
        "new_files": sorted(new_files),
        "modified_files": sorted(modified_files),
        "has_changes": bool(new_files or modified_files),
        "new_count": len(new_files),
        "modified_count": len(modified_files),
    }


def update_folder_sync_state(
    base_dir: Path, kb_name: str, folder_id: str, synced_files: list[str]
) -> None:
    metadata_file = _metadata_file(base_dir, kb_name)
    metadata = _load_metadata(metadata_file)
    linked = metadata.get("linked_folders", [])
    if not isinstance(linked, list):
        return

    for folder in linked:
        if folder.get("id") != folder_id:
            continue
        folder["last_sync"] = datetime.now().isoformat()
        file_states = folder.get("synced_files", {})
        if not isinstance(file_states, dict):
            file_states = {}
        for file_path in synced_files:
            try:
                path = Path(file_path)
                if path.exists():
                    file_states[file_path] = datetime.fromtimestamp(
                        path.stat().st_mtime
                    ).isoformat()
            except Exception:
                pass
        folder["synced_files"] = file_states
        folder["file_count"] = len(file_states)
        _save_metadata(metadata_file, metadata)
        return
