from __future__ import annotations

from pathlib import Path

from deeptutor.knowledge.manager import KnowledgeBaseManager


def _create_kb(manager: KnowledgeBaseManager, name: str) -> Path:
    kb_dir = manager.base_dir / name
    (kb_dir / "raw").mkdir(parents=True, exist_ok=True)
    manager.config.setdefault("knowledge_bases", {})[name] = {
        "path": name,
        "description": "",
        "status": "ready",
    }
    manager._save_config()
    return kb_dir


def test_linked_folder_state_round_trips_through_metadata(tmp_path: Path) -> None:
    manager = KnowledgeBaseManager(base_dir=str(tmp_path / "kbs"))
    _create_kb(manager, "kb")
    source = tmp_path / "source"
    source.mkdir()
    note = source / "note.txt"
    note.write_text("hello", encoding="utf-8")

    linked = manager.link_folder("kb", str(source))
    assert linked["file_count"] == 1
    assert manager.link_folder("kb", str(source)) == linked

    changes = manager.detect_folder_changes("kb", linked["id"])
    assert changes["new_files"] == [str(note)]
    assert changes["has_changes"] is True

    manager.update_folder_sync_state("kb", linked["id"], [str(note)])
    assert manager.detect_folder_changes("kb", linked["id"])["has_changes"] is False

    note.write_text("changed", encoding="utf-8")
    modified = manager.detect_folder_changes("kb", linked["id"])
    assert modified["modified_files"] == [str(note)]

    assert manager.unlink_folder("kb", linked["id"]) is True
    assert manager.get_linked_folders("kb") == []
