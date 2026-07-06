"""User data export and deletion policy helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
from typing import Any, Literal
import zipfile

from . import paths

DeleteDataAction = Literal["keep", "archive", "delete"]

DEFAULT_DATA_GOVERNANCE_SETTINGS: dict[str, int] = {
    # 0 means keep forever. Cleanup is explicit/admin-triggered so private
    # deployments do not start deleting data just because a file was upgraded.
    "audit_retention_days": 0,
    "usage_retention_days": 0,
    "deleted_user_retention_days": 0,
}


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _settings_file() -> Path:
    return paths.get_admin_path_service().get_settings_file("data_governance")


def _coerce_days(value: Any) -> int:
    try:
        days = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    return max(0, days)


def normalize_data_governance_settings(value: dict[str, Any] | None) -> dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    return {
        key: _coerce_days(raw.get(key, default))
        for key, default in DEFAULT_DATA_GOVERNANCE_SETTINGS.items()
    }


def load_data_governance_settings() -> dict[str, int]:
    path = _settings_file()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        loaded = {}
    settings = normalize_data_governance_settings(loaded if isinstance(loaded, dict) else {})
    if settings != loaded:
        save_data_governance_settings(settings)
    return settings


def save_data_governance_settings(settings: dict[str, Any]) -> dict[str, int]:
    normalized = normalize_data_governance_settings(settings)
    path = _settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return normalized


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _retention_cutoff(days: int) -> datetime | None:
    return None if days <= 0 else datetime.now(timezone.utc) - timedelta(days=days)


def _prune_jsonl(path: Path, retention_days: int) -> dict[str, int]:
    cutoff = _retention_cutoff(retention_days)
    if cutoff is None or not path.exists():
        return {"removed": 0}
    kept: list[str] = []
    removed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            kept.append(line)
            continue
        event_time = _parse_time(item.get("time")) if isinstance(item, dict) else None
        if event_time is not None and event_time < cutoff:
            removed += 1
        else:
            kept.append(line)
    if removed:
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        tmp.replace(path)
    return {"removed": removed}


def _prune_deleted_user_archives(root: Path, retention_days: int) -> dict[str, int]:
    cutoff = _retention_cutoff(retention_days)
    if cutoff is None or not root.exists():
        return {"removed": 0}
    removed = 0
    for archive in root.iterdir():
        if not archive.is_dir():
            continue
        manifest = archive / "manifest.json"
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        archived_at = _parse_time(data.get("archived_at") if isinstance(data, dict) else None)
        if archived_at is not None and archived_at < cutoff:
            shutil.rmtree(archive)
            removed += 1
    return {"removed": removed}


def apply_data_retention_policy() -> dict[str, Any]:
    """Prune data covered by the configured retention windows."""
    paths.ensure_system_dirs()
    settings = load_data_governance_settings()
    from .audit import _audit_write_lock
    from .usage import usage_ledger_lock

    with usage_ledger_lock():
        usage_result = _prune_jsonl(
            paths.SYSTEM_ROOT / "usage" / "llm_usage.jsonl",
            settings["usage_retention_days"],
        )
    with _audit_write_lock():
        audit_result = _prune_jsonl(
            paths.SYSTEM_ROOT / "audit" / "usage.jsonl",
            settings["audit_retention_days"],
        )
    result = {
        "settings": settings,
        "audit": audit_result,
        "usage": usage_result,
        "deleted_users": _prune_deleted_user_archives(
            paths.SYSTEM_ROOT / "deleted_users",
            settings["deleted_user_retention_days"],
        ),
    }
    result["removed_total"] = sum(
        int(value.get("removed", 0))
        for key, value in result.items()
        if key != "settings" and isinstance(value, dict)
    )
    return result


def _write_jsonl_to_zip(
    archive: zipfile.ZipFile,
    arcname: str,
    rows: list[dict[str, Any]],
) -> None:
    archive.writestr(
        arcname,
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
    )


def _add_tree(archive: zipfile.ZipFile, root: Path, prefix: str) -> None:
    if not root.exists():
        return
    resolved_root = root.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        resolved = path.resolve()
        try:
            rel = resolved.relative_to(resolved_root)
        except ValueError:
            continue
        archive.write(resolved, f"{prefix}/{rel.as_posix()}")


def export_user_data(user_id: str, username: str) -> Path:
    paths.ensure_system_dirs()
    export_dir = paths.SYSTEM_ROOT / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    target = export_dir / f"{user_id}-{_stamp()}.zip"
    workspace = paths.USERS_ROOT / user_id
    grant_file = paths.SYSTEM_ROOT / "grants" / f"{user_id}.json"
    usage_file = paths.SYSTEM_ROOT / "usage" / "llm_usage.jsonl"
    audit_file = paths.SYSTEM_ROOT / "audit" / "usage.jsonl"
    from .identity import get_user
    from .usage import usage_ledger_lock

    record = get_user(username) or {}
    account = {
        "id": str(record.get("id") or user_id),
        "username": username,
        "role": str(record.get("role") or ""),
        "created_at": str(record.get("created_at") or ""),
        "disabled": bool(record.get("disabled", False)),
        "disabled_reason": str(record.get("disabled_reason") or ""),
        "avatar": str(record.get("avatar") or ""),
        "terms_accepted": bool(record.get("terms_accepted", False)),
        "terms_accepted_at": str(record.get("terms_accepted_at") or ""),
        "terms_version": str(record.get("terms_version") or ""),
        "privacy_version": str(record.get("privacy_version") or ""),
    }

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "user_id": user_id,
                    "username": username,
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "workspace_included": workspace.exists(),
                    "grant_included": grant_file.exists(),
                },
                indent=2,
                ensure_ascii=False,
            ),
        )
        archive.writestr(
            "system/account.json",
            json.dumps(account, indent=2, ensure_ascii=False),
        )
        _add_tree(archive, workspace, "workspace")
        if grant_file.exists():
            archive.write(grant_file, "system/grant.json")
        with usage_ledger_lock():
            usage_rows = [
                row for row in _read_jsonl(usage_file) if str(row.get("user_id") or "") == user_id
            ]
        _write_jsonl_to_zip(archive, "system/usage.jsonl", usage_rows)
        _write_jsonl_to_zip(
            archive,
            "system/audit.jsonl",
            [
                row
                for row in _read_jsonl(audit_file)
                if user_id
                in {
                    str(row.get("user_id") or ""),
                    str(row.get("target_user_id") or ""),
                    str(row.get("actor_id") or ""),
                }
            ],
        )
    return target


def apply_user_delete_policy(user_id: str, action: DeleteDataAction) -> dict[str, Any]:
    if action == "keep":
        return {"action": "keep", "workspace": "kept", "grant": "kept"}
    if action not in {"archive", "delete"}:
        raise ValueError(f"Unknown delete data action: {action}")

    workspace = paths.USERS_ROOT / user_id
    grant_file = paths.SYSTEM_ROOT / "grants" / f"{user_id}.json"

    if action == "delete":
        if workspace.exists():
            shutil.rmtree(workspace)
        grant_file.unlink(missing_ok=True)
        return {"action": "delete", "workspace": "deleted", "grant": "deleted"}

    archive_root = paths.SYSTEM_ROOT / "deleted_users" / f"{user_id}-{_stamp()}"
    archive_root.mkdir(parents=True, exist_ok=False)
    manifest = {
        "user_id": user_id,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "workspace": "missing",
        "grant": "missing",
    }
    if workspace.exists():
        archive_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(workspace), str(archive_root / "workspace"))
        manifest["workspace"] = "archived"
    if grant_file.exists():
        shutil.move(str(grant_file), str(archive_root / "grant.json"))
        manifest["grant"] = "archived"
    (archive_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {"action": "archive", **manifest, "archive": str(archive_root)}
