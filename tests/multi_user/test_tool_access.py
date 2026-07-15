"""Grant v2 tool/exec whitelists: normalization and runtime resolution."""

from __future__ import annotations

import logging

import pytest

from deeptutor.multi_user.grants import load_grant, normalize_grant, save_grant
from deeptutor.multi_user.tool_access import (
    allowed_mcp_tools,
    allowed_optional_tools,
    combine_whitelists,
    exec_override,
)


@pytest.fixture
def grantable_alice(mu_isolated_root, monkeypatch):
    """Make ``save_grant`` accept u_alice without a real identity record."""
    grants = __import__("deeptutor.multi_user", fromlist=["grants"]).grants

    monkeypatch.setattr(
        grants,
        "get_user_by_id",
        lambda user_id: ("alice", {"role": "user"}) if user_id == "u_alice" else None,
    )
    return "u_alice"


def test_normalize_migrates_v1_to_v2():
    v1 = {
        "version": 1,
        "models": {
            "llm": [{"profile_id": "p", "model_ids": ["m"]}],
            "embedding": [{"profile_id": "e"}],
            "search": [{"profile_id": "s"}],
        },
        "knowledge_bases": [{"resource_id": "admin:kb:demo"}],
        "skills": [{"skill_id": "writer"}],
        "spaces": [{"space_id": "old"}],
    }
    grant = normalize_grant("u_alice", v1)
    assert grant["version"] == 2
    assert grant["models"] == {"llm": [{"profile_id": "p", "model_ids": ["m"]}]}
    assert "spaces" not in grant
    assert grant["knowledge_bases"] == [{"resource_id": "admin:kb:demo"}]
    assert grant["skills"] == [{"skill_id": "writer"}]
    # Absent v2 fields default to unrestricted.
    assert grant["enabled_tools"] is None
    assert grant["mcp_tools"] is None
    assert grant["exec_enabled"] is None


def test_normalize_tool_lists_and_exec():
    grant = normalize_grant(
        "u_alice",
        {
            "enabled_tools": ["web_search", "", "  reason  "],
            "mcp_tools": [],
            "exec_enabled": False,
        },
    )
    assert grant["enabled_tools"] == ["web_search", "reason"]
    assert grant["mcp_tools"] == []
    assert grant["exec_enabled"] is False
    # Non-bool exec values fall back to "follow policy".
    assert normalize_grant("u_alice", {"exec_enabled": "yes"})["exec_enabled"] is None


def test_admin_is_never_restricted(as_user):
    with as_user("u_admin", role="admin"):
        assert allowed_optional_tools() is None
        assert allowed_mcp_tools() is None
        assert exec_override() is None


def test_user_without_grant_keeps_builtins_unrestricted_but_denies_mcp(as_user, mu_isolated_root):
    with as_user("u_alice"):
        assert allowed_optional_tools() is None
        assert allowed_mcp_tools() == set()
        assert exec_override() is None


def test_user_whitelists_resolve_from_grant(as_user, grantable_alice):
    save_grant(
        grantable_alice,
        {
            "enabled_tools": ["web_search"],
            "mcp_tools": ["mcp_demo_search", "mcp_demo_write"],
            "exec_enabled": False,
        },
    )
    with as_user(grantable_alice):
        assert allowed_optional_tools() == {"web_search"}
        assert allowed_mcp_tools() == {"mcp_demo_search", "mcp_demo_write"}
        assert exec_override() is False


def test_saved_grant_round_trips_v2(grantable_alice):
    save_grant(grantable_alice, {"enabled_tools": ["reason"], "exec_enabled": False})
    loaded = load_grant(grantable_alice)
    assert loaded["version"] == 2
    assert loaded["enabled_tools"] == ["reason"]
    assert loaded["mcp_tools"] is None
    assert loaded["exec_enabled"] is False


def test_save_grant_uses_local_write_lock(grantable_alice, mu_isolated_root):
    save_grant(grantable_alice, {"enabled_tools": ["reason"]})

    assert (mu_isolated_root / "data" / "system" / "grants" / f"{grantable_alice}.lock").exists()


def test_save_grant_logs_when_file_lock_is_unavailable(
    grantable_alice, mu_isolated_root, caplog, monkeypatch
):
    grants = __import__("deeptutor.multi_user", fromlist=["grants"]).grants

    class _BrokenFcntl:
        LOCK_EX = 1
        LOCK_UN = 2

        @staticmethod
        def flock(*_args):
            raise OSError("no flock")

    monkeypatch.setattr(grants, "fcntl_module", _BrokenFcntl)
    caplog.set_level(logging.WARNING, logger="deeptutor.multi_user.grants")

    save_grant(grantable_alice, {"enabled_tools": ["reason"]})

    assert load_grant(grantable_alice)["enabled_tools"] == ["reason"]
    assert "Grant write lock unavailable" in caplog.text


def test_load_grant_does_not_take_write_lock(grantable_alice, mu_isolated_root):
    save_grant(grantable_alice, {"enabled_tools": ["reason"]})
    lock_file = mu_isolated_root / "data" / "system" / "grants" / f"{grantable_alice}.lock"
    lock_file.unlink()

    assert load_grant(grantable_alice)["enabled_tools"] == ["reason"]
    assert not lock_file.exists()


def test_load_grant_logs_corrupt_grant_fallback(grantable_alice, mu_isolated_root, caplog):
    grant_file = mu_isolated_root / "data" / "system" / "grants" / f"{grantable_alice}.json"
    grant_file.parent.mkdir(parents=True, exist_ok=True)
    grant_file.write_text("{bad json", encoding="utf-8")

    caplog.set_level(logging.WARNING, logger="deeptutor.multi_user.grants")

    grant = load_grant(grantable_alice)

    assert grant == normalize_grant(grantable_alice, None)
    assert "Failed to load grant for user u_alice" in caplog.text


def test_combine_whitelists():
    assert combine_whitelists(None, None) is None
    assert combine_whitelists({"a"}, None) == {"a"}
    assert combine_whitelists(None, {"b"}) == {"b"}
    assert combine_whitelists({"a", "b"}, {"b", "c"}) == {"b"}


def test_enabled_optional_tools_filtered_by_grant(as_user, grantable_alice, monkeypatch):
    settings_router = __import__("deeptutor.api.routers", fromlist=["settings"]).settings

    monkeypatch.setattr(
        settings_router,
        "load_ui_settings",
        lambda: {"enabled_optional_tools": ["web_search", "reason", "brainstorm"]},
    )
    save_grant(grantable_alice, {"enabled_tools": ["reason"]})
    with as_user(grantable_alice):
        assert settings_router.get_enabled_optional_tools() == ["reason"]
