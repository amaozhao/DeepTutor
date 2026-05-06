from __future__ import annotations

from deeptutor.auth.passwords import hash_password, verify_password


def test_hash_password_does_not_store_plaintext() -> None:
    hashed = hash_password("correct horse battery staple")

    assert hashed
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_hash_password_uses_unique_salt() -> None:
    first = hash_password("same password")
    second = hash_password("same password")

    assert first != second
    assert verify_password("same password", first) is True
    assert verify_password("same password", second) is True
