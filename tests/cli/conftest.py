from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.auth.store import reset_auth_store
from deeptutor.services.path_service import PathService


@pytest.fixture(autouse=True)
def isolate_cli_auth_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir
    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"
        monkeypatch.setenv("DEEPTUTOR_AUTH_FILE", str(tmp_path / "cli-auth.json"))
        reset_auth_store()
        yield
    finally:
        reset_auth_store()
        service._project_root = original_root
        service._user_data_dir = original_user_dir
