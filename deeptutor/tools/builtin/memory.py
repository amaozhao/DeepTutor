"""Memory built-in tool wrappers."""

from __future__ import annotations

from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.services.memory import get_memory_store
from deeptutor.services.memory.trace import TraceEvent
from deeptutor.tools.builtin.common import _PromptHintsMixin


class ReadMemoryTool(_PromptHintsMixin, BaseTool):
    """Read the current user's L3 cross-surface Memory.

    Returns the concatenation of the four L3 markdown documents
    (recent / profile / scope / preferences). Multi-user-safe: paths
    resolve to the active user via the runtime's ContextVars.
    """

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_memory",
            description=(
                "Read the user's persistent memory: recent learning summary, "
                "user profile, knowledge scope, and explicit preferences. "
                "Use to personalise tone, depth, and examples — not on "
                "every turn, not for purely factual questions."
            ),
            parameters=[],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        text = get_memory_store().read_l3_concat()
        return ToolResult(
            content=text,
            metadata={"char_count": len(text)},
        )


class WriteMemoryTool(_PromptHintsMixin, BaseTool):
    """Persist an explicit user preference into the L3 ``preferences.md``.

    The only chat-mode write into memory. Other memory docs are updated
    through the Memory workbench by the user manually. This tool is for
    moments when the user *explicitly* states a preference — speak it
    back to them only if natural, then call this with the substance.
    """

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_memory",
            description=(
                "Save an explicit user preference (writing style, language "
                "choice, depth, format) to long-term memory. Call ONLY when "
                "the user clearly states a preference — never speculate."
            ),
            parameters=[
                ToolParameter(
                    name="op",
                    type="string",
                    description="`add` for a new preference, `edit` to revise an existing one.",
                    enum=["add", "edit"],
                    required=True,
                ),
                ToolParameter(
                    name="text",
                    type="string",
                    description="The preference, in the user's own words where possible. ≤ 240 chars.",
                    required=True,
                ),
                ToolParameter(
                    name="target_id",
                    type="string",
                    description="Existing entry id (form `m_xxx`). Required for `edit`.",
                    required=False,
                ),
                ToolParameter(
                    name="reason",
                    type="string",
                    description="Optional one-line note shown in the Memory workbench.",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        op = str(kwargs.get("op") or "").strip().lower()
        text = str(kwargs.get("text") or "").strip()
        target_id = kwargs.get("target_id")
        reason = kwargs.get("reason")

        if op not in {"add", "edit"}:
            return ToolResult(
                content=f"Error: op must be 'add' or 'edit', got {op!r}.", success=False
            )
        if not text:
            return ToolResult(
                content="Error: text is required and must be non-empty.", success=False
            )

        store = get_memory_store()
        # Emit an L1 trace so the preference's footnote points at a real event.
        event = TraceEvent.new(
            "chat",
            "preference_stated",
            {"op": op, "text": text, "target_id": target_id, "reason": reason},
        )
        await store.emit(event)

        report = await store.write_preference(
            op=op,  # type: ignore[arg-type]
            text=text,
            target_id=str(target_id).strip() if target_id else None,
            reason=str(reason).strip() if reason else None,
            trace_id=event.id,
        )
        if not report.accepted:
            return ToolResult(
                content=f"write_memory rejected: {report.reason}",
                success=False,
                metadata={"op": op},
            )
        result = report.results[0] if report.results else None
        entry_id = result.entry_id if result else None
        deduplicated = result is not None and result.detail == "duplicate"
        return ToolResult(
            content=(
                f"preference already saved (entry={entry_id or target_id}); skipped duplicate."
                if deduplicated
                else f"preference {op}ed (entry={entry_id or target_id})."
            ),
            metadata={
                "op": op,
                "entry_id": entry_id or target_id,
                "deduplicated": deduplicated,
            },
        )
