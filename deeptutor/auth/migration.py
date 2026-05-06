from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from pathlib import Path
import shutil

from deeptutor.auth.context import validate_user_id
from deeptutor.services.path_service import get_path_service


@dataclass(frozen=True)
class LegacyMigrationResult:
    user_id: str
    user_root: Path
    moved: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)


def _merge_dir(source: Path, target: Path, *, moved: list[Path], skipped: list[Path]) -> None:
    if not source.exists():
        return
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if destination.exists():
            skipped.append(item)
            if item.is_dir():
                _merge_dir(item, destination, moved=moved, skipped=skipped)
                with contextlib.suppress(OSError):
                    item.rmdir()
            continue
        shutil.move(str(item), str(destination))
        moved.append(destination)
    with contextlib.suppress(OSError):
        source.rmdir()


def _copy_global_runtime_settings(
    source_dir: Path,
    target_dir: Path,
    *,
    moved: list[Path],
    skipped: list[Path],
) -> None:
    for name in ("main.yaml", "agents.yaml", "model_catalog.json"):
        source = source_dir / name
        if not source.exists():
            continue
        target = target_dir / name
        if target.exists():
            skipped.append(source)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        moved.append(target)


def migrate_legacy_data_to_user(user_id: str) -> LegacyMigrationResult:
    """Move pre-auth local data into the first user's private workspace.

    `data/memory` is merged before `data/user` so legacy memory files are not
    skipped when `data/user/workspace/memory` already exists.
    """
    resolved_user_id = validate_user_id(user_id)
    path_service = get_path_service()
    data_root = path_service.get_data_root()
    user_root = path_service.get_users_root() / resolved_user_id
    marker = user_root / ".legacy_migration_complete"
    if marker.exists():
        return LegacyMigrationResult(user_id=resolved_user_id, user_root=user_root)

    moved: list[Path] = []
    skipped: list[Path] = []
    user_root.mkdir(parents=True, exist_ok=True)

    legacy_settings_dir = data_root / "user" / "settings"
    _copy_global_runtime_settings(
        legacy_settings_dir,
        path_service.get_system_settings_dir(),
        moved=moved,
        skipped=skipped,
    )

    _merge_dir(
        data_root / "memory",
        user_root / "workspace" / "memory",
        moved=moved,
        skipped=skipped,
    )

    legacy_user_root = data_root / "user"
    if legacy_user_root.exists() and legacy_user_root.resolve() != user_root.resolve():
        _merge_dir(legacy_user_root, user_root, moved=moved, skipped=skipped)

    legacy_chat_db = data_root / "chat_history.db"
    if legacy_chat_db.exists():
        target_db = user_root / "chat_history.db"
        if target_db.exists():
            skipped.append(legacy_chat_db)
        else:
            target_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy_chat_db), str(target_db))
            moved.append(target_db)

    marker.write_text("complete\n", encoding="utf-8")
    return LegacyMigrationResult(
        user_id=resolved_user_id,
        user_root=user_root,
        moved=moved,
        skipped=skipped,
    )


__all__ = ["LegacyMigrationResult", "migrate_legacy_data_to_user"]
