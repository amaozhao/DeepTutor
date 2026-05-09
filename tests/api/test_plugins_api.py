from __future__ import annotations

from pathlib import Path

from deeptutor.api.routers import plugins_api
from deeptutor.services.path_service import get_path_service


def test_direct_web_search_params_strip_output_directory(as_multi_user) -> None:
    with as_multi_user("user_alpha"):
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


def test_direct_code_execution_params_force_user_workspace(as_multi_user) -> None:
    with as_multi_user("user_alpha"):
        params = plugins_api._sanitize_direct_tool_params(
            "code_execution",
            {
                "code": "print(1)",
                "workspace_dir": "/tmp/leak",
                "output_dir": "/tmp/leak",
                "kb_base_dir": "/tmp/leak",
            },
        )
        user_root = get_path_service().get_user_root().resolve()

    assert params["code"] == "print(1)"
    assert "output_dir" not in params
    assert "kb_base_dir" not in params
    assert Path(params["workspace_dir"]).resolve().is_relative_to(user_root)
