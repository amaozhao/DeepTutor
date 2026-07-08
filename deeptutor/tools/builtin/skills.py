"""Skill-loading built-in tool wrappers."""

from __future__ import annotations

import logging
from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.multi_user.context import get_current_user
from deeptutor.multi_user.paths import get_admin_path_service
from deeptutor.multi_user.skill_access import assigned_skill_ids
from deeptutor.services.skill import get_skill_service
from deeptutor.services.skill.service import (
    InvalidSkillNameError,
    InvalidSkillPathError,
    SkillNotFoundError,
    SkillService,
)
from deeptutor.tools.builtin.common import _PromptHintsMixin

logger = logging.getLogger(__name__)


class ReadSkillTool(_PromptHintsMixin, BaseTool):
    """Read a skill package's SKILL.md or one of its reference files.

    The system prompt carries only a one-line manifest per skill; this tool
    is how the model pulls the full playbook on demand (progressive
    disclosure). Multi-user-safe: skills resolve via the active user's
    workspace (user layer shadows builtin), plus admin-assigned skills for
    non-admin users.
    """

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_skill",
            description=(
                "Read a skill's full playbook (SKILL.md) or one of its "
                "reference files. Call this BEFORE attempting a task that "
                "matches a skill listed in the Skills section, then follow "
                "the returned instructions."
            ),
            parameters=[
                ToolParameter(
                    name="name",
                    type="string",
                    description="Skill name exactly as listed in the Skills section.",
                ),
                ToolParameter(
                    name="file",
                    type="string",
                    description=(
                        "Optional file inside the skill package (e.g. "
                        "'references/api.md'). Defaults to SKILL.md."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        name = str(kwargs.get("name") or "").strip()
        rel_path = str(kwargs.get("file") or "SKILL.md").strip() or "SKILL.md"
        if not name:
            raise ValueError("read_skill requires a skill name.")

        services: list[SkillService] = [get_skill_service()]
        try:
            user = get_current_user()
            if not user.is_admin and name in assigned_skill_ids(user.id):
                services.append(
                    SkillService(root=get_admin_path_service().get_workspace_dir() / "skills")
                )
        except Exception:
            logger.debug("read_skill: assigned-skill scope unavailable", exc_info=True)

        for service in services:
            try:
                content = service.read_skill_file(name, rel_path)
            except SkillNotFoundError:
                continue
            except (InvalidSkillNameError, InvalidSkillPathError) as exc:
                return ToolResult(content=f"(read_skill error: {exc})", success=False)
            return ToolResult(
                content=content,
                metadata={"skill": name, "file": rel_path, "char_count": len(content)},
            )
        return ToolResult(
            content=(
                f"(skill not found: {name!r} — use a name exactly as listed in the Skills section)"
            ),
            success=False,
        )


class LoadToolsTool(_PromptHintsMixin, BaseTool):
    """Load deferred (Extended) tools' schemas into the current session.

    The ``_tool_loader`` kwarg is injected server-side by the chat pipeline
    (a per-turn :class:`DeferredToolLoader`); the LLM only supplies
    ``names``.
    """

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="load_tools",
            description=(
                "Load one or more Extended Tools (listed in the Extended "
                "Tools section) so they become callable. Call this BEFORE "
                "using any extended tool; loaded tools stay available for "
                "the rest of the session."
            ),
            parameters=[
                ToolParameter(
                    name="names",
                    type="array",
                    description=(
                        "Exact tool names to load, as listed in the Extended Tools section."
                    ),
                    items={"type": "string"},
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        loader = kwargs.get("_tool_loader")
        names = kwargs.get("names")
        if loader is None:
            return ToolResult(
                content="(load_tools is unavailable in this context)",
                success=False,
            )
        if not isinstance(names, list) or not names:
            raise ValueError("load_tools requires a non-empty `names` array.")
        outcome = loader.load(names)
        parts: list[str] = []
        if outcome["loaded"]:
            parts.append("Loaded (now callable): " + ", ".join(outcome["loaded"]))
        if outcome["already_loaded"]:
            parts.append("Already loaded: " + ", ".join(outcome["already_loaded"]))
        if outcome["unknown"]:
            parts.append(
                "Unknown: "
                + ", ".join(outcome["unknown"])
                + " (use exact names from the Extended Tools section)"
            )
        return ToolResult(
            content="\n".join(parts) or "(nothing to load)",
            success=not outcome["unknown"] or bool(outcome["loaded"]),
            metadata=outcome,
        )
