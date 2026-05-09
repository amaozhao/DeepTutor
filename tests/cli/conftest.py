from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.services.path_service import PathService


@pytest.fixture(autouse=True)
def isolate_cli_path_state(tmp_path: Path):
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir
    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"
        yield
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
