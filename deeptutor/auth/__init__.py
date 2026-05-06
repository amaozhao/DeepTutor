"""Authentication primitives for local DeepTutor users."""

from deeptutor.auth.context import current_user_id, user_scope
from deeptutor.auth.models import AuthSession, AuthUser

__all__ = [
    "AuthSession",
    "AuthUser",
    "current_user_id",
    "user_scope",
]
