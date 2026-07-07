"""Self-service profile and avatar endpoints."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from deeptutor.api.routers import auth as auth_router
from deeptutor.api.routers.users import UserInfo
from deeptutor.multi_user.audit import log_admin_action
from deeptutor.multi_user.data_governance import apply_user_delete_policy, export_user_data
from deeptutor.services.auth import (
    TokenPayload,
    delete_user,
    get_user_info,
    revoke_sessions,
    set_avatar,
    update_password,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_AVATAR_MAX_BYTES = 1 * 1024 * 1024
_AVATAR_MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_valid(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class AccountDeleteRequest(BaseModel):
    password: str
    data_action: Literal["keep", "archive", "delete"] = "keep"


class UpdateProfileRequest(BaseModel):
    """Payload for the PUT /profile endpoint."""

    avatar: str

    @field_validator("avatar")
    @classmethod
    def avatar_valid(cls, value: str) -> str:
        value = value.strip()
        if value and not auth_router._ICON_MARKER_RE.match(value):
            raise ValueError("Avatar must be empty or 'icon:<name>:<color>'")
        return value


def _sniff_image(data: bytes) -> str | None:
    """Detect a supported raster image format from its magic bytes."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _require_profile_identity(payload: TokenPayload | None) -> TokenPayload:
    """Shared guard for the self-service profile endpoints."""
    if not auth_router.AUTH_ENABLED or payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auth is disabled — profiles are not available.",
        )
    return payload


def _apply_user_data_policy(
    user_id: str,
    data_action: Literal["keep", "archive", "delete"],
) -> dict:
    if user_id and auth_router._USER_ID_RE.match(user_id):
        try:
            return apply_user_delete_policy(user_id, data_action)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"User data policy failed: {exc}",
            ) from exc
    return {"action": data_action, "workspace": "skipped", "grant": "skipped"}


@router.get("/profile", response_model=UserInfo)
async def get_profile(
    payload: TokenPayload | None = Depends(auth_router.require_auth),
) -> UserInfo:
    """Return the current user's own account info."""
    current = _require_profile_identity(payload)
    info = get_user_info(current.username)
    if info is None:
        return UserInfo(
            id=current.user_id,
            username=current.username,
            role=current.role,
            created_at="",
        )
    return UserInfo(**info)


@router.put("/profile")
async def update_profile(
    body: UpdateProfileRequest,
    payload: TokenPayload | None = Depends(auth_router.require_auth),
) -> dict:
    """Update the current user's own avatar marker."""
    current = _require_profile_identity(payload)
    if not set_avatar(current.username, body.avatar):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    from deeptutor.multi_user.identity import delete_avatar_file

    if current.user_id and auth_router._USER_ID_RE.match(current.user_id):
        delete_avatar_file(current.user_id)
    return {"ok": True, "avatar": body.avatar}


@router.put("/profile/password")
async def change_profile_password(
    body: PasswordChangeRequest,
    response: Response,
    payload: TokenPayload | None = Depends(auth_router.require_auth),
) -> dict:
    """Change the current user's password and invalidate existing JWTs."""
    current = _require_profile_identity(payload)
    if auth_router.POCKETBASE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password changes are not available in PocketBase mode.",
        )
    from deeptutor.multi_user.identity import get_user

    record = get_user(current.username)
    if not record or not verify_password(body.current_password, str(record.get("hash") or "")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    if not update_password(current.username, body.new_password):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    log_admin_action(
        "user_self_password_change",
        target_user_id=current.user_id,
        summary={"username": current.username},
    )
    response.delete_cookie(key=auth_router._COOKIE_NAME, samesite=auth_router._SAMESITE)
    return {"ok": True}


@router.post("/profile/revoke-sessions")
async def revoke_profile_sessions(
    response: Response,
    payload: TokenPayload | None = Depends(auth_router.require_auth),
) -> dict:
    """Invalidate all JWTs for the current local user, including this one."""
    current = _require_profile_identity(payload)
    if auth_router.POCKETBASE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session revocation is not available in PocketBase mode.",
        )
    if not revoke_sessions(current.username):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    log_admin_action(
        "user_self_sessions_revoked",
        target_user_id=current.user_id,
        summary={"username": current.username},
    )
    response.delete_cookie(key=auth_router._COOKIE_NAME, samesite=auth_router._SAMESITE)
    return {"ok": True}


@router.get("/profile/export")
async def export_profile_data(
    payload: TokenPayload | None = Depends(auth_router.require_auth),
) -> FileResponse:
    """Export the current regular user's own data as a zip archive."""
    current = _require_profile_identity(payload)
    if auth_router.POCKETBASE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Data export is not available in PocketBase mode.",
        )
    if current.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin data export is not available from self-service profile.",
        )

    info = get_user_info(current.username)
    user_id = str((info or {}).get("id") or current.user_id or "")
    if not user_id or not auth_router._USER_ID_RE.match(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    path = export_user_data(user_id, current.username)
    log_admin_action(
        "user_self_export",
        target_user_id=user_id,
        summary={"username": current.username},
    )
    return FileResponse(
        str(path),
        media_type="application/zip",
        filename=f"deeptutor-user-{current.username}-{user_id}.zip",
    )


@router.delete("/profile")
async def delete_profile(
    body: AccountDeleteRequest,
    response: Response,
    payload: TokenPayload | None = Depends(auth_router.require_auth),
) -> dict:
    """Delete the current regular user's account after password confirmation."""
    current = _require_profile_identity(payload)
    if auth_router.POCKETBASE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account deletion is not available in PocketBase mode.",
        )
    if current.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin account deletion must be handled by another admin.",
        )

    from deeptutor.multi_user.identity import get_user

    record = get_user(current.username)
    if not record or not verify_password(body.password, str(record.get("hash") or "")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    info = get_user_info(current.username)
    user_id = str((info or record).get("id") or current.user_id or "")
    data_policy = auth_router._apply_user_data_policy(user_id, body.data_action)
    if not delete_user(current.username):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    log_admin_action(
        "user_self_delete",
        target_user_id=user_id,
        summary={"username": current.username, "data_policy": data_policy},
    )
    response.delete_cookie(key=auth_router._COOKIE_NAME, samesite=auth_router._SAMESITE)
    return {"ok": True, "data_policy": data_policy}


@router.put("/profile/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    payload: TokenPayload | None = Depends(auth_router.require_auth),
) -> dict:
    """Upload an avatar image for the current user."""
    current = _require_profile_identity(payload)
    if auth_router.POCKETBASE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Avatar upload is not available in PocketBase mode.",
        )
    if not current.user_id or not auth_router._USER_ID_RE.match(current.user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot store an avatar for this account.",
        )
    info = get_user_info(current.username)
    if info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    data = await file.read(_AVATAR_MAX_BYTES + 1)
    if len(data) > _AVATAR_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Avatar image is too large (max 1 MB).",
        )
    ext = _sniff_image(data)
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Avatar must be a PNG, JPEG or WebP image.",
        )

    from deeptutor.multi_user.identity import save_avatar_file

    previous = str(info.get("avatar") or "")
    version = 1
    if previous.startswith("img:"):
        try:
            version = int(previous.split(":", 1)[1]) + 1
        except ValueError:
            version = 1
    marker = f"img:{version}"

    save_avatar_file(current.user_id, data, ext)
    if not set_avatar(current.username, marker):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    logger.info(f"User '{current.username}' uploaded a new avatar ({ext}, {len(data)} bytes)")
    return {"ok": True, "avatar": marker}


@router.delete("/profile/avatar")
async def remove_avatar(
    payload: TokenPayload | None = Depends(auth_router.require_auth),
) -> dict:
    """Remove the current user's uploaded avatar image and reset the marker."""
    current = _require_profile_identity(payload)
    from deeptutor.multi_user.identity import delete_avatar_file

    if current.user_id and auth_router._USER_ID_RE.match(current.user_id):
        delete_avatar_file(current.user_id)
    set_avatar(current.username, "")
    return {"ok": True, "avatar": ""}


@router.get("/avatar/{user_id}")
async def get_avatar_image(
    user_id: str,
    _: TokenPayload | None = Depends(auth_router.require_auth),
) -> FileResponse:
    """Serve a stored avatar image for authenticated users."""
    if not auth_router._USER_ID_RE.match(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found")

    from deeptutor.multi_user.identity import get_avatar_file

    target = get_avatar_file(user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found")

    media_type = _AVATAR_MEDIA_TYPES.get(target.suffix.lstrip("."), "application/octet-stream")
    headers = {
        "Cache-Control": "private, max-age=86400",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline",
    }
    return FileResponse(path=str(target), media_type=media_type, headers=headers)
