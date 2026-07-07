"""Tests for session follow-up helpers."""

from __future__ import annotations

from deeptutor.services.session.followup import (
    extract_followup_question_context,
    extract_persist_user_message,
    extract_regenerate_flag,
    format_followup_question_context,
)


class TestExtractFollowupQuestionContext:
    def test_none_config(self) -> None:
        assert extract_followup_question_context(None) is None

    def test_missing_key(self) -> None:
        assert extract_followup_question_context({}) is None

    def test_non_dict_value(self) -> None:
        assert extract_followup_question_context({"followup_question_context": "string"}) is None

    def test_missing_question(self) -> None:
        assert (
            extract_followup_question_context({"followup_question_context": {"question_id": "q1"}})
            is None
        )

    def test_valid_context_extracted(self) -> None:
        config = {
            "followup_question_context": {
                "question": "What is AI?",
                "question_id": "q1",
                "question_type": "mcq",
                "options": {"A": "Choice A", "B": "Choice B"},
                "correct_answer": "A",
                "explanation": "AI is...",
                "difficulty": "easy",
                "user_answer": "B",
                "is_correct": False,
            }
        }

        result = extract_followup_question_context(config)

        assert result is not None
        assert result["question"] == "What is AI?"
        assert result["question_id"] == "q1"
        assert result["options"]["A"] == "Choice A"
        assert result["is_correct"] is False
        assert "followup_question_context" not in config

    def test_options_normalized(self) -> None:
        config = {
            "followup_question_context": {
                "question": "Q",
                "options": {"a": "lower", "B": "upper", "c": ""},
            }
        }

        result = extract_followup_question_context(config)

        assert result is not None
        assert "A" in result["options"]
        assert "B" in result["options"]
        assert "C" not in result["options"]


class TestExtractPersistUserMessage:
    def test_default_is_true(self) -> None:
        assert extract_persist_user_message({}) is True

    def test_none_config_is_true(self) -> None:
        assert extract_persist_user_message(None) is True

    def test_false_bool(self) -> None:
        config = {"_persist_user_message": False}
        assert extract_persist_user_message(config) is False
        assert "_persist_user_message" not in config

    def test_false_string(self) -> None:
        assert extract_persist_user_message({"_persist_user_message": "false"}) is False

    def test_zero_string(self) -> None:
        assert extract_persist_user_message({"_persist_user_message": "0"}) is False

    def test_no_string(self) -> None:
        assert extract_persist_user_message({"_persist_user_message": "no"}) is False

    def test_true_string(self) -> None:
        assert extract_persist_user_message({"_persist_user_message": "true"}) is True


class TestExtractRegenerateFlag:
    def test_default_is_false(self) -> None:
        assert extract_regenerate_flag({}) is False

    def test_none_config_is_false(self) -> None:
        assert extract_regenerate_flag(None) is False

    def test_true_bool(self) -> None:
        config = {"_regenerate": True}
        assert extract_regenerate_flag(config) is True
        assert "_regenerate" not in config

    def test_true_string(self) -> None:
        assert extract_regenerate_flag({"_regenerate": "true"}) is True

    def test_one_string(self) -> None:
        assert extract_regenerate_flag({"_regenerate": "1"}) is True

    def test_false_string(self) -> None:
        assert extract_regenerate_flag({"_regenerate": "false"}) is False


class TestFormatFollowupQuestionContext:
    def _base_context(self) -> dict:
        return {
            "question_id": "q1",
            "parent_quiz_session_id": "qs1",
            "question_type": "mcq",
            "difficulty": "medium",
            "concentration": "math",
            "question": "What is 2+2?",
            "options": {"A": "3", "B": "4"},
            "user_answer": "A",
            "is_correct": False,
            "correct_answer": "B",
            "explanation": "2+2=4",
            "knowledge_context": "",
        }

    def test_english_format(self) -> None:
        text = format_followup_question_context(self._base_context(), language="en")
        assert "You are handling follow-up questions" in text
        assert "What is 2+2?" in text
        assert "A. 3" in text
        assert "B. 4" in text
        assert "incorrect" in text

    def test_chinese_format(self) -> None:
        text = format_followup_question_context(self._base_context(), language="zh")
        assert "你正在处理一道测验题的后续追问" in text
        assert "What is 2+2?" in text

    def test_correct_answer_shows_correct(self) -> None:
        ctx = self._base_context()
        ctx["is_correct"] = True
        text = format_followup_question_context(ctx, language="en")
        assert "correct" in text.lower()

    def test_unknown_correctness(self) -> None:
        ctx = self._base_context()
        ctx["is_correct"] = None
        text = format_followup_question_context(ctx, language="en")
        assert "unknown" in text.lower()

    def test_knowledge_context_included(self) -> None:
        ctx = self._base_context()
        ctx["knowledge_context"] = "Some KB knowledge"
        text = format_followup_question_context(ctx, language="en")
        assert "Some KB knowledge" in text

    def test_no_options(self) -> None:
        ctx = self._base_context()
        ctx["options"] = {}
        text = format_followup_question_context(ctx, language="en")
        assert "Options:" not in text
