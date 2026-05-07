from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from deeptutor.auth.context import user_scope
from deeptutor.services.path_service import PathService
from deeptutor.services.tutorbot import get_tutorbot_manager, reset_tutorbot_managers
from deeptutor.services.tutorbot.manager import BotConfig


def test_tutorbot_manager_is_cached_per_user_root(tmp_path: Path) -> None:
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir
    reset_tutorbot_managers()

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
            alpha = get_tutorbot_manager()

        with user_scope("user_beta"):
            beta = get_tutorbot_manager()

        assert alpha is not beta
        assert alpha._tutorbot_dir == (
            tmp_path / "data" / "users" / "user_alpha" / "workspace" / "tutorbot"
        )
        assert beta._tutorbot_dir == (
            tmp_path / "data" / "users" / "user_beta" / "workspace" / "tutorbot"
        )
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
        reset_tutorbot_managers()


def test_tutorbot_path_helpers_use_current_user_root(tmp_path: Path) -> None:
    from deeptutor.tutorbot.config import paths as tutorbot_paths

    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        with user_scope("user_alpha"):
            base = tmp_path / "data" / "users" / "user_alpha" / "workspace" / "tutorbot"
            assert tutorbot_paths.get_data_dir() == base
            assert tutorbot_paths.get_media_dir() == base / "media"
            assert tutorbot_paths.get_bot_workspace("bot1") == base / "bot1" / "workspace"
            assert (
                tutorbot_paths.get_shared_memory_dir()
                == tmp_path / "data" / "users" / "user_alpha" / "workspace" / "memory"
            )
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir


def test_started_tutorbot_restricts_agent_loop_to_workspace(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}
    service = PathService.get_instance()
    original_root = service._project_root
    original_user_dir = service._user_data_dir
    reset_tutorbot_managers()

    class FakeAgentLoop:
        def __init__(self, *args, **kwargs) -> None:
            captured.update(kwargs)
            self.model = kwargs.get("model") or "fake-model"
            self.context_window_tokens = kwargs.get("context_window_tokens") or 65_536

        async def run(self) -> None:
            return None

        async def process_direct(self, *_args, **_kwargs) -> str:
            return "ok"

    class FakeHeartbeat:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def start(self) -> None:
            return None

    async def _done() -> None:
        return None

    monkeypatch.setattr("deeptutor.tutorbot.agent.loop.AgentLoop", FakeAgentLoop)
    monkeypatch.setattr(
        "deeptutor.tutorbot.providers.deeptutor_adapter.create_deeptutor_provider",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "deeptutor.services.tutorbot.model_runtime.resolve_tutorbot_llm_config",
        lambda _cfg: SimpleNamespace(model="selected-model", context_window=123456),
    )
    monkeypatch.setattr(
        "deeptutor.services.tutorbot.manager.TutorBotManager._build_channel_manager",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "deeptutor.services.tutorbot.manager.TutorBotManager._outbound_router",
        lambda *_args, **_kwargs: _done(),
    )
    monkeypatch.setattr("deeptutor.tutorbot.heartbeat.HeartbeatService", FakeHeartbeat)

    try:
        service._project_root = tmp_path
        service._user_data_dir = tmp_path / "data" / "user"

        async def run_start() -> None:
            with user_scope("user_alpha"):
                manager = get_tutorbot_manager()
                instance = await manager.start_bot("safe-bot", BotConfig(name="Safe Bot"))
                for task in instance.tasks:
                    task.cancel()

        asyncio.run(run_start())

        assert captured["restrict_to_workspace"] is True
        assert captured["workspace"] == (
            tmp_path
            / "data"
            / "users"
            / "user_alpha"
            / "workspace"
            / "tutorbot"
            / "safe-bot"
            / "workspace"
        )
    finally:
        service._project_root = original_root
        service._user_data_dir = original_user_dir
        reset_tutorbot_managers()
