from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.auth.context import user_scope
from deeptutor.services.path_service import PathService
from deeptutor.services.tutorbot.manager import TutorBotManager
from deeptutor.tutorbot.config import paths as tutorbot_paths


def test_tutorbot_manager_rejects_unsafe_bot_ids(tmp_path: Path) -> None:
    manager = TutorBotManager()
    manager._tutorbot_root = tmp_path / "tutorbot"  # type: ignore[attr-defined]

    with pytest.raises(ValueError):
        manager._bot_dir("../other-user")


def test_tutorbot_path_helpers_reject_unsafe_bot_ids(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
            with pytest.raises(ValueError):
                tutorbot_paths.get_bot_dir("../other-user")
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
