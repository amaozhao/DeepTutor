from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from deeptutor.auth.dependencies import SESSION_COOKIE, auth_cookie_secure, require_user_scope
from deeptutor.auth.migration import migrate_legacy_data_to_user
from deeptutor.auth.models import AuthUser
from deeptutor.auth.passwords import hash_password, verify_password
from deeptutor.auth.store import UserAlreadyExists, get_auth_store

router = APIRouter()


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=6, max_length=256)
    display_name: str = Field(default="", max_length=100)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("valid email is required")
        return normalized


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("valid email is required")
        return normalized


def _user_payload(user: AuthUser) -> dict[str, str | float | None]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "disabled_at": user.disabled_at,
    }


def _set_session_cookie(response: Response, token: str, expires_at: float) -> None:
    max_age = max(0, int(expires_at - time.time()))
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=auth_cookie_secure(),
        samesite="lax",
        max_age=max_age,
        path="/",
    )


@router.post("/register")
async def register(payload: RegisterRequest, response: Response, request: Request):
    store = get_auth_store()
    is_first_user = store.count_users() == 0
    try:
        user = store.create_user(
            email=payload.email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
        )
    except UserAlreadyExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc
    if is_first_user:
        migrate_legacy_data_to_user(user.id)

    session = store.create_session(
        user.id,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )
    _set_session_cookie(response, session.token, session.expires_at)
    return {"user": _user_payload(user)}


@router.post("/login")
async def login(payload: LoginRequest, response: Response, request: Request):
    store = get_auth_store()
    user = store.get_user_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if user.disabled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is disabled",
        )

    session = store.create_session(
        user.id,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )
    _set_session_cookie(response, session.token, session.expires_at)
    return {"user": _user_payload(user)}


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        get_auth_store().revoke_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"logged_out": True}


@router.get("/me")
async def me(user: AuthUser = Depends(require_user_scope)):
    return {"user": _user_payload(user)}
