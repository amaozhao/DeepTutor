"""Shared notebook visibility for admin-authored public materials."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Literal

from fastapi import HTTPException

from deeptutor.services.notebook.service import NotebookManager

from .context import get_current_user
from .paths import get_admin_path_service, get_current_path_service

ADMIN_NOTEBOOK_PREFIX = "admin:notebook:"
USER_NOTEBOOK_PREFIX = "user:notebook:"
NotebookSource = Literal["admin", "user"]


@dataclass(frozen=True)
class NotebookResolution:
    manager: NotebookManager
    notebook_id: str
    source: NotebookSource
    read_only: bool


def admin_notebook_manager() -> NotebookManager:
    return NotebookManager(base_dir=str(get_admin_path_service().get_notebook_dir()))


def current_notebook_manager() -> NotebookManager:
    return NotebookManager(base_dir=str(get_current_path_service().get_notebook_dir()))


def _strip_notebook_source(value: str) -> tuple[NotebookSource | None, str]:
    raw = str(value or "").strip()
    if raw.startswith(ADMIN_NOTEBOOK_PREFIX):
        return "admin", raw[len(ADMIN_NOTEBOOK_PREFIX) :]
    if raw.startswith(USER_NOTEBOOK_PREFIX):
        return "user", raw[len(USER_NOTEBOOK_PREFIX) :]
    return None, raw


def _notebook_exists(manager: NotebookManager, notebook_id: str) -> bool:
    return manager.get_notebook(notebook_id) is not None


def _visible_summary(
    notebook: dict[str, Any],
    *,
    source: NotebookSource,
    read_only: bool,
) -> dict[str, Any]:
    return {
        **notebook,
        "source": source,
        "read_only": read_only,
        "assigned": source == "admin" and read_only,
        "provenance_label": "Shared by admin" if read_only else "Created by you",
    }


def list_visible_notebooks() -> list[dict[str, Any]]:
    user = get_current_user()
    if user.is_admin:
        return [
            _visible_summary(item, source="admin", read_only=False)
            for item in admin_notebook_manager().list_notebooks()
        ]

    current = current_notebook_manager()
    user_items = [
        _visible_summary(item, source="user", read_only=False) for item in current.list_notebooks()
    ]
    user_ids = {str(item.get("id") or "") for item in user_items}
    admin_items = []
    for item in admin_notebook_manager().list_notebooks():
        if str(item.get("id") or "") in user_ids:
            continue
        admin_items.append(_visible_summary(item, source="admin", read_only=True))
    return sorted(
        [*user_items, *admin_items], key=lambda item: item.get("updated_at", 0), reverse=True
    )


def resolve_notebook_for_read(notebook_ref: str) -> NotebookResolution:
    user = get_current_user()
    requested_source, notebook_id = _strip_notebook_source(notebook_ref)
    if not notebook_id:
        raise HTTPException(status_code=404, detail="Notebook not found")

    if user.is_admin:
        manager = admin_notebook_manager()
        if not _notebook_exists(manager, notebook_id):
            raise HTTPException(status_code=404, detail="Notebook not found")
        return NotebookResolution(
            manager=manager, notebook_id=notebook_id, source="admin", read_only=False
        )

    current = current_notebook_manager()
    admin = admin_notebook_manager()

    if requested_source == "user":
        if not _notebook_exists(current, notebook_id):
            raise HTTPException(status_code=404, detail="Notebook not found")
        return NotebookResolution(
            manager=current, notebook_id=notebook_id, source="user", read_only=False
        )

    if requested_source == "admin":
        if not _notebook_exists(admin, notebook_id):
            raise HTTPException(status_code=404, detail="Notebook not found")
        return NotebookResolution(
            manager=admin, notebook_id=notebook_id, source="admin", read_only=True
        )

    if _notebook_exists(current, notebook_id):
        return NotebookResolution(
            manager=current, notebook_id=notebook_id, source="user", read_only=False
        )
    if _notebook_exists(admin, notebook_id):
        return NotebookResolution(
            manager=admin, notebook_id=notebook_id, source="admin", read_only=True
        )
    raise HTTPException(status_code=404, detail="Notebook not found")


def copy_admin_notebook_to_current_user(notebook_id: str) -> str:
    admin = admin_notebook_manager()
    current = current_notebook_manager()
    notebook = admin.get_notebook(notebook_id)
    if notebook is None:
        raise HTTPException(status_code=404, detail="Notebook not found")

    target = current._get_notebook_file(notebook_id)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(notebook, indent=2, ensure_ascii=False), encoding="utf-8")
        index = current._load_index()
        entries = index.setdefault("notebooks", [])
        if not any(str(item.get("id") or "") == notebook_id for item in entries):
            entries.append(
                {
                    "id": notebook_id,
                    "name": notebook.get("name", notebook_id),
                    "description": notebook.get("description", ""),
                    "created_at": notebook.get("created_at", 0),
                    "updated_at": notebook.get("updated_at", 0),
                    "record_count": len(notebook.get("records", []) or []),
                    "color": notebook.get("color", "#3B82F6"),
                    "icon": notebook.get("icon", "book"),
                }
            )
            current._save_index(index)
    return notebook_id


def resolve_notebook_for_write(
    notebook_ref: str,
    *,
    copy_public: bool = False,
) -> NotebookResolution:
    resolved = resolve_notebook_for_read(notebook_ref)
    if not resolved.read_only:
        return resolved
    if not copy_public:
        raise HTTPException(status_code=403, detail="Shared admin notebooks are read-only")
    notebook_id = copy_admin_notebook_to_current_user(resolved.notebook_id)
    return NotebookResolution(
        manager=current_notebook_manager(),
        notebook_id=notebook_id,
        source="user",
        read_only=False,
    )


def get_records_by_references_for_current_user(notebook_references: list[dict]) -> list[dict]:
    resolved_records: list[dict] = []
    for ref in notebook_references:
        notebook_id = str(ref.get("notebook_id", "") or "").strip()
        if not notebook_id:
            continue
        record_ids = [
            str(record_id).strip()
            for record_id in (ref.get("record_ids") or [])
            if str(record_id).strip()
        ]
        try:
            resolved = resolve_notebook_for_read(notebook_id)
        except HTTPException:
            continue
        notebook = resolved.manager.get_notebook(resolved.notebook_id)
        if not notebook:
            continue
        notebook_name = str(notebook.get("name", "") or resolved.notebook_id)
        public_notebook_id = (
            f"{ADMIN_NOTEBOOK_PREFIX}{resolved.notebook_id}"
            if resolved.source == "admin" and resolved.read_only
            else resolved.notebook_id
        )
        for record in resolved.manager.get_records(resolved.notebook_id, record_ids):
            resolved_records.append(
                {
                    **record,
                    "notebook_id": public_notebook_id,
                    "notebook_name": notebook_name,
                    "source": resolved.source,
                    "read_only": resolved.read_only,
                }
            )
    return resolved_records
