"""Services-layer provider runtime used by both llm.factory and TutorBot."""

from __future__ import annotations

import importlib

from .base import GenerationSettings, LLMProvider, LLMResponse, ToolCallRequest

__all__ = [
    "AnthropicProvider",
    "AzureOpenAIProvider",
    "GenerationSettings",
    "GitHubCopilotProvider",
    "LLMProvider",
    "LLMResponse",
    "OpenAICodexProvider",
    "OpenAICompatProvider",
    "ToolCallRequest",
]


def __getattr__(name: str):
    if name == "AnthropicProvider":
        return importlib.import_module(f"{__name__}.anthropic_provider").AnthropicProvider
    if name == "AzureOpenAIProvider":
        return importlib.import_module(f"{__name__}.azure_openai_provider").AzureOpenAIProvider
    if name == "GitHubCopilotProvider":
        return importlib.import_module(f"{__name__}.github_copilot_provider").GitHubCopilotProvider
    if name == "OpenAICodexProvider":
        return importlib.import_module(f"{__name__}.openai_codex_provider").OpenAICodexProvider
    if name == "OpenAICompatProvider":
        return importlib.import_module(f"{__name__}.openai_compat_provider").OpenAICompatProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
