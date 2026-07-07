"""Auth router — login, logout, status, registration, profile, and user-management endpoints."""

import base64
from contextvars import Token as _CtxToken
import csv
import hashlib
import hmac
import io
import json
import logging
import re
import secrets
import time
from typing import Literal

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    File,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError, field_validator

from deeptutor.services.config import load_auth_settings

# SameSite=None lets the cookie work when the browser accesses the frontend via
# 127.0.0.1 and the backend via localhost (different origins on the same machine).
# Browsers require Secure=True for SameSite=None, but that needs HTTPS — so in
# local dev we fall back to SameSite=Lax and tell users to use localhost:// URLs.
_SECURE = bool(load_auth_settings()["cookie_secure"])
_SAMESITE = "none" if _SECURE else "lax"

from deeptutor.api.security import client_ip, require_rate_limit, websocket_ip
from deeptutor.multi_user.audit import log_admin_action
from deeptutor.multi_user.context import set_current_user, user_from_token_payload
from deeptutor.multi_user.data_governance import apply_user_delete_policy, export_user_data
from deeptutor.multi_user.invites import (
    consume_invite,
    create_invite,
    delete_invite,
    list_invites,
    unconsume_invite,
)
from deeptutor.multi_user.paths import local_admin_user
from deeptutor.services.auth import (
    AUTH_ENABLED,
    POCKETBASE_ENABLED,
    TOKEN_EXPIRE_HOURS,
    TokenPayload,
    add_user,
    authenticate,
    authenticate_pb,
    create_token,
    decode_token,
    delete_user,
    get_user_info,
    is_first_user,
    list_users,
    register_pb,
    revoke_sessions,
    set_avatar,
    set_disabled,
    set_role,
    update_password,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_COOKIE_NAME = "dt_token"
_COOKIE_MAX_AGE = TOKEN_EXPIRE_HOURS * 3600
_CSV_IMPORT_MAX_BYTES = 1_000_000
_REGISTER_CHALLENGE_TTL_SECONDS = 10 * 60
_REGISTER_CHALLENGE_DIFFICULTY = 3


def _cookie_attrs() -> dict:
    """Attribute set shared by ``login``'s ``set_cookie`` and ``logout``'s
    ``delete_cookie``.

    The deletion ``Set-Cookie`` must carry the same attributes as the one
    that created the cookie — ``delete_cookie`` defaults ``secure=False``,
    which browsers reject when paired with ``SameSite=None``, silently
    keeping the old cookie. See #623. Reads the module globals at call time
    so tests can monkeypatch ``_SECURE``/``_SAMESITE``.
    """
    return {
        "key": _COOKIE_NAME,
        "httponly": True,
        "samesite": _SAMESITE,
        "secure": _SECURE,
    }


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Payload for the POST /login endpoint."""

    username: str
    password: str


class RegisterRequest(BaseModel):
    """Payload for email/password account creation endpoints."""

    username: str
    password: str
    terms_accepted: bool = False
    captcha_token: str | None = None
    invite_code: str | None = None

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Email cannot be empty")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class InviteCreateRequest(BaseModel):
    """Payload for admin-created one-use registration invites."""

    email: str = ""

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if v and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Enter a valid email address")
        return v


class InviteInfo(BaseModel):
    code: str
    email: str = ""
    created_by: str = ""
    created_at: str = ""
    used_by: str = ""
    used_at: str = ""


class RegisterChallenge(BaseModel):
    token: str
    difficulty: int
    expires_in: int


class SetRoleRequest(BaseModel):
    """Payload for the PUT /users/{username}/role endpoint."""

    role: str

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str) -> str:
        if v not in ("admin", "user"):
            raise ValueError("Role must be 'admin' or 'user'")
        return v


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_valid(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class PasswordResetRequest(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class DisabledRequest(BaseModel):
    disabled: bool
    reason: str = ""

    @field_validator("reason")
    @classmethod
    def reason_valid(cls, v: str) -> str:
        return v.strip()[:500]


class AccountDeleteRequest(BaseModel):
    password: str
    data_action: Literal["keep", "archive", "delete"] = "keep"


class AuthStatusResponse(BaseModel):
    """Response body for the GET /status endpoint."""

    enabled: bool
    authenticated: bool
    user_id: str | None = None
    username: str | None = None
    role: str | None = None
    is_admin: bool = False
    avatar: str = ""


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


# Markers settable through PUT /profile. Image markers ("img:<version>") are
# managed exclusively by the upload endpoint so users cannot point their
# avatar at a file that was never validated.
_ICON_MARKER_RE = re.compile(r"^icon:[a-z0-9-]{1,32}:[a-z0-9-]{1,32}$")

# User ids are generated as "u_<uuid hex>" (plus the "local-admin" /
# "env-admin" sentinels); reject anything else before it reaches the
# filesystem layer.
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class UpdateProfileRequest(BaseModel):
    """Payload for the PUT /profile endpoint."""

    avatar: str

    @field_validator("avatar")
    @classmethod
    def avatar_valid(cls, v: str) -> str:
        v = v.strip()
        if v and not _ICON_MARKER_RE.match(v):
            raise ValueError("Avatar must be empty or 'icon:<name>:<color>'")
        return v


# ---------------------------------------------------------------------------
# Shared helper — extract token from cookie or Bearer header
# ---------------------------------------------------------------------------


def _bearer_token_from_header(authorization: str | None) -> str | None:
    """Parse ``Authorization: Bearer <token>`` without using ``HTTPBearer``.

    ``HTTPBearer`` is a class-based dependency whose ``__call__`` is annotated
    ``request: Request``. FastAPI doesn't inject a Request into WebSocket
    dependency resolution, which makes ``HTTPBearer`` raise ``TypeError`` the
    moment a router with this dep mounts a WS endpoint. Doing the parse by
    hand keeps ``require_auth`` HTTP/WS-symmetric.
    """
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1].strip()
        return token or None
    return None


def _extract_token(authorization: str | None, dt_token: str | None) -> str | None:
    return _bearer_token_from_header(authorization) or dt_token


def _rate_key(prefix: str, request: Request, identity: str) -> str:
    return f"{prefix}:{client_ip(request)}:{identity.strip().lower()}"


def _is_email(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value.strip()))


def _captcha_secret() -> str:
    from deeptutor.multi_user.identity import load_or_create_auth_secret

    return load_or_create_auth_secret()


def _challenge_signature(payload: str) -> str:
    return hmac.new(
        _captcha_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _encode_challenge(payload: dict[str, object]) -> str:
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"{body}.{_challenge_signature(body)}"


def _decode_challenge(token: str) -> dict[str, object] | None:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _challenge_signature(body)):
        return None
    try:
        padded = body + ("=" * (-len(body) % 4))
        loaded = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def _new_registration_challenge(email: str) -> str:
    expires_at = int(time.time()) + _REGISTER_CHALLENGE_TTL_SECONDS
    return _encode_challenge(
        {
            "email": email.strip().lower(),
            "nonce": secrets.token_urlsafe(16),
            "exp": expires_at,
            "difficulty": _REGISTER_CHALLENGE_DIFFICULTY,
        }
    )


def _require_registration_challenge(email: str, captcha_token: str | None) -> None:
    """Validate a tiny proof-of-work challenge for public registrations.

    ponytail: avoids adding a CAPTCHA provider; replace when real bot pressure
    justifies third-party risk scoring.
    """
    raw = (captcha_token or "").strip()
    try:
        token, nonce = raw.rsplit(":", 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration challenge is required.",
        ) from exc
    challenge = _decode_challenge(token)
    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration challenge is invalid.",
        )
    if str(challenge.get("email") or "") != email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration challenge is for a different email.",
        )
    try:
        expires_at = int(challenge.get("exp") or 0)
        difficulty = max(1, int(challenge.get("difficulty") or _REGISTER_CHALLENGE_DIFFICULTY))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration challenge is invalid.",
        ) from exc
    if expires_at < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration challenge expired.",
        )
    digest = hashlib.sha256(f"{token}:{nonce}".encode("utf-8")).hexdigest()
    if not digest.startswith("0" * difficulty):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration challenge proof is invalid.",
        )


def _csv_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_user_import_csv(data: bytes) -> list[dict[str, str | bool]]:
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
        try:
            RegisterRequest(username=email, password=password)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Row {row_index}: {exc.errors()[0]['msg']}",
            ) from exc
        if email in seen:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Row {row_index}: duplicate email in CSV.",
            )
        seen.add(email)
        disabled = _csv_bool(row.get("disabled", ""))
        reason = DisabledRequest(
            disabled=disabled,
            reason=row.get("disabled_reason", ""),
        ).reason
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


def _public_registration_enabled() -> bool:
    return bool(load_auth_settings().get("public_registration_enabled", False))


def _registration_review_required() -> bool:
    return bool(load_auth_settings().get("registration_review_required", False))


def _terms_required() -> bool:
    return bool(load_auth_settings().get("require_terms_acceptance", True))


def _agreement_versions() -> dict[str, str]:
    auth = load_auth_settings()
    return {
        "terms_version": str(auth.get("terms_version") or ""),
        "privacy_version": str(auth.get("privacy_version") or ""),
    }


# ponytail: file-backed seat checks are best-effort; external user DB for multi-replica exactness.
def _enforce_user_seats(additional: int = 1) -> None:
    try:
        max_users = max(0, int(load_auth_settings().get("max_users") or 0))
    except (TypeError, ValueError):
        max_users = 0
    if max_users > 0 and len(list_users()) + additional > max_users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User seat limit reached ({max_users}).",
        )


# ---------------------------------------------------------------------------
# Dependencies — reusable auth guards for other routers
# ---------------------------------------------------------------------------


def _install_current_user(payload: TokenPayload | None) -> _CtxToken:
    """Install the request-local current-user ContextVar from an auth result.

    Single point of truth for ``payload → CurrentUser`` so HTTP and WebSocket
    entry points produce identical user objects. ``payload is None`` means
    "no JWT was required" (AUTH_ENABLED=false) and resolves to the local
    admin user; a non-None payload resolves through ``user_from_token_payload``.

    Returns the ContextVar reset token. HTTP callers ignore it (the request
    ends with the task, so the var is GC'd with the task context). WebSocket
    callers keep it and call ``reset_current_user`` in their ``finally`` block,
    because a WS connection outlives the dependency-resolution task.

    ⚠ Invariant: every authenticated entry point MUST call this before the
    handler runs. Skipping it leaves ``get_current_path_service()`` falling
    back to the admin workspace — the silent-routing root cause of #481.
    """
    user = local_admin_user() if payload is None else user_from_token_payload(payload)
    return set_current_user(user)


async def require_auth(
    authorization: str | None = Header(default=None, alias="Authorization"),
    dt_token: str | None = Cookie(default=None),
) -> TokenPayload | None:
    """
    FastAPI dependency that enforces authentication when AUTH_ENABLED=true.

    Accepts the JWT from either:
      - Authorization: Bearer <token> header
      - dt_token cookie

    ``Header`` and ``Cookie`` are kept here in place of ``HTTPBearer`` so the
    function stays usable from WebSocket call sites that don't go through
    FastAPI's standard HTTP request lifecycle.

    Returns the authenticated TokenPayload, or None if auth is disabled.
    Raises HTTP 401 if auth is enabled but the token is missing or invalid.

    Declared ``async def`` so the ``set_current_user`` call runs in the same
    asyncio context as the endpoint. A sync dependency is dispatched via
    ``anyio.to_thread.run_sync``, which executes the function in a worker
    thread under a *copy* of the request context; any ``ContextVar.set``
    inside that thread is discarded when the thread returns, leaving the
    endpoint to read the unset default. That regression was the root cause
    of #481.
    """
    if not AUTH_ENABLED:
        _install_current_user(None)
        return None

    token = _extract_token(authorization, dt_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _install_current_user(payload)
    return payload


class _WsAuthFailed:
    """Sentinel: ws_require_auth failed and closed the WebSocket."""


ws_auth_failed: _WsAuthFailed = _WsAuthFailed()


async def ws_require_auth(ws: WebSocket) -> _CtxToken | _WsAuthFailed:
    """Authenticate a WebSocket connection and set the user ContextVar.

    Must be called **before** ``ws.accept()`` so the server can reject
    unauthenticated upgrades cleanly.

    Returns a ContextVar reset token on success, or ``ws_auth_failed``
    on failure (the WebSocket is already closed — the caller should
    ``return`` immediately).

    Usage::

        user_token = await ws_require_auth(ws)
        if user_token is ws_auth_failed:
            return
        await ws.accept()
        try:
            ...
        finally:
            reset_current_user(user_token)
    """
    if not AUTH_ENABLED:
        return _install_current_user(None)

    token = ws.query_params.get("token") or ws.cookies.get(_COOKIE_NAME)
    payload = decode_token(token) if token else None
    if not payload:
        await ws.close(code=4001)
        return ws_auth_failed

    try:
        require_rate_limit(
            f"ws:{websocket_ip(ws)}:{payload.username.lower()}",
            limit=60,
            window_seconds=60,
        )
    except HTTPException:
        await ws.close(code=4008)
        return ws_auth_failed

    return _install_current_user(payload)


async def require_admin(
    payload: TokenPayload | None = Depends(require_auth),
) -> TokenPayload:
    """
    FastAPI dependency that requires the caller to be an admin.

    Raises HTTP 403 if the authenticated user is not an admin.
    When AUTH_ENABLED=false, all requests are treated as admin.

    ``async def`` mirrors ``require_auth`` so the dependency chain stays on
    the event loop and the user ContextVar set by ``require_auth`` is visible
    to the endpoint.
    """
    if not AUTH_ENABLED:
        return _local_admin_token_payload()

    if payload is None or payload.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return payload


def _local_admin_token_payload() -> TokenPayload:
    """Synthetic admin payload used when AUTH_ENABLED=false.

    Mirrors the local admin identity (LOCAL_ADMIN_USERNAME / LOCAL_ADMIN_ID)
    so audit logs and self-reference checks behave the same as in multi-user
    mode. Values are kept aligned with ``local_admin_user()`` in
    ``deeptutor/multi_user/paths.py``.
    """
    from deeptutor.multi_user.models import LOCAL_ADMIN_ID, LOCAL_ADMIN_USERNAME

    return TokenPayload(
        username=LOCAL_ADMIN_USERNAME,
        role="admin",
        user_id=LOCAL_ADMIN_ID,
    )


# ---------------------------------------------------------------------------
# Public endpoints (no auth required)
# ---------------------------------------------------------------------------


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(
    authorization: str | None = Header(default=None, alias="Authorization"),
    dt_token: str | None = Cookie(default=None),
) -> AuthStatusResponse:
    """Return whether auth is enabled and whether the current request is authenticated."""
    if not AUTH_ENABLED:
        return AuthStatusResponse(
            enabled=False,
            authenticated=True,
            user_id="local-admin",
            username="local",
            role="admin",
            is_admin=True,
        )

    token = _extract_token(authorization, dt_token)
    payload = decode_token(token) if token else None
    avatar = ""
    if payload is not None:
        info = get_user_info(payload.username)
        if info:
            avatar = str(info.get("avatar") or "")
    return AuthStatusResponse(
        enabled=True,
        authenticated=payload is not None,
        user_id=payload.user_id if payload else None,
        username=payload.username if payload else None,
        role=payload.role if payload else None,
        is_admin=payload.role == "admin" if payload else False,
        avatar=avatar,
    )


@router.post("/login")
async def login(body: LoginRequest, response: Response, request: Request) -> dict:
    """Validate credentials and set a JWT cookie."""
    if not AUTH_ENABLED:
        return {"ok": True, "message": "Auth is disabled — no login required."}

    require_rate_limit(_rate_key("login", request, body.username), limit=10, window_seconds=300)

    if POCKETBASE_ENABLED:
        # PocketBase mode: email = username field for backwards-compat with the
        # existing LoginRequest schema; users can pass their email as "username".
        pb_result = authenticate_pb(body.username, body.password)
        if not pb_result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )
        payload, pb_token = pb_result
        response.set_cookie(value=pb_token, max_age=_COOKIE_MAX_AGE, **_cookie_attrs())
        logger.info(f"User '{payload.username}' logged in via PocketBase (role={payload.role!r})")
        return {
            "ok": True,
            "user_id": payload.user_id,
            "username": payload.username,
            "role": payload.role,
            "is_admin": payload.role == "admin",
        }

    # Standard JWT + bcrypt mode
    result = authenticate(body.username, body.password)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = create_token(result.username, result.role, result.user_id)
    response.set_cookie(value=token, max_age=_COOKIE_MAX_AGE, **_cookie_attrs())

    logger.info(f"User '{result.username}' logged in (role={result.role!r})")
    return {
        "ok": True,
        "user_id": result.user_id,
        "username": result.username,
        "role": result.role,
        "is_admin": result.role == "admin",
    }


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear the JWT cookie.

    Deletion attributes mirror ``login`` structurally via ``_cookie_attrs()``
    (see the rationale there and #623).
    """
    response.delete_cookie(**_cookie_attrs())
    return {"ok": True}


@router.get("/register/challenge", response_model=RegisterChallenge)
async def registration_challenge(email: str, request: Request) -> RegisterChallenge:
    """Issue a lightweight registration challenge for public signups."""
    normalized = email.strip().lower()
    if not _is_email(normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Enter a valid email address",
        )
    require_rate_limit(
        _rate_key("register-challenge", request, normalized),
        limit=20,
        window_seconds=300,
    )
    return RegisterChallenge(
        token=_new_registration_challenge(normalized),
        difficulty=_REGISTER_CHALLENGE_DIFFICULTY,
        expires_in=_REGISTER_CHALLENGE_TTL_SECONDS,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request) -> dict:
    """
    Bootstrap-only registration.

    Public endpoint that creates the *first* admin account when the user store
    is empty. Once an admin exists, this endpoint is closed; further accounts
    must be created by an admin via ``POST /api/v1/auth/users``.

    Only available when AUTH_ENABLED=true.
    """
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auth is disabled — registration is not available.",
        )

    require_rate_limit(_rate_key("register", request, body.username), limit=5, window_seconds=300)

    if POCKETBASE_ENABLED:
        # PocketBase deployments are documented as single-user. Keep registration
        # closed and require admins to provision users in the PocketBase admin UI.
        if not is_first_user():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Self-registration is closed. Ask an administrator to create your account.",
            )
        _require_registration_challenge(body.username, body.captcha_token)
        _enforce_user_seats()
        result = register_pb(username=body.username, email=body.username, password=body.password)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Registration failed — username or email may already be taken.",
            )
        logger.info(f"First user registered via PocketBase: '{body.username}'")
        return {
            "ok": True,
            "user_id": result.get("id", ""),
            "username": body.username,
            "role": "user",
            "is_first_user": True,
            "is_admin": False,
        }

    # Standard mode — first account bootstraps admin; later public signups are
    # email-only and opt-in through auth.public_registration_enabled.
    if not is_first_user():
        public_registration = _public_registration_enabled()
        invite_code = (body.invite_code or "").strip()
        if not public_registration and not invite_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Self-registration is closed. Ask an administrator to create your account.",
            )
        if not _is_email(body.username):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Public registration requires an email address.",
            )
        if _terms_required() and not body.terms_accepted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You must accept the terms to create an account.",
            )

        existing = {u["username"].lower() for u in list_users()}
        if body.username.lower() in existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            )
        if public_registration and not invite_code:
            _require_registration_challenge(body.username, body.captcha_token)
        _enforce_user_seats()
        if invite_code and not consume_invite(invite_code, email=body.username):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or already used invite code.",
            )
        review_required = (
            public_registration and not invite_code and _registration_review_required()
        )
        try:
            created = add_user(body.username, body.password, role="user")
        except Exception:
            if invite_code:
                unconsume_invite(invite_code, email=body.username)
            raise
        if created is None:
            if invite_code:
                unconsume_invite(invite_code, email=body.username)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            )
        if review_required:
            set_disabled(body.username, True, reason="pending registration review")
        if body.terms_accepted:
            from deeptutor.multi_user.identity import record_terms_acceptance

            record_terms_acceptance(body.username, **_agreement_versions())
        user = next((u for u in list_users() if u.get("username") == body.username), {})
        logger.info("Public user registered: '%s'", body.username)
        return {
            "ok": True,
            "user_id": str(user.get("id") or ""),
            "username": body.username,
            "role": "user",
            "is_first_user": False,
            "is_admin": False,
            "requires_review": review_required,
        }

    existing = {u["username"] for u in list_users()}
    if body.username in existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    _enforce_user_seats()
    _require_registration_challenge(body.username, body.captcha_token)
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
    logger.info(f"First user (admin) registered: '{body.username}'")
    return {
        "ok": True,
        "user_id": user_id,
        "username": body.username,
        "role": role,
        "is_first_user": True,
        "is_admin": role == "admin",
    }


@router.get("/is_first_user")
async def check_is_first_user() -> dict:
    """Return whether the user store is empty (used by the register UI)."""
    return {"is_first_user": is_first_user() if AUTH_ENABLED else False}


# ---------------------------------------------------------------------------
# Profile endpoints (any authenticated user, self-service)
# ---------------------------------------------------------------------------

_AVATAR_MAX_BYTES = 1 * 1024 * 1024
_AVATAR_MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


def _sniff_image(data: bytes) -> str | None:
    """Detect a supported raster image format from its magic bytes.

    The uploaded filename and Content-Type are attacker-controlled, so the
    stored extension (and the media type served back) is derived from the
    bytes alone. SVG is deliberately unsupported — serving user-supplied SVG
    is a stored-XSS vector.
    """
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _require_profile_identity(payload: TokenPayload | None) -> TokenPayload:
    """Shared guard for the self-service profile endpoints."""
    if not AUTH_ENABLED or payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auth is disabled — profiles are not available.",
        )
    return payload


def _apply_user_data_policy(
    user_id: str,
    data_action: Literal["keep", "archive", "delete"],
) -> dict:
    if user_id and _USER_ID_RE.match(user_id):
        try:
            data_policy = apply_user_delete_policy(user_id, data_action)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"User data policy failed: {exc}",
            ) from exc
        return data_policy
    return {"action": data_action, "workspace": "skipped", "grant": "skipped"}


@router.get("/profile", response_model=UserInfo)
async def get_profile(
    payload: TokenPayload | None = Depends(require_auth),
) -> UserInfo:
    """Return the current user's own account info."""
    current = _require_profile_identity(payload)
    info = get_user_info(current.username)
    if info is None:
        # PocketBase-backed identities have no local record; fall back to the
        # token claims so the profile page still renders.
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
    payload: TokenPayload | None = Depends(require_auth),
) -> dict:
    """Update the current user's own avatar marker (icon choice or reset).

    Only the validated ``icon:<name>:<color>`` form (or empty string) is
    accepted here; ``img:`` markers are owned by the upload endpoint.
    """
    current = _require_profile_identity(payload)
    if not set_avatar(current.username, body.avatar):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # The marker no longer references an uploaded image, so drop the file.
    from deeptutor.multi_user.identity import delete_avatar_file

    if current.user_id and _USER_ID_RE.match(current.user_id):
        delete_avatar_file(current.user_id)
    return {"ok": True, "avatar": body.avatar}


@router.put("/profile/password")
async def change_profile_password(
    body: PasswordChangeRequest,
    response: Response,
    payload: TokenPayload | None = Depends(require_auth),
) -> dict:
    """Change the current user's password and invalidate existing JWTs."""
    current = _require_profile_identity(payload)
    if POCKETBASE_ENABLED:
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
    response.delete_cookie(key=_COOKIE_NAME, samesite=_SAMESITE)
    return {"ok": True}


@router.post("/profile/revoke-sessions")
async def revoke_profile_sessions(
    response: Response,
    payload: TokenPayload | None = Depends(require_auth),
) -> dict:
    """Invalidate all JWTs for the current local user, including this one."""
    current = _require_profile_identity(payload)
    if POCKETBASE_ENABLED:
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
    response.delete_cookie(key=_COOKIE_NAME, samesite=_SAMESITE)
    return {"ok": True}


@router.get("/profile/export")
async def export_profile_data(
    payload: TokenPayload | None = Depends(require_auth),
) -> FileResponse:
    """Export the current regular user's own data as a zip archive."""
    current = _require_profile_identity(payload)
    if POCKETBASE_ENABLED:
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
    if not user_id or not _USER_ID_RE.match(user_id):
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
    payload: TokenPayload | None = Depends(require_auth),
) -> dict:
    """Delete the current regular user's account after password confirmation."""
    current = _require_profile_identity(payload)
    if POCKETBASE_ENABLED:
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
    data_policy = _apply_user_data_policy(user_id, body.data_action)
    if not delete_user(current.username):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    log_admin_action(
        "user_self_delete",
        target_user_id=user_id,
        summary={"username": current.username, "data_policy": data_policy},
    )
    response.delete_cookie(key=_COOKIE_NAME, samesite=_SAMESITE)
    return {"ok": True, "data_policy": data_policy}


@router.put("/profile/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    payload: TokenPayload | None = Depends(require_auth),
) -> dict:
    """Upload an avatar image for the current user.

    The client is expected to crop/resize before uploading; the server only
    enforces a size cap and validates the format by magic bytes. Not available
    in PocketBase mode (those identities have no local user record).
    """
    current = _require_profile_identity(payload)
    if POCKETBASE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Avatar upload is not available in PocketBase mode.",
        )
    if not current.user_id or not _USER_ID_RE.match(current.user_id):
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

    # Bump the version embedded in the marker so clients cache-bust the URL.
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
    payload: TokenPayload | None = Depends(require_auth),
) -> dict:
    """Remove the current user's uploaded avatar image and reset the marker."""
    current = _require_profile_identity(payload)
    from deeptutor.multi_user.identity import delete_avatar_file

    if current.user_id and _USER_ID_RE.match(current.user_id):
        delete_avatar_file(current.user_id)
    set_avatar(current.username, "")
    return {"ok": True, "avatar": ""}


@router.get("/avatar/{user_id}")
async def get_avatar_image(
    user_id: str,
    _: TokenPayload | None = Depends(require_auth),
) -> FileResponse:
    """Serve a stored avatar image. Any authenticated user may view avatars
    (they appear in the admin table and next to the viewer's own profile)."""
    if not _USER_ID_RE.match(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found")

    from deeptutor.multi_user.identity import get_avatar_file

    target = get_avatar_file(user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found")

    media_type = _AVATAR_MEDIA_TYPES.get(target.suffix.lstrip("."), "application/octet-stream")
    headers = {
        # Private user content; the marker version in the URL handles busting.
        "Cache-Control": "private, max-age=86400",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline",
    }
    return FileResponse(path=str(target), media_type=media_type, headers=headers)


# ---------------------------------------------------------------------------
# Admin-only endpoints
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[UserInfo])
async def get_users(_: TokenPayload = Depends(require_admin)) -> list[UserInfo]:
    """List all registered users. Requires admin role."""
    return [UserInfo(**u) for u in list_users()]


@router.get("/users/export.csv")
async def export_users_csv(_: TokenPayload = Depends(require_admin)) -> Response:
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
    current: TokenPayload = Depends(require_admin),
) -> UserImportResult:
    """Admin-only bulk import for email/password user accounts."""
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auth is disabled — user import is not available.",
        )
    if POCKETBASE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User import is not available in PocketBase mode.",
        )

    data = await file.read()
    if len(data) > _CSV_IMPORT_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="CSV is too large."
        )
    rows = _parse_user_import_csv(data)
    existing = {str(user.get("username") or "").lower() for user in list_users()}
    for row in rows:
        email = str(row["email"])
        if email in existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email already exists: {email}",
            )

    _enforce_user_seats(additional=len(rows))
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


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    body: RegisterRequest,
    current: TokenPayload = Depends(require_admin),
) -> dict:
    """Admin-only: create a new user account.

    Replaces the public ``/register`` flow once the first admin exists. The
    new account is always created with role=``user``; admins can promote
    later via ``PUT /users/{username}/role``.
    """
    if not AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auth is disabled — user creation is not available.",
        )

    if POCKETBASE_ENABLED:
        _enforce_user_seats()
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

    _enforce_user_seats()
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
    current: TokenPayload = Depends(require_admin),
) -> dict:
    """Admin-only: reset another user's password and invalidate their JWTs."""
    if POCKETBASE_ENABLED:
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
    current: TokenPayload = Depends(require_admin),
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
    current: TokenPayload = Depends(require_admin),
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
    current: TokenPayload = Depends(require_admin),
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
    data_policy = _apply_user_data_policy(user_id, data_action)
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
    current: TokenPayload = Depends(require_admin),
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
