"""Shared helpers for built-in tool wrappers."""

from __future__ import annotations

from deeptutor.tools.prompting import load_prompt_hints


class _PromptHintsMixin:
    """Shared prompt-hint loader for built-in tools."""

    def get_prompt_hints(self, language: str = "en"):
        return load_prompt_hints(self.name, language=language)
