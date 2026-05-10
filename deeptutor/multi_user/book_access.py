"""Shared book visibility for admin-authored public learning materials."""

from __future__ import annotations

from dataclasses import dataclass
import shutil
from typing import Any

from fastapi import HTTPException

from deeptutor.book.engine import BookEngine
from deeptutor.book.models import Progress
from deeptutor.book.storage import BookStorage

from .book_storage_access import (
    BookSource,
    admin_book_storage,
    current_book_storage,
    resolve_book_storage_for_read,
)
from .context import get_current_user
from .paths import get_admin_path_service, get_current_path_service

_engines: dict[str, BookEngine] = {}


@dataclass(frozen=True)
class BookResolution:
    engine: BookEngine
    book_id: str
    source: BookSource
    read_only: bool


def _engine_for(storage: BookStorage) -> BookEngine:
    key = str(storage.path_service.get_book_dir().resolve())
    engine = _engines.get(key)
    if engine is None:
        engine = BookEngine(storage=storage)
        _engines[key] = engine
    return engine


def admin_book_engine() -> BookEngine:
    return _engine_for(admin_book_storage())


def current_book_engine() -> BookEngine:
    return _engine_for(current_book_storage())


def _visible_book(
    book: Any,
    *,
    source: BookSource,
    read_only: bool,
) -> dict[str, Any]:
    payload = book.model_dump(mode="json")
    payload["source"] = source
    payload["read_only"] = read_only
    payload["assigned"] = source == "admin" and read_only
    payload["provenance_label"] = "Shared by admin" if read_only else "Created by you"
    return payload


def list_visible_books() -> list[dict[str, Any]]:
    user = get_current_user()
    if user.is_admin:
        return [
            _visible_book(book, source="admin", read_only=False)
            for book in admin_book_engine().list_books()
        ]

    current = current_book_engine()
    user_books = [
        _visible_book(book, source="user", read_only=False) for book in current.list_books()
    ]
    user_ids = {str(book.get("id") or "") for book in user_books}
    admin_books = []
    for book in admin_book_engine().list_books():
        if str(book.id) in user_ids:
            continue
        admin_books.append(_visible_book(book, source="admin", read_only=True))
    return sorted(
        [*user_books, *admin_books], key=lambda item: item.get("updated_at", 0), reverse=True
    )


def resolve_book_for_read(book_ref: str) -> BookResolution:
    resolved = resolve_book_storage_for_read(book_ref)
    return BookResolution(
        engine=_engine_for(resolved.storage),
        book_id=resolved.book_id,
        source=resolved.source,
        read_only=resolved.read_only,
    )


def copy_admin_book_to_current_user(book_id: str) -> str:
    admin_service = get_admin_path_service()
    current_service = get_current_path_service()
    source = admin_service.get_book_root(book_id)
    target = current_service.get_book_root(book_id)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Book not found")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        current_book_engine().storage.save_progress(Progress(book_id=book_id))
    return book_id


def resolve_book_for_write(
    book_ref: str,
    *,
    copy_public: bool = False,
) -> BookResolution:
    resolved = resolve_book_for_read(book_ref)
    if not resolved.read_only:
        return resolved
    if not copy_public:
        raise HTTPException(status_code=403, detail="Shared admin books are read-only")
    book_id = copy_admin_book_to_current_user(resolved.book_id)
    return BookResolution(
        engine=current_book_engine(),
        book_id=book_id,
        source="user",
        read_only=False,
    )


def decorate_book_detail(book: Any, *, source: BookSource, read_only: bool) -> dict[str, Any]:
    return _visible_book(book, source=source, read_only=read_only)
