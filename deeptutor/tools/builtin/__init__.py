"""Built-in tool implementations and metadata."""

from __future__ import annotations

from deeptutor.tools.builtin.context import RAGTool, ReadSourceTool
from deeptutor.tools.builtin.execution import CodeExecutionTool
from deeptutor.tools.builtin.external import CronTool, GithubTool, WebFetchTool
from deeptutor.tools.builtin.interaction import AskUserTool
from deeptutor.tools.builtin.memory import ReadMemoryTool, WriteMemoryTool
from deeptutor.tools.builtin.notes import ListNotebookTool, WriteNoteTool
from deeptutor.tools.builtin.registry import (
    BUILTIN_TOOL_NAMES,
    BUILTIN_TOOL_TYPES,
    COMING_SOON_TOOL_NAMES,
    COMING_SOON_TOOL_TYPES,
    CONFIGURABLE_BUILTIN_TOOL_NAMES,
    TOOL_ALIASES,
    USER_TOGGLEABLE_TOOL_NAMES,
)
from deeptutor.tools.builtin.search import (
    BrainstormTool,
    PaperSearchToolWrapper,
    ReasonTool,
    WebSearchTool,
)
from deeptutor.tools.builtin.skills import LoadToolsTool, ReadSkillTool
from deeptutor.tools.builtin.vision import GeoGebraAnalysisTool
from deeptutor.tools.exec_tool import ExecTool
from deeptutor.tools.media_gen_tool import ImagegenTool, VideogenTool
from deeptutor.tools.partner_memory import (
    PARTNER_BUILTIN_TOOL_NAMES,
    PartnerMemorizeTool,
    PartnerReadTool,
    PartnerSearchTool,
)

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
