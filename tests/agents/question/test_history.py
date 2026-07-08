"""Tests for question quiz-history loading."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_sqlite_store(tmp_path: Path):
    """Spin up an isolated SQLite session store for history loading."""
    SQLiteSessionStore = __import__(
        "deeptutor.services.session.sqlite_store", fromlist=["SQLiteSessionStore"]
    ).SQLiteSessionStore

    store = SQLiteSessionStore(db_path=tmp_path / "session.db")
    with patch(
        "deeptutor.services.session.sqlite_store.get_sqlite_session_store",
        return_value=store,
    ):
        yield store


def test_history_loader_returns_session_scoped_entries(tmp_sqlite_store) -> None:
    load_session_quiz_history = __import__(
        "deeptutor.agents.question.history", fromlist=["load_session_quiz_history"]
    ).load_session_quiz_history

    store = tmp_sqlite_store

    async def setup() -> None:
        await store.create_session(session_id="s1", title="quiz session")
        await store.create_session(session_id="s2", title="other session")
        await store.upsert_notebook_entries(
            "s1",
            [
                {
                    "turn_id": "t1",
                    "question_id": "q_1",
                    "question": "What is 2+2?",
                    "question_type": "written",
                    "options": {},
                    "correct_answer": "4",
                    "explanation": "addition",
                    "difficulty": "easy",
                    "user_answer": "4",
                    "is_correct": True,
                },
                {
                    "turn_id": "t1",
                    "question_id": "q_2",
                    "question": "What is 3*3?",
                    "question_type": "written",
                    "options": {},
                    "correct_answer": "9",
                    "explanation": "multiplication",
                    "difficulty": "easy",
                    "user_answer": "8",
                    "is_correct": False,
                },
                {
                    "turn_id": "t2",
                    "question_id": "q_3",
                    "question": "What is e^0?",
                    "question_type": "written",
                    "options": {},
                    "correct_answer": "1",
                    "explanation": "exp",
                    "difficulty": "medium",
                    "user_answer": "",
                    "is_correct": False,
                },
            ],
        )
        await store.upsert_notebook_entries(
            "s2",
            [
                {
                    "turn_id": "t99",
                    "question_id": "q_1",
                    "question": "OTHER SESSION should not leak",
                    "question_type": "written",
                    "correct_answer": "x",
                    "explanation": "x",
                    "user_answer": "x",
                    "is_correct": True,
                }
            ],
        )

    asyncio.run(setup())

    entries = asyncio.run(load_session_quiz_history("s1"))
    questions = [e.question for e in entries]
    assert "OTHER SESSION should not leak" not in questions
    assert questions == ["What is 2+2?", "What is 3*3?", "What is e^0?"]
    assert entries[0].is_correct is True
    assert entries[1].is_correct is False
    assert entries[2].is_correct is None
    assert entries[2].user_answer == ""


def test_history_loader_returns_empty_for_unknown_session(tmp_sqlite_store) -> None:
    load_session_quiz_history = __import__(
        "deeptutor.agents.question.history", fromlist=["load_session_quiz_history"]
    ).load_session_quiz_history

    entries = asyncio.run(load_session_quiz_history(""))
    assert entries == []
    entries = asyncio.run(load_session_quiz_history("does-not-exist"))
    assert entries == []
