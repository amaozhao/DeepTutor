"""Admin-user helpers for auth routes."""

from __future__ import annotations

import csv
import io
import re

from fastapi import HTTPException, status
from pydantic import BaseModel

CSV_IMPORT_MAX_BYTES = 1_000_000


class UserInfo(BaseModel):
    """Single user record returned by the GET /users and /profile endpoints."""

    id: str = ""
    username: str
    role: str
    created_at: str
    disabled: bool = False
    disabled_reason: str = ""
    avatar: str = ""


class UserImportResult(BaseModel):
    ok: bool = True
    created: int
    usernames: list[str]


def parse_user_import_csv(data: bytes) -> list[dict[str, str | bool]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must be UTF-8 encoded.",
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    headers = {str(name or "").strip().lower() for name in (reader.fieldnames or [])}
    if not headers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV is empty.")
    if "password" not in headers or "email" not in headers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must include email,password columns.",
        )

    rows: list[dict[str, str | bool]] = []
    seen: set[str] = set()
    for row_index, raw in enumerate(reader, start=2):
        row = {
            str(key or "").strip().lower(): str(value or "").strip() for key, value in raw.items()
        }
        if not any(row.values()):
            continue
        email = row.get("email", "").lower()
        password = row.get("password") or ""
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Row {row_index}: Value error, Enter a valid email address",
            )
        if len(password) < 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Row {row_index}: Value error, Password must be at least 8 characters",
            )
        if email in seen:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Row {row_index}: duplicate email in CSV.",
            )
        seen.add(email)
        disabled = _csv_bool(row.get("disabled", ""))
        reason = row.get("disabled_reason", "").strip()[:500]
        rows.append(
            {
                "email": email,
                "password": password,
                "disabled": disabled,
                "disabled_reason": reason if disabled else "",
            }
        )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="CSV contains no users."
        )
    return rows


def _csv_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}
