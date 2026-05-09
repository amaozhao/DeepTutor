from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from deeptutor.multi_user import grants, paths
from deeptutor.multi_user.knowledge_access import (
    assert_writable,
    list_visible_knowledge_bases,
    resolve_kb,
)
from deeptutor.services.path_service import PathService
from deeptutor.services.storage.attachment_store import (
    LocalDiskAttachmentStore,
    get_attachment_store,
    reset_attachment_store,
)


def _write_kb_config(base, *names: str) -> None:
    base.mkdir(parents=True, exist_ok=True)
    payload = {
        "defaults": {"default_kb": names[0] if names else None},
        "knowledge_bases": {
            name: {
                "path": name,
                "description": f"Knowledge base: {name}",
                "status": "ready",
            }
            for name in names
        },
    }
    (base / "kb_config.json").write_text(json.dumps(payload), encoding="utf-8")
    for name in names:
        (base / name / "raw").mkdir(parents=True, exist_ok=True)


def _write_grant(user_id: str, payload: dict) -> None:
    grants.GRANTS_DIR.mkdir(parents=True, exist_ok=True)
    (grants.GRANTS_DIR / f"{user_id}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_admin_knowledge_bases_are_hidden_until_granted(
    tmp_path, monkeypatch, as_multi_user
) -> None:
    from deeptutor.multi_user import knowledge_access

    monkeypatch.setattr(grants, "GRANTS_DIR", tmp_path / "grants")
    knowledge_access._manager_for.cache_clear()

    admin_base = paths.ADMIN_WORKSPACE_ROOT / "knowledge_bases"
    user_base = paths.MULTI_USER_ROOT / "u_child" / "knowledge_bases"
    _write_kb_config(admin_base, "admin-shared")
    _write_kb_config(user_base, "child-private")

    with as_multi_user("u_child", username="child"):
        visible = list_visible_knowledge_bases()
        assert {item["id"] for item in visible} == {"user:kb:child-private"}

        with pytest.raises(HTTPException) as missing:
            resolve_kb("admin-shared")
        assert missing.value.status_code == 404

        with pytest.raises(HTTPException) as forbidden:
            resolve_kb("admin:kb:admin-shared")
        assert forbidden.value.status_code == 403

    _write_grant(
        "u_child",
        {
            "version": 1,
            "user_id": "u_child",
            "models": {"llm": [], "embedding": [], "search": []},
            "knowledge_bases": [{"resource_id": "admin:kb:admin-shared"}],
            "skills": [],
            "spaces": [],
        },
    )

    with as_multi_user("u_child", username="child"):
        visible = list_visible_knowledge_bases()
        assigned = next(item for item in visible if item["id"] == "admin:kb:admin-shared")
        assert assigned["assigned"] is True
        assert assigned["read_only"] is True

        resource = resolve_kb("admin:kb:admin-shared")
        assert resource.assigned is True
        assert resource.read_only is True
        assert resource.base_dir == admin_base.resolve()

        with pytest.raises(HTTPException) as forbidden_write:
            assert_writable("admin:kb:admin-shared")
        assert forbidden_write.value.status_code == 403


@pytest.mark.asyncio
async def test_attachment_store_resolves_only_current_user_root(
    monkeypatch, as_multi_user
) -> None:
    monkeypatch.delenv("CHAT_ATTACHMENT_DIR", raising=False)
    reset_attachment_store()
    PathService.reset_instance()

    try:
        with as_multi_user("u_admin", role="admin", username="admin"):
            admin_store = get_attachment_store()
            assert isinstance(admin_store, LocalDiskAttachmentStore)
            await admin_store.put(
                session_id="session-one",
                attachment_id="att-one",
                filename="note.txt",
                data=b"admin-only",
            )
            admin_path = admin_store.resolve_path(
                session_id="session-one",
                attachment_id="att-one",
                filename="note.txt",
            )
            assert admin_path is not None
            assert admin_path.read_bytes() == b"admin-only"

        with as_multi_user("u_child", username="child"):
            child_store = get_attachment_store()
            assert isinstance(child_store, LocalDiskAttachmentStore)
            assert child_store.root != admin_store.root
            assert (
                child_store.resolve_path(
                    session_id="session-one",
                    attachment_id="att-one",
                    filename="note.txt",
                )
                is None
            )
    finally:
        reset_attachment_store()
        PathService.reset_instance()
