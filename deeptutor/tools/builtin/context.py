"""Attached-context built-in tool wrappers."""

from __future__ import annotations

import asyncio
from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.knowledge.manifest import KB_FILES_DEFAULT_LIMIT, KB_FILES_MAX_LIMIT
from deeptutor.tools.builtin.common import _PromptHintsMixin


def _rag_sources(result: dict[str, Any], *, query: str, kb_name: str) -> list[dict[str, Any]]:
    retrieved = [item for item in (result.get("sources") or []) if isinstance(item, dict)]
    if not retrieved:
        return [{"type": "rag", "query": query, "kb_name": kb_name}]
    return [{"type": "rag", "kb_name": kb_name, **item} for item in retrieved]


class RAGTool(_PromptHintsMixin, BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="rag",
            description=(
                "Retrieve relevant passages from one of the knowledge bases the "
                "user attached to this turn. Call once per knowledge base you "
                "want to consult; the system runs them in parallel."
            ),
            parameters=[
                ToolParameter(name="query", type="string", description="Search query."),
                ToolParameter(
                    name="kb_name",
                    type="string",
                    description="Knowledge base to search. Must be one of the attached knowledge bases.",
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        from deeptutor.tools.rag_tool import rag_search

        query = str(kwargs.get("query") or "").strip()
        if not query:
            raise ValueError("RAG query must be a non-empty string.")
        kb_name = str(kwargs.get("kb_name") or "").strip()
        if not kb_name:
            raise ValueError("RAG requires an explicit kb_name.")
        event_sink = kwargs.get("event_sink")
        extra_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key not in {"query", "kb_name", "event_sink"}
        }

        result = await rag_search(
            query=query,
            kb_name=kb_name,
            event_sink=event_sink,
            **extra_kwargs,
        )
        content = result.get("answer") or result.get("content", "")
        return ToolResult(
            content=content,
            sources=_rag_sources(result, query=query, kb_name=kb_name),
            metadata=result,
        )


class KbFilesTool(_PromptHintsMixin, BaseTool):
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="kb_files",
            description=(
                "List the documents stored in one of the knowledge bases attached "
                "to this turn, with the total count. Use this — never rag — for "
                "questions about how many files a knowledge base holds, what its "
                "files are called, or whether a particular file is in it."
            ),
            parameters=[
                ToolParameter(
                    name="kb_name",
                    type="string",
                    description="Knowledge base to inspect. Must be one of the attached knowledge bases.",
                ),
                ToolParameter(
                    name="pattern",
                    type="string",
                    description=(
                        "Optional name filter: a glob such as '*.pdf', or a "
                        "case-insensitive substring. Omit to list everything."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description=(
                        "Optional maximum number of documents to list "
                        f"(default {KB_FILES_DEFAULT_LIMIT}, max {KB_FILES_MAX_LIMIT})."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        from deeptutor.knowledge.manifest import render_manifest_report
        from deeptutor.multi_user.knowledge_access import resolve_kb_manifest

        kb_name = str(kwargs.get("kb_name") or "").strip()
        if not kb_name:
            raise ValueError("kb_files requires an explicit kb_name.")
        pattern = str(kwargs.get("pattern") or "").strip()
        language = str(kwargs.get("language") or "en")

        manifest = await asyncio.to_thread(
            resolve_kb_manifest,
            kb_name,
            limit=_kb_files_limit(kwargs.get("limit")),
            pattern=pattern,
        )
        if manifest is None:
            raise ValueError(f"Knowledge base '{kb_name}' is not accessible.")

        return ToolResult(
            content=render_manifest_report(manifest, language=language),
            metadata={
                "kb_name": manifest.name,
                "total": manifest.total,
                "matched": manifest.matched,
                "listed": [document.name for document in manifest.documents],
                "omitted": manifest.omitted,
                "pattern": manifest.pattern,
                "status": manifest.status,
                "unavailable": manifest.unavailable,
            },
        )


def _kb_files_limit(raw: Any) -> int:
    try:
        requested = int(raw)
    except (TypeError, ValueError):
        return KB_FILES_DEFAULT_LIMIT
    if requested <= 0:
        return KB_FILES_DEFAULT_LIMIT
    return min(requested, KB_FILES_MAX_LIMIT)


class ReadSourceTool(_PromptHintsMixin, BaseTool):
    """Load the full text of an attached Space source by its manifest id.

    The chat pipeline auto-enables this tool whenever a turn has any non-image
    attached source (notebook record, book reference, history session,
    question-bank entry, or document attachment). The per-turn full-text
    payload is carried in ``context.metadata["source_index"]`` as
    ``{source_id: str}`` and injected into the tool call by
    ``_augment_tool_kwargs``. The tool itself stays stateless.
    """

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_source",
            description=(
                "Load the full text of one attached source by id. Use ONLY when "
                "the preview shown in the Attached Sources manifest is "
                "insufficient to answer the user's question. The id must be "
                "copied verbatim from the manifest — do not invent ids. Do not "
                "call this on every source 'just in case'."
            ),
            parameters=[
                ToolParameter(
                    name="source_id",
                    type="string",
                    description=(
                        "The source identifier from the Attached Sources "
                        "manifest. Begins with one of: nb- (notebook record), "
                        "bk- (book reference), hs- (history session), qb- "
                        "(question-bank entry), at- (document attachment)."
                    ),
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        source_id = str(kwargs.get("source_id") or "").strip()
        if not source_id:
            return ToolResult(
                content="Error: source_id is required.",
                success=False,
            )
        source_index = kwargs.get("source_index")
        if not isinstance(source_index, dict) or not source_index:
            return ToolResult(
                content=("Error: no attached sources are available for this turn."),
                success=False,
            )
        full_text = source_index.get(source_id)
        if not full_text:
            available = ", ".join(sorted(source_index.keys()))
            return ToolResult(
                content=(
                    f"Error: unknown source_id {source_id!r}. "
                    f"Valid ids for this turn: {available or '(none)'}."
                ),
                success=False,
            )
        return ToolResult(
            content=str(full_text),
            metadata={"source_id": source_id, "char_count": len(str(full_text))},
        )
