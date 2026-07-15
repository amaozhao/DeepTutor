"""Built-in tool implementations and metadata."""

from __future__ import annotations

import importlib

__all__ = [
    "BUILTIN_TOOL_NAMES",
    "BUILTIN_TOOL_TYPES",
    "COMING_SOON_TOOL_NAMES",
    "COMING_SOON_TOOL_TYPES",
    "CONFIGURABLE_BUILTIN_TOOL_NAMES",
    "PARTNER_BUILTIN_TOOL_NAMES",
    "TOOL_ALIASES",
    "USER_TOGGLEABLE_TOOL_NAMES",
    "AskUserTool",
    "BrainstormTool",
    "CodeExecutionTool",
    "ExecTool",
    "GeoGebraAnalysisTool",
    "GithubTool",
    "ImagegenTool",
    "VideogenTool",
    "ListNotebookTool",
    "PaperSearchToolWrapper",
    "PartnerMemorizeTool",
    "PartnerReadTool",
    "PartnerSearchTool",
    "RAGTool",
    "LoadToolsTool",
    "ReadMemoryTool",
    "ReadSkillTool",
    "ReadSourceTool",
    "ReasonTool",
    "WebFetchTool",
    "WebSearchTool",
    "WriteMemoryTool",
    "WriteNoteTool",
]


def __getattr__(name: str):
    if name in {
        "BUILTIN_TOOL_NAMES",
        "BUILTIN_TOOL_TYPES",
        "COMING_SOON_TOOL_NAMES",
        "COMING_SOON_TOOL_TYPES",
    }:
        module = importlib.import_module(f"{__name__}.registry")
        return getattr(module, name)
    if name in {
        "CONFIGURABLE_BUILTIN_TOOL_NAMES",
        "TOOL_ALIASES",
        "USER_TOGGLEABLE_TOOL_NAMES",
    }:
        module = importlib.import_module(f"{__name__}.names")
        return getattr(module, name)
    if name in {"RAGTool", "ReadSourceTool"}:
        module = importlib.import_module(f"{__name__}.context")
        return getattr(module, name)
    if name == "CodeExecutionTool":
        module = importlib.import_module(f"{__name__}.execution")
        return module.CodeExecutionTool
    if name in {"CronTool", "GithubTool", "WebFetchTool"}:
        module = importlib.import_module(f"{__name__}.external")
        return getattr(module, name)
    if name == "AskUserTool":
        module = importlib.import_module(f"{__name__}.interaction")
        return module.AskUserTool
    if name in {"ReadMemoryTool", "WriteMemoryTool"}:
        module = importlib.import_module(f"{__name__}.memory")
        return getattr(module, name)
    if name in {"ListNotebookTool", "WriteNoteTool"}:
        module = importlib.import_module(f"{__name__}.notes")
        return getattr(module, name)
    if name in {"BrainstormTool", "PaperSearchToolWrapper", "ReasonTool", "WebSearchTool"}:
        module = importlib.import_module(f"{__name__}.search")
        return getattr(module, name)
    if name in {"LoadToolsTool", "ReadSkillTool"}:
        module = importlib.import_module(f"{__name__}.skills")
        return getattr(module, name)
    if name == "GeoGebraAnalysisTool":
        module = importlib.import_module(f"{__name__}.vision")
        return module.GeoGebraAnalysisTool
    if name == "ExecTool":
        module = importlib.import_module("deeptutor.tools.exec_tool")
        return module.ExecTool
    if name in {"ImagegenTool", "VideogenTool"}:
        module = importlib.import_module("deeptutor.tools.media_gen_tool")
        return getattr(module, name)
    if name in {
        "PARTNER_BUILTIN_TOOL_NAMES",
        "PartnerMemorizeTool",
        "PartnerReadTool",
        "PartnerSearchTool",
    }:
        module = importlib.import_module("deeptutor.tools.partner_memory")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
