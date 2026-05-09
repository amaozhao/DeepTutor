from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types

import pytest


@pytest.fixture(autouse=True)
def _cleanup_question_router_module():
    yield
    sys.modules.pop("deeptutor.api.routers.question", None)


def _package(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__path__ = []
    return module


def _load_question_router_module(monkeypatch: pytest.MonkeyPatch):
    sys.modules.pop("deeptutor.api.routers.question", None)

    fake_agents = _package("deeptutor.agents")
    fake_agents_question = types.ModuleType("deeptutor.agents.question")
    fake_agents_question.AgentCoordinator = object
    fake_agents.question = fake_agents_question
    monkeypatch.setitem(sys.modules, "deeptutor.agents", fake_agents)
    monkeypatch.setitem(sys.modules, "deeptutor.agents.question", fake_agents_question)

    fake_logging = _package("deeptutor.logging")
    fake_logging.ProcessLogEvent = object
    fake_logging.bind_log_context = lambda *_args, **_kwargs: pytest.MonkeyPatch.context()
    fake_logging.capture_process_logs = lambda *_args, **_kwargs: pytest.MonkeyPatch.context()
    fake_logging.current_log_context = lambda: {}
    monkeypatch.setitem(sys.modules, "deeptutor.logging", fake_logging)

    fake_config = types.ModuleType("deeptutor.services.config")
    fake_config.PROJECT_ROOT = Path.cwd()
    fake_config.load_config_with_main = lambda *_args, **_kwargs: {}
    monkeypatch.setitem(sys.modules, "deeptutor.services.config", fake_config)

    fake_llm_package = _package("deeptutor.services.llm")
    fake_llm_config = types.ModuleType("deeptutor.services.llm.config")
    fake_llm_config.get_llm_config = lambda: None
    fake_llm_package.config = fake_llm_config
    monkeypatch.setitem(sys.modules, "deeptutor.services.llm", fake_llm_package)
    monkeypatch.setitem(sys.modules, "deeptutor.services.llm.config", fake_llm_config)

    fake_settings_package = _package("deeptutor.services.settings")
    fake_interface_settings = types.ModuleType("deeptutor.services.settings.interface_settings")
    fake_interface_settings.get_ui_language = lambda default="en": default
    fake_settings_package.interface_settings = fake_interface_settings
    monkeypatch.setitem(sys.modules, "deeptutor.services.settings", fake_settings_package)
    monkeypatch.setitem(
        sys.modules,
        "deeptutor.services.settings.interface_settings",
        fake_interface_settings,
    )

    fake_tools = _package("deeptutor.tools")
    fake_tools_question = types.ModuleType("deeptutor.tools.question")

    async def _default_mimic_exam_questions(*_args, **_kwargs):
        return {"success": True}

    fake_tools_question.mimic_exam_questions = _default_mimic_exam_questions
    fake_tools.question = fake_tools_question
    monkeypatch.setitem(sys.modules, "deeptutor.tools", fake_tools)
    monkeypatch.setitem(sys.modules, "deeptutor.tools.question", fake_tools_question)

    return importlib.import_module("deeptutor.api.routers.question")


def test_mimic_resolves_relative_parsed_dir_under_mimic_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_question_router_module(monkeypatch)
    mimic_root = tmp_path / "mimic_papers"
    parsed_dir = mimic_root / "2211asm1"
    parsed_dir.mkdir(parents=True)
    monkeypatch.setattr(module, "MIMIC_OUTPUT_DIR", mimic_root)

    assert module._resolve_mimic_parsed_dir("2211asm1") == parsed_dir.resolve()


def test_mimic_rejects_parsed_path_outside_user_mimic_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_question_router_module(monkeypatch)
    monkeypatch.setattr(module, "MIMIC_OUTPUT_DIR", tmp_path / "mimic_papers")

    with pytest.raises(ValueError, match="current user's mimic output directory"):
        module._resolve_mimic_parsed_dir(str(tmp_path / "outside_paper"))


@pytest.mark.asyncio
async def test_mimic_websocket_sets_and_resets_upstream_user_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_question_router_module(monkeypatch)
    calls: list[str] = []

    async def _fake_set_websocket_current_user(_websocket):
        calls.append("set")
        return object()

    def _fake_reset_websocket_current_user(_token):
        calls.append("reset")

    async def _fake_authenticated_handler(_websocket):
        calls.append("handler")

    monkeypatch.setattr(module, "set_websocket_current_user", _fake_set_websocket_current_user)
    monkeypatch.setattr(module, "reset_websocket_current_user", _fake_reset_websocket_current_user)
    monkeypatch.setattr(module, "_authenticated_websocket_mimic_generate", _fake_authenticated_handler)

    await module.websocket_mimic_generate(object())

    assert calls == ["set", "handler", "reset"]
