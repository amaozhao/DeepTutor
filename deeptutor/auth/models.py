from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    password_hash: str
    display_name: str
    created_at: float
    updated_at: float
    disabled_at: float | None = None


@dataclass(frozen=True)
class AuthSession:
    id: str
    user_id: str
    token: str
    token_hash: str
    created_at: float
    expires_at: float
    revoked_at: float | None = None
    user_agent: str = ""
    ip_address: str = ""
