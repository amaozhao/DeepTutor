"""Contract: new registrations are email/password, while login stays legacy-safe."""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from deeptutor.api.routers.auth import LoginRequest, RegisterRequest

# ---------------------------------------------------------------------------
# RegisterRequest.username — email/password account creation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "username",
    [
        "admin@admin.com",  # standard email (PocketBase mode)
        "user.name@sub.example.co",  # email with dotted local/sub-domain
    ],
)
def test_register_accepts_email(username: str) -> None:
    assert RegisterRequest(username=username, password="password1234").username == username


@pytest.mark.parametrize(
    "username",
    [
        "",  # empty
        "   ",  # whitespace only
        "admin",
        "john_doe",
        "user.name",
        "a-b-c",
        "has space",
        "@nodomain",
        "bad@",
        "no-at-but-bad!",
    ],
)
def test_register_rejects_invalid_username(username: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(username=username, password="password1234")


def test_register_username_is_trimmed() -> None:
    assert (
        RegisterRequest(username="  ADMIN@Example.COM  ", password="password1234").username
        == "admin@example.com"
    )


@pytest.mark.parametrize("password", ["", "short", "1234567"])  # all < 8 chars
def test_register_rejects_short_password(password: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(username="admin@example.com", password=password)


def test_register_accepts_eight_char_password() -> None:
    assert RegisterRequest(username="admin@example.com", password="12345678").password == "12345678"


# ---------------------------------------------------------------------------
# LoginRequest — must NOT impose email-only validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("username", ["admin", "admin@admin.com", "john_doe"])
def test_login_accepts_plain_username(username: str) -> None:
    """Login must accept legacy bare usernames and must not re-validate password length."""
    req = LoginRequest(username=username, password="x")
    assert req.username == username
    assert req.password == "x"


# ---------------------------------------------------------------------------
# End-to-end: a user created with a plain username can authenticate
# ---------------------------------------------------------------------------


def test_authenticate_round_trip_with_plain_username(
    monkeypatch: pytest.MonkeyPatch, seed_user
) -> None:
    pytest.importorskip("bcrypt")  # password hashing dep; present in CI/Docker
    auth_service = __import__("deeptutor.services", fromlist=["auth"]).auth

    monkeypatch.setattr(auth_service, "AUTH_ENABLED", True)
    seed_user("plainuser", password="password1234")

    payload = auth_service.authenticate("plainuser", "password1234")
    assert payload is not None
    assert payload.username == "plainuser"

    assert auth_service.authenticate("plainuser", "wrong-password") is None
    assert auth_service.authenticate("ghost", "password1234") is None
