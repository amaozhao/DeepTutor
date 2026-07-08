"""Pure payload helpers for turn runtime."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from deeptutor.services.llm.utils import clean_thinking_tags
from deeptutor.services.model_selection import LLMSelection

MemoryReference = Literal["recent", "profile", "scope", "preferences", "summary"]


def clip_text(value: str, limit: int = 4000) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


_TITLE_QUOTE_PAIRS: tuple[tuple[str, str], ...] = (
    ('"', '"'),
    ("'", "'"),
    ("“", "”"),
    ("‘", "’"),
    ("「", "」"),
    ("『", "』"),
    ("`", "`"),
)
_TITLE_PREFIXES: tuple[str, ...] = (
    "Title:",
    "title:",
    "TITLE:",
    "Title-",
    "标题：",
    "标题:",
    "对话标题：",
    "对话标题:",
)
_TITLE_TRAILING_PUNCT = ".。!！?？,，;；、 \t"


def sanitize_session_title(raw: str) -> str:
    """Trim common LLM noise from short generated titles."""
    text = clean_thinking_tags(raw or "").strip()
    if not text:
        return ""
    text = text.splitlines()[0].strip()
    for _ in range(8):
        prev = text
        text = text.lstrip("*_#- \t").rstrip("*_ \t")
        for prefix in _TITLE_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
                break
        for opener, closer in _TITLE_QUOTE_PAIRS:
            if len(text) >= 2 and text.startswith(opener) and text.endswith(closer):
                text = text[len(opener) : len(text) - len(closer)].strip()
                break
        text = text.rstrip(_TITLE_TRAILING_PUNCT)
        if text == prev:
            break
    return text[:80]


def extract_memory_references(payload: dict[str, Any]) -> list[MemoryReference]:
    """Return the L3 slot names the client opted in for this turn."""
    refs = payload.get("memory_references", []) or []
    if not isinstance(refs, list):
        return []
    allowed = {"recent", "profile", "scope", "preferences", "summary"}
    out: list[MemoryReference] = []
    for item in refs:
        if item in allowed and item not in out:
            out.append(item)
    return out


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def llm_selection_dict(value: Any) -> dict[str, str] | None:
    selection = LLMSelection.from_payload(value)
    return selection.to_dict() if selection else None


def request_snapshot_metadata(
    *,
    payload: dict[str, Any],
    content: str,
    capability: str,
    config: dict[str, Any],
    attachments: list[dict[str, Any]],
    notebook_references: list[Any],
    history_references: list[Any],
    question_notebook_references: list[Any],
    book_references: list[Any],
    persona: str,
    memory_references: Sequence[str],
    llm_selection: dict[str, str] | None,
) -> dict[str, Any]:
    """Persist the front-end context chips with the user message."""
    snapshot: dict[str, Any] = {
        "content": content,
        "capability": capability,
        "enabledTools": string_list(payload.get("tools")),
        "knowledgeBases": string_list(payload.get("knowledge_bases")),
        "language": str(payload.get("language", "en") or "en"),
    }
    if attachments:
        snapshot["attachments"] = attachments
    if config:
        snapshot["config"] = dict(config)
    if notebook_references:
        snapshot["notebookReferences"] = notebook_references
    if history_references:
        snapshot["historyReferences"] = history_references
    if question_notebook_references:
        snapshot["questionNotebookReferences"] = question_notebook_references
    if book_references:
        snapshot["bookReferences"] = book_references
    if persona:
        snapshot["persona"] = persona
    if memory_references:
        snapshot["memoryReferences"] = memory_references
    if llm_selection:
        snapshot["llmSelection"] = llm_selection
    return {"request_snapshot": snapshot}
