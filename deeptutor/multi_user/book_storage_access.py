"""Storage-only shared book visibility for chat context and low-level readers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException

from deeptutor.book.storage import BookStorage
from deeptutor.services.path_service import PathService

from .context import get_current_user
from .paths import get_admin_path_service, get_current_path_service

ADMIN_BOOK_PREFIX = "admin:book:"
USER_BOOK_PREFIX = "user:book:"
BookSource = Literal["admin", "user"]

_storages: dict[str, BookStorage] = {}


@dataclass(frozen=True)
class BookStorageResolution:
    storage: BookStorage
    book_id: str
    source: BookSource
    read_only: bool


def _storage_for(service: PathService) -> BookStorage:
    key = str(service.get_book_dir().resolve())
    storage = _storages.get(key)
    if storage is None:
        storage = BookStorage(path_service=service)
        _storages[key] = storage
    return storage


def admin_book_storage() -> BookStorage:
    return _storage_for(get_admin_path_service())


def current_book_storage() -> BookStorage:
    return _storage_for(get_current_path_service())


def strip_book_source(value: str) -> tuple[BookSource | None, str]:
    raw = str(value or "").strip()
    if raw.startswith(ADMIN_BOOK_PREFIX):
        return "admin", raw[len(ADMIN_BOOK_PREFIX) :]
    if raw.startswith(USER_BOOK_PREFIX):
        return "user", raw[len(USER_BOOK_PREFIX) :]
    return None, raw


def _book_exists(storage: BookStorage, book_id: str) -> bool:
    return storage.load_book(book_id) is not None


def resolve_book_storage_for_read(book_ref: str) -> BookStorageResolution:
    user = get_current_user()
    requested_source, book_id = strip_book_source(book_ref)
    if not book_id:
        raise HTTPException(status_code=404, detail="Book not found")

    if user.is_admin:
        storage = admin_book_storage()
        if not _book_exists(storage, book_id):
            raise HTTPException(status_code=404, detail="Book not found")
        return BookStorageResolution(
            storage=storage, book_id=book_id, source="admin", read_only=False
        )

    current = current_book_storage()
    admin = admin_book_storage()

    if requested_source == "user":
        if not _book_exists(current, book_id):
            raise HTTPException(status_code=404, detail="Book not found")
        return BookStorageResolution(
            storage=current, book_id=book_id, source="user", read_only=False
        )

    if requested_source == "admin":
        if not _book_exists(admin, book_id):
            raise HTTPException(status_code=404, detail="Book not found")
        return BookStorageResolution(storage=admin, book_id=book_id, source="admin", read_only=True)

    if _book_exists(current, book_id):
        return BookStorageResolution(
            storage=current, book_id=book_id, source="user", read_only=False
        )
    if _book_exists(admin, book_id):
        return BookStorageResolution(storage=admin, book_id=book_id, source="admin", read_only=True)
    raise HTTPException(status_code=404, detail="Book not found")
