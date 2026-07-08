"""Built-in tool registry metadata."""

from __future__ import annotations

from deeptutor.capabilities.mastery.tools import MASTERY_TOOL_TYPES
from deeptutor.capabilities.obsidian.tools import OBSIDIAN_TOOL_TYPES
from deeptutor.capabilities.solve.tools import SOLVE_TOOL_TYPES
from deeptutor.capabilities.subagent.tools import SUBAGENT_TOOL_TYPES
from deeptutor.core.tool_protocol import BaseTool
from deeptutor.tools.builtin.context import RAGTool, ReadSourceTool
from deeptutor.tools.builtin.execution import CodeExecutionTool
from deeptutor.tools.builtin.external import CronTool, GithubTool, WebFetchTool
from deeptutor.tools.builtin.interaction import AskUserTool
from deeptutor.tools.builtin.memory import ReadMemoryTool, WriteMemoryTool
from deeptutor.tools.builtin.notes import ListNotebookTool, WriteNoteTool
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
from deeptutor.tools.partner_memory import PartnerMemorizeTool, PartnerReadTool, PartnerSearchTool

BUILTIN_TOOL_TYPES: tuple[type[BaseTool], ...] = (
    BrainstormTool,
    RAGTool,
    WebSearchTool,
    CodeExecutionTool,
    ReasonTool,
    PaperSearchToolWrapper,
    ReadSourceTool,
    ReadMemoryTool,
    WriteMemoryTool,
    ReadSkillTool,
    LoadToolsTool,
    ExecTool,
    WebFetchTool,
    ListNotebookTool,
    WriteNoteTool,
    GithubTool,
    AskUserTool,
    CronTool,
    GeoGebraAnalysisTool,
    ImagegenTool,
    VideogenTool,
    *MASTERY_TOOL_TYPES,
    *SOLVE_TOOL_TYPES,
    *OBSIDIAN_TOOL_TYPES,
    *SUBAGENT_TOOL_TYPES,
    PartnerReadTool,
    PartnerMemorizeTool,
    PartnerSearchTool,
)

COMING_SOON_TOOL_TYPES: tuple[type[BaseTool], ...] = ()

BUILTIN_TOOL_NAMES: tuple[str, ...] = tuple(tool_type().name for tool_type in BUILTIN_TOOL_TYPES)
COMING_SOON_TOOL_NAMES: tuple[str, ...] = tuple(
    tool_type().name for tool_type in COMING_SOON_TOOL_TYPES
)
