"""External-service built-in tool wrappers."""

from __future__ import annotations

from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.tools.builtin.common import _PromptHintsMixin
from deeptutor.tools.cron_tool import run_cron_action
from deeptutor.tools.github_query import run_github_query
from deeptutor.tools.web_fetch import (
    DEFAULT_MAX_CHARS,
    fetch_url_as_markdown,
)


class WebFetchTool(_PromptHintsMixin, BaseTool):
    """Fetch a specific URL and return readable markdown.

    The actual fetch / extract / safety logic lives in
    ``deeptutor.tools.web_fetch`` so this wrapper stays free of network
    code — easier to unit-test the BaseTool boilerplate without spinning
    up an httpx mock.
    """

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_fetch",
            description=(
                "Fetch a specific URL and extract readable content as "
                "markdown. Use this when the user shares a specific link; "
                "use `web_search` for general topic searches."
            ),
            parameters=[
                ToolParameter(
                    name="url",
                    type="string",
                    description="Full http:// or https:// URL.",
                ),
                ToolParameter(
                    name="max_chars",
                    type="integer",
                    description="Cap on the extracted text length; defaults to 50000.",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        url = str(kwargs.get("url") or "").strip()
        if not url:
            return ToolResult(content="Error: url is required.", success=False)
        try:
            max_chars = int(kwargs.get("max_chars") or DEFAULT_MAX_CHARS)
        except (TypeError, ValueError):
            max_chars = DEFAULT_MAX_CHARS
        outcome = await fetch_url_as_markdown(url, max_chars=max_chars)
        if not outcome.ok:
            return ToolResult(
                content=outcome.error or "Fetch failed.",
                success=False,
                metadata={"url": url},
            )
        return ToolResult(
            content=outcome.markdown,
            sources=[{"type": "web", "url": outcome.url, "title": outcome.title}],
            metadata={
                "url": outcome.url,
                "title": outcome.title,
                "char_count": len(outcome.markdown),
                "truncated": outcome.truncated,
            },
        )


class GithubTool(_PromptHintsMixin, BaseTool):
    """Read-only GitHub queries via `gh`. Always auto-mounted; the
    underlying call gracefully reports "gh unavailable" when the CLI
    isn't installed on the server."""

    _ALLOWED_QUERY_TYPES = ("pr", "issue", "run", "repo", "api")

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="github",
            description=(
                "Read-only queries against GitHub PRs / issues / repos / "
                "CI runs via the gh CLI. This tool cannot write — no "
                "comments, no closes, no merges."
            ),
            parameters=[
                ToolParameter(
                    name="query_type",
                    type="string",
                    description=("One of 'pr', 'issue', 'run', 'repo', 'api'."),
                    enum=list(_ALLOWED_QUERY_TYPES := ("pr", "issue", "run", "repo", "api")),
                ),
                ToolParameter(
                    name="target",
                    type="string",
                    description=(
                        "owner/repo[#number] or full URL for pr/issue; "
                        "owner/repo for run/repo; gh-api relative path "
                        "for api."
                    ),
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        outcome = await run_github_query(
            query_type=str(kwargs.get("query_type") or ""),
            target=str(kwargs.get("target") or ""),
        )
        if not outcome.ok:
            return ToolResult(
                content=outcome.error,
                success=False,
                metadata={"query_type": outcome.query_type, "target": outcome.target},
            )
        return ToolResult(
            content=outcome.output,
            sources=[
                {
                    "type": "github",
                    "query_type": outcome.query_type,
                    "target": outcome.target,
                }
            ],
            metadata={
                "query_type": outcome.query_type,
                "target": outcome.target,
            },
        )


class CronTool(_PromptHintsMixin, BaseTool):
    """Schedule, list, and cancel timed tasks for the current conversation.

    Mirrors nanobot's cron tool. Jobs belong to the conversation that
    created them: a chat job re-runs as a turn appended to that session; a
    partner job is injected into the partner's message bus so the reply
    rides the original IM channel. The owner routing context arrives via
    the pipeline-injected ``_cron_owner`` kwarg — never from the model.
    """

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="cron",
            description=(
                "Schedule a task to run later, list scheduled tasks, or "
                "cancel one. When a task is due, its message is executed "
                "as a new instruction in this same conversation and the "
                "result is delivered here. Use action='schedule' with "
                "`message` plus EXACTLY ONE of: `at` (ISO 8601 time, one-"
                "shot), `every_seconds` (repeating interval, min 30), or "
                "`cron_expr` (cron expression like '0 9 * * *', optional "
                "`tz` IANA timezone). Use action='list' to see this "
                "conversation's tasks and action='cancel' with `job_id` "
                "to remove one. Times without a timezone are server-local."
            ),
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="What to do.",
                    required=True,
                    enum=["schedule", "list", "cancel"],
                ),
                ToolParameter(
                    name="message",
                    type="string",
                    description=(
                        "schedule: the instruction to execute when due — "
                        "write it as a complete, self-contained request."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="name",
                    type="string",
                    description="schedule: short human-readable task name.",
                    required=False,
                ),
                ToolParameter(
                    name="at",
                    type="string",
                    description=(
                        "schedule (one-shot): ISO 8601 time, e.g. "
                        "'2026-06-12T09:00' or with offset '…+08:00'."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="every_seconds",
                    type="integer",
                    description="schedule (repeating): interval in seconds, minimum 30.",
                    required=False,
                ),
                ToolParameter(
                    name="cron_expr",
                    type="string",
                    description="schedule (cron): 5-field cron expression, e.g. '0 9 * * 1-5'.",
                    required=False,
                ),
                ToolParameter(
                    name="tz",
                    type="string",
                    description="schedule (cron): IANA timezone for cron_expr, e.g. 'Asia/Hong_Kong'.",
                    required=False,
                ),
                ToolParameter(
                    name="delete_after_run",
                    type="boolean",
                    description="schedule: remove the task after one run (default true for 'at').",
                    required=False,
                ),
                ToolParameter(
                    name="job_id",
                    type="string",
                    description="cancel: id of the task to remove (from action='list').",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        outcome = run_cron_action(kwargs)
        return ToolResult(content=outcome.text, success=outcome.ok, metadata=outcome.meta)
