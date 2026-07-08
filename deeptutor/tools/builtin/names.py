"""Built-in tool name constants independent of heavy tool instantiation."""

from __future__ import annotations

USER_TOGGLEABLE_TOOL_NAMES: tuple[str, ...] = (
    "brainstorm",
    "web_search",
    "paper_search",
    "reason",
    "geogebra_analysis",
    "imagegen",
    "videogen",
)

CONFIGURABLE_BUILTIN_TOOL_NAMES: tuple[str, ...] = (
    "rag",
    "code_execution",
    "read_source",
    "read_memory",
    "write_memory",
    "read_skill",
    "list_notebook",
    "write_note",
    "web_fetch",
    "github",
    "exec",
    "load_tools",
    "cron",
    "ask_user",
)

TOOL_ALIASES: dict[str, tuple[str, dict[str, object]]] = {
    "rag_hybrid": ("rag", {"mode": "hybrid"}),
    "rag_naive": ("rag", {"mode": "naive"}),
    "rag_search": ("rag", {}),
    "code_execute": ("code_execution", {}),
    "run_code": ("code_execution", {}),
}
