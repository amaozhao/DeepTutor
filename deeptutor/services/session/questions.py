"""Question-bank entry rendering shared by session helpers."""

from __future__ import annotations

from typing import Any

from deeptutor.services.session.payloads import clip_text as _clip_text


def format_question_bank_entry(entry: dict[str, Any]) -> str:
    """Render a single Question Bank entry as a structured Markdown block."""
    lines: list[str] = []
    title = str(entry.get("session_title", "") or "Untitled session")
    difficulty = str(entry.get("difficulty", "") or "").strip()
    qtype = str(entry.get("question_type", "") or "").strip()
    is_correct = bool(entry.get("is_correct"))

    badges: list[str] = []
    if qtype:
        badges.append(qtype)
    if difficulty:
        badges.append(difficulty)
    badges.append("correct" if is_correct else "incorrect")
    badge_text = " · ".join(badges)

    lines.append(f"### Question (from {title}) [{badge_text}]")
    lines.append(_clip_text(str(entry.get("question", "") or ""), limit=2000))

    options = entry.get("options") or {}
    if isinstance(options, dict) and options:
        lines.append("")
        lines.append("**Options:**")
        for key in sorted(options.keys()):
            lines.append(f"- {key}. {options[key]}")

    user_answer = str(entry.get("user_answer", "") or "").strip()
    correct_answer = str(entry.get("correct_answer", "") or "").strip()
    if user_answer:
        lines.append("")
        lines.append(f"**User's Answer:** {_clip_text(user_answer, limit=1000)}")
    if correct_answer:
        lines.append(f"**Reference Answer:** {_clip_text(correct_answer, limit=1500)}")

    explanation = str(entry.get("explanation", "") or "").strip()
    if explanation:
        lines.append("")
        lines.append("**Explanation:**")
        lines.append(_clip_text(explanation, limit=2000))

    return "\n".join(lines)


__all__ = ["format_question_bank_entry"]
