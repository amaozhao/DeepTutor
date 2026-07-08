"""Conversation interaction built-in tool wrappers."""

from __future__ import annotations

from typing import Any

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.tools.builtin.common import _PromptHintsMixin


class AskUserTool(_PromptHintsMixin, BaseTool):
    """Pause the turn mid-loop to ask the user a clarifying question.

    Returns ``pause_for_user`` carrying the structured question payload.
    The chat pipeline halts the agentic loop after this call, surfaces
    the question + options as a card in the chat UI, and **waits for
    the user's reply on the same turn**. When the reply arrives the
    loop resumes with the user's answer substituted into this tool's
    result body — so subsequent iterations see "User answered: <text>"
    as the matching ``role=tool`` content and can act on it. The user
    can also abort the wait at any time via the composer's stop button
    (which cancels the whole turn).
    """

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="ask_user",
            description=(
                "Pause the conversation to ask the user 1-4 clarifying "
                "questions in one batch, rendered as a card with "
                "clickable options. Use ONLY when you are blocked on a "
                "decision that is genuinely the user's to make — one "
                "you cannot resolve from the request, the conversation, "
                "the attached material, or sensible defaults. Never use "
                "it to ask 'should I proceed?', to confirm what the "
                "user already said, or for choices with an obvious "
                "conventional answer — pick that answer, mention it, "
                "and proceed. The turn does NOT end: when the answers "
                "arrive the agentic loop resumes with them as this "
                "tool's result, and you must then complete the user's "
                "original request."
            ),
            parameters=[
                ToolParameter(
                    name="questions",
                    type="array",
                    description=(
                        "1-4 questions to ask in one card. Bundle ALL "
                        "clarifications into this single call — never "
                        "emit a second ask_user in the same message. "
                        "Give each question 2-4 distinct, mutually "
                        "exclusive options (set multi_select: true when "
                        "choices can combine, and phrase the question "
                        "accordingly). Option labels are short (1-5 "
                        "words); put what picking it implies in the "
                        "description. If you recommend an option, place "
                        "it FIRST and append ' (Recommended)' to its "
                        "label. Never add your own 'Other' option — the "
                        "card offers free-form input automatically."
                    ),
                    required=True,
                    items={
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "The complete question text.",
                            },
                            "header": {
                                "type": "string",
                                "description": (
                                    "Very short tab label (max 12 chars), "
                                    "e.g. 'Scope', 'Depth', '受众'."
                                ),
                            },
                            "options": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {
                                            "type": "string",
                                            "description": ("Concise display text (1-5 words)."),
                                        },
                                        "description": {
                                            "type": "string",
                                            "description": (
                                                "What this choice means or "
                                                "implies, trade-offs "
                                                "included."
                                            ),
                                        },
                                    },
                                    "required": ["label"],
                                },
                            },
                            "multi_select": {
                                "type": "boolean",
                                "description": ("true = the user may pick several options."),
                            },
                            "id": {"type": "string"},
                            "allow_free_text": {"type": "boolean"},
                            "placeholder": {
                                "type": "string",
                                "description": ("Hint shown in the free-form input."),
                            },
                        },
                        "required": ["prompt"],
                    },
                ),
                ToolParameter(
                    name="intro",
                    type="string",
                    description=(
                        "Optional one-line lead-in shown above the "
                        "questions (e.g. 'To tailor the research, please "
                        "answer:')."
                    ),
                    required=False,
                ),
                # NOTE: the legacy top-level ``{question, options}`` shape
                # is still ACCEPTED by ``execute()`` (normalised into a
                # one-element ``questions`` list) but is no longer
                # advertised in the schema — two redundant entry points
                # measurably degraded call accuracy on weaker models.
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        from deeptutor.tools.ask_user import build_ask_user_payload

        payload, err = build_ask_user_payload(
            questions=kwargs.get("questions"),
            intro=kwargs.get("intro"),
            question=kwargs.get("question"),
            options=kwargs.get("options"),
        )
        if payload is None:
            return ToolResult(content=err or "Invalid ask_user arguments.", success=False)

        payload_dict = payload.to_dict()
        prompts = ", ".join(q.prompt for q in payload.questions)
        return ToolResult(
            # The placeholder content is overwritten by the pipeline
            # once the user's reply arrives; the model never sees this
            # literal string on a normal flow. It only surfaces if the
            # runtime crashes mid-pause (in which case the LLM at least
            # gets a coherent log entry).
            content=f"[awaiting user reply to: {prompts}]",
            metadata={"ask_user": payload_dict},
            pause_for_user=payload_dict,
        )
