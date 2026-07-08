"""Planning-stage data shapes and parsing helpers for question generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import logging
from typing import Any

from deeptutor.utils.json_parser import parse_json_response

logger = logging.getLogger(__name__)


class QuestionType(StrEnum):
    """Canonical question-type taxonomy used by planning and validation."""

    CHOICE = "choice"
    CONCEPT = "concept"
    FILL_IN_BLANK = "fill_in_blank"
    SHORT_ANSWER = "short_answer"
    WRITTEN = "written"
    CODING = "coding"


_VALID_QUESTION_TYPES: frozenset[str] = frozenset(qt.value for qt in QuestionType)
_TYPES_WITH_OPTIONS: frozenset[str] = frozenset({QuestionType.CHOICE.value})
_VALID_DIFFICULTIES = ("easy", "medium", "hard")
_CHOICE_KEYS = ("A", "B", "C", "D")
_FILL_IN_BLANK_TOKEN = "____"
_CONCEPT_ANSWERS: frozenset[str] = frozenset({"true", "false"})


@dataclass(frozen=True)
class QuizTemplate:
    question_id: str
    topic: str
    question_type: str
    difficulty: str
    # ``source`` distinguishes templates the planner invents from templates
    # lifted out of an exam paper. ``mimic`` templates carry the original
    # text so the quiz step can shadow / paraphrase rather than invent.
    source: str = "custom"
    reference_question: str | None = None
    reference_answer: str | None = None


@dataclass(frozen=True)
class QuizPlan:
    analysis: str
    templates: list[QuizTemplate] = field(default_factory=list)


@dataclass(frozen=True)
class QuizHistoryEntry:
    """One prior quiz item the learner attempted in this session."""

    question: str
    question_type: str
    correct_answer: str
    user_answer: str
    is_correct: bool | None
    turn_id: str = ""


def _normalize_type_list(raw: list[str] | None) -> list[str]:
    """Coerce a user-supplied type list into the canonical taxonomy."""
    if not raw:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        value = str(item or "").strip().lower()
        if value in _VALID_QUESTION_TYPES and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _normalize_per_type_counts(
    raw: dict[str, int] | None,
    allowed_types: list[str],
) -> dict[str, int]:
    """Coerce per-type quantity targets into the canonical taxonomy."""
    if not raw:
        return {}
    accepted: frozenset[str] = frozenset(allowed_types) if allowed_types else _VALID_QUESTION_TYPES
    out: dict[str, int] = {}
    for key, value in raw.items():
        canonical = str(key or "").strip().lower()
        if canonical not in accepted:
            continue
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count > 0:
            out[canonical] = count
    return out


def _format_allowed_types(allowed_types: list[str]) -> str:
    """Prompt-side rendering of the allowed-types directive."""
    if not allowed_types:
        return "any (planner picks per question)"
    return ", ".join(f"``{t}``" for t in allowed_types)


def _format_per_type_counts(per_type_counts: dict[str, int]) -> str:
    """Prompt-side rendering of the per-type quantity directive."""
    if not per_type_counts:
        return "no per-type targets (planner distributes freely)"
    return ", ".join(f"{t}={n}" for t, n in per_type_counts.items())


def parse_quiz_plan(
    raw: str,
    *,
    requested: int,
    allowed_types: list[str],
    target_difficulty: str,
    logger_instance: Any = None,
) -> QuizPlan:
    """Parse the Phase 2 planner response into normalized quiz templates."""
    data = parse_json_response(raw, logger_instance=logger_instance or logger, fallback={})
    if not isinstance(data, dict) or not data:
        return QuizPlan(analysis="", templates=[])
    analysis = str(data.get("analysis", "") or "")

    raw_items: list[Any]
    if isinstance(data.get("templates"), list):
        raw_items = list(data["templates"])
    elif isinstance(data.get("ideas"), list):
        raw_items = list(data["ideas"])
    else:
        raw_items = []

    allowed_set: frozenset[str] = (
        frozenset(allowed_types) if allowed_types else _VALID_QUESTION_TYPES
    )
    if QuestionType.SHORT_ANSWER.value in allowed_set:
        fallback_type = QuestionType.SHORT_ANSWER.value
    elif allowed_types:
        fallback_type = allowed_types[0]
    else:
        fallback_type = QuestionType.WRITTEN.value

    templates: list[QuizTemplate] = []
    seen_topics: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic") or item.get("concentration") or "").strip()
        if not topic or topic.lower() in seen_topics:
            continue
        seen_topics.add(topic.lower())

        qtype_raw = str(item.get("question_type", "")).strip().lower()
        qtype = qtype_raw if qtype_raw in allowed_set else fallback_type

        diff_raw = str(item.get("difficulty", "")).strip().lower()
        diff = target_difficulty or diff_raw
        diff = diff if diff in _VALID_DIFFICULTIES else "medium"

        templates.append(
            QuizTemplate(
                question_id=f"q_{len(templates) + 1}",
                topic=topic,
                question_type=qtype,
                difficulty=diff,
            )
        )
        if len(templates) >= requested:
            break
    return QuizPlan(analysis=analysis, templates=templates)


__all__ = [
    "QuestionType",
    "QuizHistoryEntry",
    "QuizPlan",
    "QuizTemplate",
    "_CHOICE_KEYS",
    "_CONCEPT_ANSWERS",
    "_FILL_IN_BLANK_TOKEN",
    "_TYPES_WITH_OPTIONS",
    "_VALID_DIFFICULTIES",
    "_VALID_QUESTION_TYPES",
    "_format_allowed_types",
    "_format_per_type_counts",
    "_normalize_per_type_counts",
    "_normalize_type_list",
    "parse_quiz_plan",
]
