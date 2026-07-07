"""Tests for session turn payload helpers."""

from __future__ import annotations

from deeptutor.services.session.payloads import (
    clip_text,
    extract_memory_references,
    sanitize_session_title,
)


class TestClipText:
    def test_short_text_unchanged(self) -> None:
        assert clip_text("hello", limit=100) == "hello"

    def test_long_text_truncated(self) -> None:
        text = "x" * 5000
        result = clip_text(text, limit=100)
        assert len(result) < 200
        assert "[truncated]" in result

    def test_empty_string(self) -> None:
        assert clip_text("") == ""

    def test_none_becomes_empty(self) -> None:
        assert clip_text(None) == ""  # type: ignore[arg-type]


class TestExtractMemoryReferences:
    def test_extracts_valid_memory_files_in_order(self) -> None:
        payload = {"memory_references": ["profile", "summary"]}

        assert extract_memory_references(payload) == ["profile", "summary"]

    def test_filters_unknown_and_duplicate_memory_files(self) -> None:
        payload = {"memory_references": ["summary", "unknown", "summary", "profile"]}

        assert extract_memory_references(payload) == ["summary", "profile"]

    def test_non_list_memory_references_are_ignored(self) -> None:
        assert extract_memory_references({"memory_references": "summary"}) == []


def test_sanitize_session_title_removes_reasoning_block() -> None:
    raw = '<think>需要总结</think>\n标题："AgenticRAG 定义。"'

    assert sanitize_session_title(raw) == "AgenticRAG 定义"


def test_sanitize_session_title_falls_back_when_only_reasoning_remains() -> None:
    raw = "<think>only internal reasoning</think>"

    assert sanitize_session_title(raw) == ""
