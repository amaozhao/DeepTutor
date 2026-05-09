from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.agents.question.coordinator import AgentCoordinator
from deeptutor.services.path_service import get_path_service


@pytest.mark.asyncio
async def test_parse_exam_to_templates_resolves_relative_dir_under_question_workspace(
    tmp_path: Path,
    as_multi_user,
) -> None:
    coordinator = AgentCoordinator(output_dir=str(tmp_path / "output"))

    with as_multi_user("user_alpha"):
        parsed_dir = get_path_service().get_question_dir() / "2211asm1"
        parsed_dir.mkdir(parents=True)
        question_file = parsed_dir / "exam_questions.json"
        question_file.write_text(
            json.dumps(
                {
                    "questions": [
                        {
                            "question_number": "1",
                            "question_text": "Differentiate x^2.",
                            "answer": "2x",
                            "question_type": "written",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        templates, trace = await coordinator._parse_exam_to_templates(
            exam_paper_path="2211asm1",
            max_questions=1,
            paper_mode="parsed",
        )

    assert trace["paper_dir"] == str(parsed_dir.resolve())
    assert trace["question_file"] == str(question_file.resolve())
    assert templates[0].reference_question == "Differentiate x^2."
