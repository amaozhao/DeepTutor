from contextlib import contextmanager
import logging
from pathlib import Path

from deeptutor.multi_user import identity, paths
from deeptutor.multi_user.context import reset_current_user, set_current_user
from deeptutor.multi_user.models import CurrentUser, UserScope
from deeptutor.services.path_service import get_path_service


def test_identity_migrates_legacy_users_with_stable_uid(tmp_path, monkeypatch):
    legacy = tmp_path / "data" / "user" / "auth_users.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"alice":{"hash":"h1","role":"admin","created_at":"t"},"bob":"h2"}')
    users_file = tmp_path / "data" / "system" / "auth" / "users.json"

    monkeypatch.setattr(identity, "USERS_FILE", users_file)
    monkeypatch.setattr(identity, "LEGACY_USERS_FILE", legacy)

    users = identity.load_users()

    assert users["alice"]["id"].startswith("u_")
    assert users["alice"]["role"] == "admin"
    assert users["bob"]["role"] == "user"
    assert users_file.exists()


def test_identity_writes_under_local_auth_store_write_lock(mu_isolated_root):
    identity.save_user("alice", "h1", role="user")
    identity.save_user("bob", "h2", role="user")

    users = identity.load_users()

    assert users["alice"]["role"] == "admin"
    assert users["bob"]["role"] == "user"
    assert (mu_isolated_root / "data" / "system" / "auth" / "users.lock").exists()


def test_identity_logs_when_auth_store_file_lock_is_unavailable(
    mu_isolated_root, caplog, monkeypatch
):
    class _BrokenFcntl:
        LOCK_EX = 1
        LOCK_UN = 2

        @staticmethod
        def flock(*_args):
            raise OSError("no flock")

    monkeypatch.setattr(identity, "fcntl_module", _BrokenFcntl)
    caplog.set_level(logging.WARNING, logger="deeptutor.multi_user.identity")

    identity.save_user("alice", "h1", role="user")

    assert identity.load_users()["alice"]["role"] == "admin"
    assert "Auth store write lock unavailable" in caplog.text


def test_create_user_does_not_overwrite_existing_email(mu_isolated_root):
    created = identity.create_user("alice@example.com", "h1", role="user")
    duplicate = identity.create_user("alice@example.com", "h2", role="user")

    users = identity.load_users()
    assert created is not None
    assert duplicate is None
    assert users["alice@example.com"]["hash"] == "h1"


def test_identity_plain_reads_do_not_take_write_lock(mu_isolated_root):
    identity.save_user("alice", "h1", role="user")
    lock_file = mu_isolated_root / "data" / "system" / "auth" / "users.lock"
    lock_file.unlink()

    assert identity.load_users()["alice"]["role"] == "admin"
    assert not lock_file.exists()


def test_auth_secret_creation_uses_auth_store_write_lock(mu_isolated_root):
    secret = identity.load_or_create_auth_secret()

    auth_root = mu_isolated_root / "data" / "system" / "auth"
    assert len(secret) == 64
    assert (auth_root / "auth_secret").read_text(encoding="utf-8") == secret
    assert (auth_root / "users.lock").exists()
    assert not (auth_root / "auth_secret.tmp").exists()


def test_auth_secret_creation_logs_chmod_failure(mu_isolated_root, caplog, monkeypatch):
    original_chmod = Path.chmod

    def fail_auth_secret_chmod(path: Path, mode: int):
        if path.name == "auth_secret":
            raise OSError("chmod denied")
        return original_chmod(path, mode)

    monkeypatch.setattr(Path, "chmod", fail_auth_secret_chmod)
    caplog.set_level(logging.WARNING, logger="deeptutor.multi_user.identity")

    secret = identity.load_or_create_auth_secret()

    assert len(secret) == 64
    assert "Failed to restrict auth secret permissions" in caplog.text


def test_existing_auth_secret_read_does_not_take_write_lock(mu_isolated_root):
    secret_file = mu_isolated_root / "data" / "system" / "auth" / "auth_secret"
    secret_file.parent.mkdir(parents=True)
    secret_file.write_text("stable-secret", encoding="utf-8")

    assert identity.load_or_create_auth_secret() == "stable-secret"
    assert not (secret_file.parent / "users.lock").exists()


def test_invite_writes_reuse_auth_store_write_lock(mu_isolated_root, monkeypatch):
    invites = __import__("deeptutor.multi_user", fromlist=["invites"]).invites

    calls = 0

    @contextmanager
    def fake_lock():
        nonlocal calls
        calls += 1
        yield

    monkeypatch.setattr(invites, "auth_store_write_lock", fake_lock)

    invite = invites.create_invite(email="learner@example.com", created_by="admin")
    assert calls == 1

    assert invites.consume_invite(invite["code"], email="learner@example.com") is not None
    assert calls == 2

    second = invites.create_invite(email="other@example.com", created_by="admin")
    assert calls == 3
    assert invites.delete_invite(second["code"]) is True
    assert calls == 4


def test_path_service_uses_current_user_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ensure_user_workspace", lambda _uid: tmp_path)
    user_root = tmp_path / "data" / "users" / "u_alice"
    user = CurrentUser(
        id="u_alice",
        username="alice",
        role="user",
        scope=UserScope(kind="user", user_id="u_alice", root=user_root),
    )

    token = set_current_user(user)
    try:
        service = get_path_service()
        assert service.workspace_root == user_root.resolve()
        assert service.get_chat_history_db() == user_root.resolve() / "user" / "chat_history.db"
        assert service.get_knowledge_bases_root() == user_root.resolve() / "knowledge_bases"
    finally:
        reset_current_user(token)


def test_legacy_multi_user_tree_migrates_into_data(tmp_path, monkeypatch):
    legacy = tmp_path / "multi-user"
    (legacy / "_system" / "auth").mkdir(parents=True)
    (legacy / "_system" / "auth" / "users.json").write_text("{}")
    (legacy / "u_alice" / "user").mkdir(parents=True)
    (legacy / "u_alice" / "user" / "chat_history.db").write_text("x")

    users_root = tmp_path / "data" / "users"
    system_root = tmp_path / "data" / "system"
    monkeypatch.setattr(paths, "LEGACY_MULTI_USER_ROOT", legacy)
    monkeypatch.setattr(paths, "USERS_ROOT", users_root)
    monkeypatch.setattr(paths, "SYSTEM_ROOT", system_root)
    monkeypatch.setattr(paths, "_legacy_migration_done", False)

    paths.migrate_legacy_multi_user_tree()

    assert (system_root / "auth" / "users.json").read_text() == "{}"
    assert (users_root / "u_alice" / "user" / "chat_history.db").read_text() == "x"
    assert not legacy.exists()


def test_legacy_migration_never_overwrites_existing_targets(tmp_path, monkeypatch):
    legacy = tmp_path / "multi-user"
    (legacy / "u_alice").mkdir(parents=True)
    (legacy / "u_alice" / "old.txt").write_text("legacy")
    (legacy / "u_bob").mkdir(parents=True)
    (legacy / "u_bob" / "data.txt").write_text("bob")

    users_root = tmp_path / "data" / "users"
    (users_root / "u_alice").mkdir(parents=True)
    (users_root / "u_alice" / "new.txt").write_text("current")

    monkeypatch.setattr(paths, "LEGACY_MULTI_USER_ROOT", legacy)
    monkeypatch.setattr(paths, "USERS_ROOT", users_root)
    monkeypatch.setattr(paths, "SYSTEM_ROOT", tmp_path / "data" / "system")
    monkeypatch.setattr(paths, "_legacy_migration_done", False)

    paths.migrate_legacy_multi_user_tree()

    # Existing target untouched; the colliding legacy dir stays for manual
    # reconciliation while non-colliding siblings still migrate.
    assert (users_root / "u_alice" / "new.txt").read_text() == "current"
    assert (legacy / "u_alice" / "old.txt").read_text() == "legacy"
    assert (users_root / "u_bob" / "data.txt").read_text() == "bob"
    assert legacy.exists()
