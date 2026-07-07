"""Admin registration-invite endpoints."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from deeptutor.api.routers.auth import _enforce_user_seats, require_admin
from deeptutor.multi_user.audit import log_admin_action
from deeptutor.multi_user.invites import create_invite, delete_invite, list_invites
from deeptutor.services.auth import TokenPayload

router = APIRouter()


class InviteCreateRequest(BaseModel):
    """Payload for admin-created one-use registration invites."""

    email: str = ""

    @field_validator("email")
    @classmethod
    def email_valid(cls, value: str) -> str:
        value = value.strip().lower()
        if value and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
            raise ValueError("Enter a valid email address")
        return value


class InviteInfo(BaseModel):
    code: str
    email: str = ""
    created_by: str = ""
    created_at: str = ""
    used_by: str = ""
    used_at: str = ""


@router.get("/invites", response_model=list[InviteInfo])
async def get_invites(_: TokenPayload = Depends(require_admin)) -> list[InviteInfo]:
    """List registration invites. Requires admin role."""
    return [InviteInfo(**item) for item in list_invites()]


@router.post("/invites", response_model=InviteInfo, status_code=status.HTTP_201_CREATED)
async def admin_create_invite(
    body: InviteCreateRequest,
    current: TokenPayload = Depends(require_admin),
) -> InviteInfo:
    """Admin-only: create a one-use email/password registration invite."""
    _enforce_user_seats()
    invite = create_invite(email=body.email, created_by=current.username)
    log_admin_action(
        "invite_create",
        summary={"email": body.email or "", "used": False},
    )
    return InviteInfo(**invite)


@router.delete("/invites/{code}", status_code=status.HTTP_200_OK)
async def admin_delete_invite(
    code: str,
    _: TokenPayload = Depends(require_admin),
) -> dict:
    """Admin-only: revoke an unused or used invite code."""
    if not delete_invite(code):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    log_admin_action("invite_delete")
    return {"ok": True}
