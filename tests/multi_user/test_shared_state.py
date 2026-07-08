from __future__ import annotations

from datetime import datetime, timezone


class _FakeSharedState:
    def __init__(self) -> None:
        self.users = {}
        self.grants = {}
        self.usage = []
        self.rate = {}
        self.secret = "shared-secret"
        self.invites = {}

    def postgres_enabled(self):
        return True

    def load_users(self):
        return dict(self.users)

    def save_users(self, users):
        self.users = dict(users)

    def update_users(self, mutator):
        result = mutator(self.users)
        self.users = dict(self.users)
        return result

    def load_or_create_auth_secret(self):
        return self.secret

    def load_grant(self, user_id):
        return self.grants.get(user_id)

    def save_grant(self, user_id, grant):
        self.grants[user_id] = dict(grant)

    def record_usage_event(self, event):
        self.usage.append(dict(event))

    def usage_events(self):
        return list(self.usage)

    def allow_rate_hit(self, bucket, *, limit, window_seconds, now):
        cutoff = now - window_seconds
        hits = [hit for hit in self.rate.get(bucket, []) if hit > cutoff]
        if len(hits) >= limit:
            self.rate[bucket] = hits
            return False
        hits.append(now)
        self.rate[bucket] = hits
        return True

    def clear_rate_hits(self):
        self.rate.clear()

    def load_invites(self):
        return dict(self.invites)

    def update_invites(self, mutator):
        result = mutator(self.invites)
        self.invites = dict(self.invites)
        return result


def test_postgres_shared_state_drives_auth_secret_users_and_token_version(monkeypatch):
    from deeptutor.multi_user import identity
    from deeptutor.services import auth as auth_service

    fake = _FakeSharedState()
    monkeypatch.setattr(identity, "_postgres_enabled", fake.postgres_enabled)
    monkeypatch.setattr(identity, "_postgres_load_users", lambda *_args: fake.load_users())
    monkeypatch.setattr(identity, "_postgres_save_users", fake.save_users)
    monkeypatch.setattr("deeptutor.multi_user.shared_state.update_users", fake.update_users)
    monkeypatch.setattr(auth_service, "AUTH_ENABLED", True)
    monkeypatch.setattr(auth_service, "AUTH_SECRET", fake.load_or_create_auth_secret())

    record = identity.save_user("alice", auth_service.hash_password("password1234"), role="admin")
    token = auth_service.create_token("alice", "admin", record["id"])

    assert auth_service.decode_token(token) is not None
    assert identity.revoke_sessions("alice") is True
    assert auth_service.decode_token(token) is None


def test_postgres_shared_state_create_user_does_not_overwrite(monkeypatch):
    from deeptutor.multi_user import identity

    fake = _FakeSharedState()
    monkeypatch.setattr(identity, "_postgres_enabled", fake.postgres_enabled)
    monkeypatch.setattr("deeptutor.multi_user.shared_state.update_users", fake.update_users)

    created = identity.create_user("alice@example.com", "h1", role="user")
    duplicate = identity.create_user("alice@example.com", "h2", role="user")

    assert created is not None
    assert duplicate is None
    assert fake.users["alice@example.com"]["hash"] == "h1"


def test_postgres_shared_state_imports_file_users_and_secret(mu_isolated_root, monkeypatch):
    from deeptutor.multi_user import identity

    identity.save_user("alice", "hash", role="admin")
    identity.SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    identity.SECRET_FILE.write_text("existing-secret", encoding="utf-8")

    fake = _FakeSharedState()
    fake.users = {}
    imported_secret = {}

    def load_or_create_secret(seed=""):
        imported_secret["seed"] = seed
        return seed or fake.secret

    monkeypatch.setattr(identity, "_postgres_enabled", fake.postgres_enabled)
    monkeypatch.setattr("deeptutor.multi_user.shared_state.load_users", fake.load_users)
    monkeypatch.setattr("deeptutor.multi_user.shared_state.save_users", fake.save_users)
    monkeypatch.setattr(
        "deeptutor.multi_user.shared_state.load_or_create_auth_secret",
        load_or_create_secret,
    )

    users = identity.load_users()

    assert users["alice"]["role"] == "admin"
    assert fake.users["alice"]["role"] == "admin"
    assert identity.load_or_create_auth_secret() == "existing-secret"
    assert imported_secret["seed"] == "existing-secret"


def test_postgres_shared_state_logs_unreadable_auth_secret_seed(
    mu_isolated_root, monkeypatch, caplog
):
    from deeptutor.multi_user import identity

    class _UnreadableSecret:
        def exists(self):
            return True

        def read_text(self, encoding="utf-8"):
            raise OSError("permission denied")

    fake = _FakeSharedState()
    imported_secret = {}

    def load_or_create_secret(seed=""):
        imported_secret["seed"] = seed
        return seed or fake.secret

    monkeypatch.setattr(identity, "_postgres_enabled", fake.postgres_enabled)
    monkeypatch.setattr(identity, "SECRET_FILE", _UnreadableSecret())
    monkeypatch.setattr(
        "deeptutor.multi_user.shared_state.load_or_create_auth_secret",
        load_or_create_secret,
    )

    with caplog.at_level("WARNING", logger="deeptutor.multi_user.identity"):
        assert identity.load_or_create_auth_secret() == fake.secret

    assert imported_secret["seed"] == ""
    assert "Failed to read local auth secret seed" in caplog.text
    assert "permission denied" in caplog.text


def test_postgres_shared_state_drives_grants_and_usage_quota(seed_user, as_user, monkeypatch):
    from deeptutor.multi_user import grants, usage
    from deeptutor.multi_user.usage import UsageQuotaExceeded

    fake = _FakeSharedState()
    monkeypatch.setattr(grants, "_postgres_enabled", fake.postgres_enabled)
    monkeypatch.setattr(usage, "_postgres_enabled", fake.postgres_enabled)
    monkeypatch.setattr("deeptutor.multi_user.shared_state.load_grant", fake.load_grant)
    monkeypatch.setattr("deeptutor.multi_user.shared_state.save_grant", fake.save_grant)
    monkeypatch.setattr(
        "deeptutor.multi_user.shared_state.record_usage_event", fake.record_usage_event
    )
    monkeypatch.setattr("deeptutor.multi_user.shared_state.usage_events", fake.usage_events)

    seed_user("admin", role="admin")
    user = seed_user("alice")
    user_id = user["id"]
    grants.save_grant(user_id, {"quota": {"daily_call_limit": 1}})
    usage.record_usage(
        user_id=user_id,
        username="alice",
        session_id="s1",
        turn_id="t1",
        capability="chat",
        provider="minimax",
        model="M3",
        summary={"total_calls": 1},
    )

    assert usage.usage_summary(user_id, now=datetime.now(timezone.utc))["today"]["total_calls"] == 1
    with as_user(user_id, username="alice"):
        try:
            usage.enforce_current_user_quota()
        except UsageQuotaExceeded:
            pass
        else:  # pragma: no cover
            raise AssertionError("quota should be enforced from shared state")


def test_postgres_shared_state_drives_rate_limiter(monkeypatch):
    from deeptutor.api import security

    fake = _FakeSharedState()
    monkeypatch.setattr(security, "_postgres_shared_state_enabled", fake.postgres_enabled)
    monkeypatch.setattr("deeptutor.multi_user.shared_state.allow_rate_hit", fake.allow_rate_hit)
    monkeypatch.setattr("deeptutor.multi_user.shared_state.clear_rate_hits", fake.clear_rate_hits)

    limiter = security.FileSlidingWindowRateLimiter()

    assert limiter.allow("login:alice", limit=1, window_seconds=60, now=100.0) is True
    assert limiter.allow("login:alice", limit=1, window_seconds=60, now=101.0) is False
    limiter.clear()
    assert limiter.allow("login:alice", limit=1, window_seconds=60, now=102.0) is True


def test_postgres_shared_state_drives_invites(monkeypatch):
    from deeptutor.multi_user import invites

    fake = _FakeSharedState()
    monkeypatch.setattr(invites, "_postgres_enabled", fake.postgres_enabled)
    monkeypatch.setattr("deeptutor.multi_user.shared_state.load_invites", fake.load_invites)
    monkeypatch.setattr("deeptutor.multi_user.shared_state.update_invites", fake.update_invites)

    invite = invites.create_invite(email="learner@example.com", created_by="admin")

    assert invites.list_invites()[0]["code"] == invite["code"]
    assert invites.consume_invite(invite["code"], email="wrong@example.com") is None
    consumed = invites.consume_invite(invite["code"], email="learner@example.com")
    assert consumed is not None
    assert consumed["used_by"] == "learner@example.com"
    assert invites.consume_invite(invite["code"], email="learner@example.com") is None
    assert invites.unconsume_invite(invite["code"], email="learner@example.com") is True
    assert invites.delete_invite(invite["code"]) is True
    assert invites.list_invites() == []


def test_postgres_shared_state_export_and_delete_policy(seed_user, monkeypatch):
    import json
    import zipfile

    from deeptutor.multi_user import grants, usage
    from deeptutor.multi_user.data_governance import apply_user_delete_policy, export_user_data

    fake = _FakeSharedState()
    monkeypatch.setattr(grants, "_postgres_enabled", fake.postgres_enabled)
    monkeypatch.setattr(usage, "_postgres_enabled", fake.postgres_enabled)
    monkeypatch.setattr("deeptutor.multi_user.shared_state.load_grant", fake.load_grant)
    monkeypatch.setattr("deeptutor.multi_user.shared_state.save_grant", fake.save_grant)
    monkeypatch.setattr(
        "deeptutor.multi_user.shared_state.delete_grant",
        lambda user_id: fake.grants.pop(user_id, None),
    )
    monkeypatch.setattr(
        "deeptutor.multi_user.shared_state.record_usage_event", fake.record_usage_event
    )
    monkeypatch.setattr("deeptutor.multi_user.shared_state.usage_events", fake.usage_events)

    seed_user("admin", role="admin")
    user = seed_user("alice")
    user_id = user["id"]
    grants.save_grant(user_id, {"quota": {"daily_call_limit": 2}})
    usage.record_usage(
        user_id=user_id,
        username="alice",
        session_id="s1",
        turn_id="t1",
        capability="chat",
        provider="minimax",
        model="M3",
        summary={"total_calls": 1},
    )

    archive = export_user_data(user_id, "alice")
    with zipfile.ZipFile(archive) as zf:
        grant = json.loads(zf.read("system/grant.json").decode())
        assert grant["quota"]["daily_call_limit"] == 2
        assert user_id in zf.read("system/usage.jsonl").decode()

    result = apply_user_delete_policy(user_id, "delete")

    assert result["grant"] == "deleted"
    assert user_id not in fake.grants
