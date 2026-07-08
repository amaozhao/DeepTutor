"""Tests for question planning-stage helpers."""

from __future__ import annotations

import json

from deeptutor.agents.question.planning import (
    QuizPlan,
    _format_allowed_types,
    _format_per_type_counts,
    _normalize_per_type_counts,
    _normalize_type_list,
    parse_quiz_plan,
)


def test_parse_quiz_plan_happy_path() -> None:
    raw = json.dumps(
        {
            "analysis": "mix of recall + applied",
            "templates": [
                {"topic": "Definition of X", "question_type": "choice", "difficulty": "easy"},
                {"topic": "Apply X to Y", "question_type": "written", "difficulty": "medium"},
            ],
        }
    )
    plan = parse_quiz_plan(raw, requested=2, allowed_types=[], target_difficulty="")
    assert plan.analysis == "mix of recall + applied"
    assert [t.topic for t in plan.templates] == ["Definition of X", "Apply X to Y"]
    assert [t.question_id for t in plan.templates] == ["q_1", "q_2"]
    assert plan.templates[0].question_type == "choice"
    assert plan.templates[1].difficulty == "medium"


def test_parse_quiz_plan_dedupes_topics_case_insensitive() -> None:
    raw = json.dumps(
        {
            "templates": [
                {"topic": "Matrix Multiplication", "question_type": "written"},
                {"topic": "matrix multiplication", "question_type": "choice"},
                {"topic": "Eigenvalues", "question_type": "written"},
            ]
        }
    )
    plan = parse_quiz_plan(raw, requested=3, allowed_types=[], target_difficulty="")
    assert len(plan.templates) == 2
    assert plan.templates[0].topic == "Matrix Multiplication"
    assert plan.templates[1].topic == "Eigenvalues"


def test_parse_quiz_plan_respects_user_specified_type_and_difficulty() -> None:
    raw = json.dumps(
        {
            "templates": [
                {"topic": "T1", "question_type": "choice", "difficulty": "easy"},
                {"topic": "T2", "question_type": "written", "difficulty": "hard"},
            ]
        }
    )
    plan = parse_quiz_plan(raw, requested=2, allowed_types=["coding"], target_difficulty="medium")
    assert all(t.question_type == "coding" for t in plan.templates)
    assert all(t.difficulty == "medium" for t in plan.templates)


def test_parse_quiz_plan_invalid_json_returns_empty() -> None:
    plan = parse_quiz_plan("not even json", requested=3, allowed_types=[], target_difficulty="")
    assert isinstance(plan, QuizPlan)
    assert plan.templates == []


def test_parse_quiz_plan_truncates_to_requested() -> None:
    raw = json.dumps(
        {
            "templates": [
                {"topic": f"T{i}", "question_type": "written", "difficulty": "easy"}
                for i in range(5)
            ]
        }
    )
    plan = parse_quiz_plan(raw, requested=2, allowed_types=[], target_difficulty="")
    assert len(plan.templates) == 2


def test_parse_quiz_plan_accepts_ideas_alias() -> None:
    raw = json.dumps(
        {
            "analysis": "fallback schema",
            "ideas": [
                {"concentration": "Linear independence", "question_type": "short_answer"},
            ],
        }
    )
    plan = parse_quiz_plan(raw, requested=1, allowed_types=[], target_difficulty="")
    assert plan.analysis == "fallback schema"
    assert plan.templates[0].topic == "Linear independence"
    assert plan.templates[0].question_type == "short_answer"


def test_planning_directives_are_normalized_for_prompting() -> None:
    allowed = _normalize_type_list(["WRITTEN", "bad", "choice", "written"])
    counts = _normalize_per_type_counts({"written": "2", "choice": 1, "coding": 3}, allowed)

    assert allowed == ["written", "choice"]
    assert counts == {"written": 2, "choice": 1}
    assert _format_allowed_types(allowed) == "``written``, ``choice``"
    assert _format_per_type_counts(counts) == "written=2, choice=1"
