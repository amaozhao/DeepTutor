from __future__ import annotations

from deeptutor.services import auth


def test_blank_auth_token_expire_hours_uses_default(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_TOKEN_EXPIRE_HOURS", "")

    assert auth._int_env("AUTH_TOKEN_EXPIRE_HOURS", 24) == 24


def test_auth_token_expire_hours_reads_integer(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_TOKEN_EXPIRE_HOURS", "12")

    assert auth._int_env("AUTH_TOKEN_EXPIRE_HOURS", 24) == 12
