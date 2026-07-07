"""Admin-user helpers for auth routes."""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, field_validator

from deeptutor.api.routers import auth as auth_router
from deeptutor.multi_user.audit import log_admin_action
from deeptutor.services.auth import (
    TokenPayload,
    add_user,
    delete_user,
    get_user_info,
    list_users,
    register_pb,
    revoke_sessions,
    set_disabled,
    set_role,
    update_password,
)

logger = logging.getLogger(__name__)
router = APIRouter()

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


class SetRoleRequest(BaseModel):
    """Payload for the PUT /users/{username}/role endpoint."""

    role: str

    @field_validator("role")
    @classmethod
    def role_valid(cls, value: str) -> str:
        if value not in ("admin", "user"):
            raise ValueError("Role must be 'admin' or 'user'")
        return value


class PasswordResetRequest(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def password_valid(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class DisabledRequest(BaseModel):
    disabled: bool
    reason: str = ""

    @field_validator("reason")
    @classmethod
    def reason_valid(cls, value: str) -> str:
        return value.strip()[:500]


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


@router.get("/users", response_model=list[UserInfo])
async def get_users(_: TokenPayload = Depends(auth_router.require_admin)) -> list[UserInfo]:
    """List all registered users. Requires admin role."""
    return [UserInfo(**u) for u in list_users()]


@router.get("/users/export.csv")
async def export_users_csv(_: TokenPayload = Depends(auth_router.require_admin)) -> Response:
    """Export the user directory as CSV. Password hashes are never included."""
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["email", "role", "disabled", "disabled_reason", "created_at", "user_id"],
    )
    writer.writeheader()
    for user in list_users():
        writer.writerow(
            {
                "email": user.get("username", ""),
                "role": user.get("role", "user"),
                "disabled": "true" if user.get("disabled") else "false",
                "disabled_reason": user.get("disabled_reason", ""),
                "created_at": user.get("created_at", ""),
                "user_id": user.get("id", ""),
            }
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="deeptutor-users.csv"'},
    )


@router.post("/users/import.csv", response_model=UserImportResult)
async def import_users_csv(
    file: UploadFile = File(...),
    current: TokenPayload = Depends(auth_router.require_admin),
) -> UserImportResult:
    """Admin-only bulk import for email/password user accounts."""
    if not auth_router.AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auth is disabled — user import is not available.",
        )
    if auth_router.POCKETBASE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User import is not available in PocketBase mode.",
        )

    data = await file.read()
    if len(data) > CSV_IMPORT_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="CSV is too large."
        )
    rows = parse_user_import_csv(data)
    existing = {str(user.get("username") or "").lower() for user in list_users()}
    for row in rows:
        email = str(row["email"])
        if email in existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email already exists: {email}",
            )

    auth_router._enforce_user_seats(additional=len(rows))
    usernames: list[str] = []
    for row in rows:
        email = str(row["email"])
        created = add_user(email, str(row["password"]), role="user")
        if created is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email already exists: {email}",
            )
        if row["disabled"]:
            set_disabled(email, True, reason=str(row["disabled_reason"]))
        usernames.append(email)

    log_admin_action(
        "users_import",
        summary={
            "created": len(usernames),
            "usernames": usernames[:20],
            "truncated": len(usernames) > 20,
            "actor": current.username if current else "local",
        },
    )
    return UserImportResult(created=len(usernames), usernames=usernames)


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    body: auth_router.RegisterRequest,
    current: TokenPayload = Depends(auth_router.require_admin),
) -> dict:
    """Admin-only: create a new user account."""
    if not auth_router.AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auth is disabled — user creation is not available.",
        )

    if auth_router.POCKETBASE_ENABLED:
        auth_router._enforce_user_seats()
        result = register_pb(username=body.username, email=body.username, password=body.password)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Failed to create user — username may already be taken.",
            )
        logger.info(
            f"Admin '{current.username if current else 'local'}' created PocketBase user "
            f"'{body.username}'"
        )
        log_admin_action(
            "user_create",
            target_user_id=str(result.get("id") or ""),
            summary={"username": body.username, "role": "user", "provider": "pocketbase"},
        )
        return {
            "ok": True,
            "user_id": result.get("id", ""),
            "username": body.username,
            "role": "user",
            "is_admin": False,
        }

    existing = {u["username"] for u in list_users()}
    if body.username in existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    auth_router._enforce_user_seats()
    created = add_user(body.username, body.password)
    if created is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )
    user_id = ""
    role = "user"
    for item in list_users():
        if item.get("username") == body.username:
            user_id = str(item.get("id") or "")
            role = str(item.get("role") or "user")
            break
    logger.info(
        f"Admin '{current.username if current else 'local'}' created user '{body.username}' "
        f"(role={role!r})"
    )
    log_admin_action(
        "user_create",
        target_user_id=user_id,
        summary={"username": body.username, "role": role, "provider": "local"},
    )
    return {
        "ok": True,
        "user_id": user_id,
        "username": body.username,
        "role": role,
        "is_admin": role == "admin",
    }


@router.put("/users/{username}/password", status_code=status.HTTP_200_OK)
async def admin_reset_user_password(
    username: str,
    body: PasswordResetRequest,
    current: TokenPayload = Depends(auth_router.require_admin),
) -> dict:
    """Admin-only: reset another user's password and invalidate their JWTs."""
    if auth_router.POCKETBASE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset is not available in PocketBase mode.",
        )
    if current and username == current.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use profile settings to change your own password",
        )
    info = get_user_info(username)
    if not update_password(username, body.password):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    logger.info(
        "Admin '%s' reset password for '%s'", current.username if current else "local", username
    )
    log_admin_action(
        "user_password_reset",
        target_user_id=str((info or {}).get("id") or ""),
        summary={"username": username},
    )
    return {"ok": True}


@router.put("/users/{username}/disabled", status_code=status.HTTP_200_OK)
async def update_user_disabled(
    username: str,
    body: DisabledRequest,
    current: TokenPayload = Depends(auth_router.require_admin),
) -> dict:
    """Admin-only: enable or disable a user. Admins cannot disable themselves."""
    if current and username == current.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot disable your own account",
        )
    info = get_user_info(username)
    if not set_disabled(username, body.disabled, reason=body.reason):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    logger.info(
        "Admin '%s' set '%s' disabled=%s",
        current.username if current else "local",
        username,
        body.disabled,
    )
    log_admin_action(
        "user_disabled_set",
        target_user_id=str((info or {}).get("id") or ""),
        summary={
            "username": username,
            "disabled": body.disabled,
            "reason": body.reason if body.disabled else "",
        },
    )
    return {
        "ok": True,
        "username": username,
        "disabled": body.disabled,
        "disabled_reason": body.reason if body.disabled else "",
    }


@router.post("/users/{username}/revoke-sessions", status_code=status.HTTP_200_OK)
async def admin_revoke_user_sessions(
    username: str,
    current: TokenPayload = Depends(auth_router.require_admin),
) -> dict:
    """Admin-only: invalidate another user's existing JWTs."""
    if current and username == current.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot revoke your own current session here",
        )
    info = get_user_info(username)
    if not revoke_sessions(username):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    log_admin_action(
        "user_sessions_revoked",
        target_user_id=str((info or {}).get("id") or ""),
        summary={"username": username},
    )
    return {"ok": True, "username": username}


@router.delete("/users/{username}", status_code=status.HTTP_200_OK)
async def remove_user(
    username: str,
    data_action: Literal["keep", "archive", "delete"] = "keep",
    current: TokenPayload = Depends(auth_router.require_admin),
) -> dict:
    """Delete a user. Admins cannot delete their own account."""
    if current and username == current.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )

    info = get_user_info(username)
    if info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user_id = str(info.get("id") or "") if info else ""
    data_policy = auth_router._apply_user_data_policy(user_id, data_action)
    if not delete_user(username):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    logger.info(f"Admin '{current.username if current else 'local'}' deleted user '{username}'")
    log_admin_action(
        "user_delete",
        target_user_id=user_id,
        summary={"username": username, "data_policy": data_policy},
    )
    return {"ok": True, "data_policy": data_policy}


@router.put("/users/{username}/role", status_code=status.HTTP_200_OK)
async def update_user_role(
    username: str,
    body: SetRoleRequest,
    current: TokenPayload = Depends(auth_router.require_admin),
) -> dict:
    """Change a user's role. Admins cannot change their own role."""
    if current and username == current.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role",
        )

    info = get_user_info(username)
    updated = set_role(username, body.role)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    logger.info(
        f"Admin '{current.username if current else 'local'}' set '{username}' role to {body.role!r}"
    )
    log_admin_action(
        "user_role_set",
        target_user_id=str((info or {}).get("id") or ""),
        summary={"username": username, "role": body.role},
    )
    return {"ok": True, "username": username, "role": body.role}
