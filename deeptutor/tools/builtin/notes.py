"""Notebook built-in tool wrappers."""

from __future__ import annotations

from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.tools.builtin.common import _PromptHintsMixin
from deeptutor.tools.list_notebook import list_notebooks_or_records
from deeptutor.tools.write_note import write_note


class ListNotebookTool(_PromptHintsMixin, BaseTool):
    """List the user's notebooks, or list the records inside one notebook.

    Two-mode discovery tool. Auto-mounted by the chat pipeline iff the
    user has at least one notebook. The tool itself is stateless; the
    chat pipeline supplies no extra context — list calls go straight
    against the per-user notebook manager.
    """

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_notebook",
            description=(
                "Discover the user's notebooks and the records inside "
                "them. Call with no arguments to list every notebook "
                "the user owns (id + name + record count). Call with a "
                "specific `notebook_id` to drill in and list its "
                "records (record_id + title + summary + timestamp). "
                "Use this BEFORE `write_note` in edit mode so you have "
                "valid record ids."
            ),
            parameters=[
                ToolParameter(
                    name="notebook_id",
                    type="string",
                    description=(
                        "Optional. When omitted, returns the notebook "
                        "index. When supplied, returns the records in "
                        "that notebook. Must be a valid id from the "
                        "notebook index — do not invent ids."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        outcome = list_notebooks_or_records(
            notebook_id=str(kwargs.get("notebook_id") or ""),
        )
        if not outcome.ok:
            return ToolResult(content=outcome.error, success=False)
        return ToolResult(
            content=outcome.text,
            metadata=outcome.summary or {},
        )


class WriteNoteTool(_PromptHintsMixin, BaseTool):
    """Create OR edit a notebook record from the chat agent.

    Two modes mirror what a human sees in the notebook UI:

    * ``append`` — create a new record in a notebook (the model picks
      a title; the body defaults to the actual chat transcript built
      from injected conversation history, or to an agent-authored
      markdown body if ``content`` is explicitly provided).
    * ``edit`` — patch an existing record's title / body / summary.
      Requires a known ``record_id`` (obtained via ``list_notebook``).

    Auto-mounted only when the user has at least one notebook. The
    pipeline injects ``conversation_history`` + ``current_user_message``
    so the model never has to fabricate the saved chat.
    """

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_note",
            description=(
                "Save or edit a notebook record. mode='append' creates "
                "a NEW record (default body = the actual recent chat "
                "transcript built by the tool; pass `content` instead "
                "to save an agent-authored markdown body). "
                "mode='edit' patches an existing record's title / body "
                "/ summary — `record_id` is required (call `list_notebook` "
                "first to discover valid ids)."
            ),
            parameters=[
                ToolParameter(
                    name="mode",
                    type="string",
                    description="'append' (new record) or 'edit' (patch existing).",
                    enum=["append", "edit"],
                ),
                ToolParameter(
                    name="notebook_id",
                    type="string",
                    description=(
                        "Id of the target notebook from the schema enum (do not invent ids)."
                    ),
                ),
                ToolParameter(
                    name="record_id",
                    type="string",
                    description=("Required for mode='edit'. Discover with `list_notebook` first."),
                    required=False,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description=(
                        "For append: required, short descriptive title. "
                        "For edit: optional new title (leave empty to "
                        "keep the existing one)."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description=(
                        "For append: optional agent-authored markdown body "
                        "(when omitted the tool inserts the real Q&A "
                        "transcript itself, the recommended default). "
                        "For edit: replacement body (leave empty to keep "
                        "the existing body)."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="turns_to_include",
                    type="string",
                    description=(
                        "Append mode only. Number of recent user+assistant "
                        "turns to render into the transcript body. Pass an "
                        "integer as a string (e.g. '3') or 'all' to include "
                        "every turn currently in scope. Ignored when "
                        "`content` is provided. Default '3'."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="note",
                    type="string",
                    description=(
                        "Optional one-paragraph commentary. In append "
                        "mode it's prepended above the transcript; in "
                        "edit mode it replaces the record's summary."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        outcome = write_note(
            mode=str(kwargs.get("mode") or ""),
            notebook_id=str(kwargs.get("notebook_id") or ""),
            record_id=str(kwargs.get("record_id") or ""),
            title=str(kwargs.get("title") or ""),
            content=str(kwargs.get("content") or ""),
            turns_to_include=kwargs.get("turns_to_include") or 3,
            note=str(kwargs.get("note") or ""),
            conversation_history=kwargs.get("conversation_history") or [],
            current_user_message=str(kwargs.get("current_user_message") or ""),
        )
        if not outcome.ok:
            return ToolResult(content=outcome.error, success=False)
        action = "Saved new record" if outcome.mode == "append" else "Updated record"
        return ToolResult(
            content=(
                f"{action} in notebook {outcome.notebook_name!r} (record id: {outcome.record_id})."
            ),
            metadata={
                "mode": outcome.mode,
                "record_id": outcome.record_id,
                "notebook_id": outcome.notebook_id,
                "notebook_name": outcome.notebook_name,
            },
        )
