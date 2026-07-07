"""Question follow-up helpers for turn runtime."""

from __future__ import annotations

from typing import Any

from deeptutor.services.session.payloads import clip_text


def normalize_filename_list(raw: dict[str, Any]) -> list[str]:
    """Coalesce legacy single-filename and modern multi-filename inputs."""
    candidates: list[Any] = []
    plural = raw.get("user_answer_image_filenames")
    if isinstance(plural, list):
        candidates.extend(plural)
    elif isinstance(plural, str):
        candidates.append(plural)
    legacy = raw.get("user_answer_image_filename")
    if isinstance(legacy, str) and legacy.strip():
        candidates.append(legacy)
    cleaned: list[str] = []
    for item in candidates:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if name:
            cleaned.append(name)
    return cleaned


def extract_followup_question_context(
    config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    raw = config.pop("followup_question_context", None)
    if not isinstance(raw, dict):
        return None

    question = str(raw.get("question", "") or "").strip()
    question_id = str(raw.get("question_id", "") or "").strip()
    if not question:
        return None

    options = raw.get("options")
    normalized_options: dict[str, str] | None = None
    if isinstance(options, dict):
        normalized_options = {
            str(key).strip().upper()[:1]: str(value or "").strip()
            for key, value in options.items()
            if str(value or "").strip()
        }

    return {
        "parent_quiz_session_id": str(raw.get("parent_quiz_session_id", "") or "").strip(),
        "question_id": question_id,
        "question": question,
        "question_type": str(raw.get("question_type", "") or "").strip(),
        "options": normalized_options,
        "correct_answer": str(raw.get("correct_answer", "") or "").strip(),
        "explanation": str(raw.get("explanation", "") or "").strip(),
        "difficulty": str(raw.get("difficulty", "") or "").strip(),
        "concentration": str(raw.get("concentration", "") or "").strip(),
        "knowledge_context": clip_text(str(raw.get("knowledge_context", "") or "").strip()),
        "user_answer": str(raw.get("user_answer", "") or "").strip(),
        "is_correct": raw.get("is_correct"),
        "user_answer_image_filenames": normalize_filename_list(raw),
        "ai_judgment": clip_text(str(raw.get("ai_judgment", "") or "").strip()),
    }


def extract_persist_user_message(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return True
    raw = config.pop("_persist_user_message", True)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() not in {"false", "0", "no"}
    return bool(raw)


def extract_regenerate_flag(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return False
    raw = config.pop("_regenerate", False)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "1", "yes"}
    return bool(raw)


def format_followup_question_context(context: dict[str, Any], language: str = "en") -> str:
    options = context.get("options") or {}
    option_lines = []
    if isinstance(options, dict) and options:
        for key, value in options.items():
            if value:
                option_lines.append(f"{key}. {value}")
    correctness = context.get("is_correct")
    correctness_text = (
        "correct" if correctness is True else "incorrect" if correctness is False else "unknown"
    )

    if str(language or "en").lower().startswith("zh"):
        lines = [
            "你正在处理一道测验题的后续追问。",
            "下面是本题上下文，请在后续回答中优先围绕这道题进行解释、纠错、延展和追问。",
            "如果用户提出超出本题的内容，也可以正常回答，但要保持和本题的连续性。",
            "",
            "[Question Follow-up Context]",
            f"Question ID: {context.get('question_id') or '(none)'}",
            f"Parent quiz session: {context.get('parent_quiz_session_id') or '(none)'}",
            f"Question type: {context.get('question_type') or '(none)'}",
            f"Difficulty: {context.get('difficulty') or '(none)'}",
            f"Concentration: {context.get('concentration') or '(none)'}",
            "",
            "Question:",
            context.get("question") or "(none)",
        ]
        if option_lines:
            lines.extend(["", "Options:", *option_lines])
        lines.extend(
            [
                "",
                f"User answer: {context.get('user_answer') or '(not provided)'}",
                f"User result: {correctness_text}",
                f"Reference answer: {context.get('correct_answer') or '(none)'}",
                "",
                "Explanation:",
                context.get("explanation") or "(none)",
            ]
        )
        image_filenames = context.get("user_answer_image_filenames") or []
        if isinstance(image_filenames, list) and image_filenames:
            filename_text = "、".join(image_filenames)
            count_text = f"{len(image_filenames)} 张" if len(image_filenames) > 1 else "一张"
            lines.extend(
                [
                    "",
                    "学习者作答附图：",
                    f"该作答共附了{count_text}图片（文件名：{filename_text}），"
                    f"随首条追问消息一起发送，是用户提交的作答内容的一部分，不是无关上下文。"
                    f"请结合图片中的文字/公式/草图进行解读，并将其视为对上面 “User answer” 文本的补充。",
                ]
            )
        ai_judgment = context.get("ai_judgment")
        if ai_judgment:
            lines.extend(
                [
                    "",
                    "AI 评判（之前已对学习者作答给出的评判，请基于此继续，不要重复完整重写）：",
                    ai_judgment,
                ]
            )
        if context.get("knowledge_context"):
            lines.extend(
                [
                    "",
                    "Knowledge context:",
                    context["knowledge_context"],
                ]
            )
        return "\n".join(lines).strip()

    lines = [
        "You are handling follow-up questions about a single quiz item.",
        "Use the question context below as the primary grounding for future turns in this session.",
        "If the user asks something broader, you may answer normally, but maintain continuity with this quiz item.",
        "",
        "[Question Follow-up Context]",
        f"Question ID: {context.get('question_id') or '(none)'}",
        f"Parent quiz session: {context.get('parent_quiz_session_id') or '(none)'}",
        f"Question type: {context.get('question_type') or '(none)'}",
        f"Difficulty: {context.get('difficulty') or '(none)'}",
        f"Concentration: {context.get('concentration') or '(none)'}",
        "",
        "Question:",
        context.get("question") or "(none)",
    ]
    if option_lines:
        lines.extend(["", "Options:", *option_lines])
    lines.extend(
        [
            "",
            f"User answer: {context.get('user_answer') or '(not provided)'}",
            f"User result: {correctness_text}",
            f"Reference answer: {context.get('correct_answer') or '(none)'}",
            "",
            "Explanation:",
            context.get("explanation") or "(none)",
        ]
    )
    image_filenames = context.get("user_answer_image_filenames") or []
    if isinstance(image_filenames, list) and image_filenames:
        joined = ", ".join(image_filenames)
        plural = "images were" if len(image_filenames) > 1 else "image was"
        plural_noun = (
            "Learner answer images" if len(image_filenames) > 1 else "Learner answer image"
        )
        lines.extend(
            [
                "",
                f"{plural_noun}:",
                f"{len(image_filenames)} {plural} attached to the first follow-up message "
                f"(filenames: {joined}). They are part of the learner's answer — read their "
                "text/formulas/sketches and treat them as a supplement to the typed `User answer` "
                "above, not unrelated context.",
            ]
        )
    ai_judgment = context.get("ai_judgment")
    if ai_judgment:
        lines.extend(
            [
                "",
                "Prior AI judgment (already shown to the learner — build on it instead of restating it in full):",
                ai_judgment,
            ]
        )
    if context.get("knowledge_context"):
        lines.extend(
            [
                "",
                "Knowledge context:",
                context["knowledge_context"],
            ]
        )
    return "\n".join(lines).strip()
