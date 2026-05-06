from __future__ import annotations

from pathlib import Path

from deeptutor.auth.migration import migrate_legacy_data_to_user
from deeptutor.services.path_service import PathService


def test_legacy_migration_merges_data_memory_before_user_workspace(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        global_memory = tmp_path / "data" / "memory"
        global_memory.mkdir(parents=True)
        (global_memory / "SUMMARY.md").write_text("global summary", encoding="utf-8")

        legacy_user = tmp_path / "data" / "user"
        legacy_workspace_memory = legacy_user / "workspace" / "memory"
        legacy_workspace_memory.mkdir(parents=True)
        (legacy_workspace_memory / "PROFILE.md").write_text("legacy profile", encoding="utf-8")
        (legacy_user / "settings").mkdir(parents=True)
        (legacy_user / "settings" / "interface.json").write_text("{}", encoding="utf-8")
        (legacy_user / "settings" / "main.yaml").write_text(
            "system:\n  language: en\n", encoding="utf-8"
        )
        (legacy_user / "settings" / "agents.yaml").write_text(
            "capabilities: {}\n", encoding="utf-8"
        )
        (legacy_user / "chat_history.db").write_text("sqlite bytes", encoding="utf-8")

        result = migrate_legacy_data_to_user("user_first")

        user_root = tmp_path / "data" / "users" / "user_first"
        assert result.user_root == user_root
        assert (user_root / "workspace" / "memory" / "SUMMARY.md").read_text(
            encoding="utf-8"
        ) == "global summary"
        assert (user_root / "workspace" / "memory" / "PROFILE.md").read_text(
            encoding="utf-8"
        ) == "legacy profile"
        assert (user_root / "settings" / "interface.json").exists()
        assert (user_root / "settings" / "main.yaml").exists()
        assert (tmp_path / "data" / "system" / "settings" / "main.yaml").exists()
        assert (tmp_path / "data" / "system" / "settings" / "agents.yaml").exists()
        assert (user_root / "chat_history.db").read_text(encoding="utf-8") == "sqlite bytes"
        assert (user_root / ".legacy_migration_complete").exists()
        assert not global_memory.exists()
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
