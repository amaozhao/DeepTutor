from __future__ import annotations

from pathlib import Path

from deeptutor.api.routers import plugins_api
from deeptutor.auth.context import user_scope
from deeptutor.services.path_service import PathService


def test_direct_web_search_params_strip_output_directory(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
            params = plugins_api._sanitize_direct_tool_params(
                "web_search",
                {
                    "query": "latest research",
                    "output_dir": "/tmp/leak",
                    "workspace_dir": "/tmp/leak",
                    "kb_base_dir": "/tmp/leak",
                },
            )

        assert params == {"query": "latest research"}
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


def test_direct_code_execution_params_force_user_workspace(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
            params = plugins_api._sanitize_direct_tool_params(
                "code_execution",
                {
                    "code": "print(1)",
                    "workspace_dir": "/tmp/leak",
                    "output_dir": "/tmp/leak",
                    "kb_base_dir": "/tmp/leak",
                },
            )
            user_root = service.get_user_root().resolve()

        assert params["code"] == "print(1)"
        assert "output_dir" not in params
        assert "kb_base_dir" not in params
        assert Path(params["workspace_dir"]).resolve().is_relative_to(user_root)
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
