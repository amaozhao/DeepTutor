import test from "node:test";
import assert from "node:assert/strict";

import {
  isChoiceQuizQuestion,
  isConceptQuizQuestion,
  isFillInBlankQuizQuestion,
  normalizeQuizQuestionType,
  resolveChoiceAnswerKey,
  resolveConceptAnswer,
} from "../lib/quiz-question-type";
import {
  extractQuizQuestions,
  quizFollowupAnswerImageAttachments,
  quizFollowupConfigWithMemory,
  quizFollowupSendPlan,
} from "../lib/quiz-types";

const baseQuestion = {
  question_id: "q1",
  question: "Pick one",
  question_type: "choice" as const,
  options: { A: "One", B: "Two" },
  correct_answer: "A",
  explanation: "A is correct",
};

test("normalizeQuizQuestionType maps legacy choice aliases to choice", () => {
  assert.equal(normalizeQuizQuestionType("choice"), "choice");
  assert.equal(normalizeQuizQuestionType("multiple_choice"), "choice");
  assert.equal(normalizeQuizQuestionType("multiple choice"), "choice");
  assert.equal(normalizeQuizQuestionType("mcq"), "choice");
  assert.equal(isChoiceQuizQuestion("multiple_choice"), true);
});

test("normalizeQuizQuestionType preserves every canonical type", () => {
  assert.equal(normalizeQuizQuestionType("written"), "written");
  assert.equal(normalizeQuizQuestionType("essay"), "written");
  assert.equal(normalizeQuizQuestionType("short_answer"), "short_answer");
  assert.equal(normalizeQuizQuestionType("concept"), "concept");
  assert.equal(normalizeQuizQuestionType("true_false"), "concept");
  assert.equal(normalizeQuizQuestionType("fill_in_blank"), "fill_in_blank");
  assert.equal(normalizeQuizQuestionType("fill-in-the-blank"), "fill_in_blank");
  assert.equal(normalizeQuizQuestionType("coding"), "coding");
  assert.equal(normalizeQuizQuestionType("programming"), "coding");
  assert.equal(isConceptQuizQuestion("true_false"), true);
  assert.equal(isFillInBlankQuizQuestion("fill-in-the-blank"), true);
});

test("resolveConceptAnswer normalizes T/F variants", () => {
  assert.equal(resolveConceptAnswer("true"), "true");
  assert.equal(resolveConceptAnswer("TRUE"), "true");
  assert.equal(resolveConceptAnswer("false"), "false");
  assert.equal(resolveConceptAnswer(""), "");
  assert.equal(resolveConceptAnswer("maybe"), "");
});

test("resolveChoiceAnswerKey accepts either the option key or label text", () => {
  const options = {
    A: "Alpha",
    B: "Beta",
    C: "Gamma",
    D: "Delta",
  };

  assert.equal(resolveChoiceAnswerKey("C", options), "C");
  assert.equal(resolveChoiceAnswerKey("gamma", options), "C");
});

test("extractQuizQuestions normalizes legacy question types from payloads", () => {
  const questions = extractQuizQuestions({
    summary: {
      results: [
        {
          qa_pair: {
            question_id: "q_1",
            question: "Pick the best answer.",
            question_type: "multiple_choice",
            options: { A: "One", B: "Two", C: "Three", D: "Four" },
            correct_answer: "B",
            explanation: "Because two is correct.",
          },
        },
      ],
    },
  });

  assert.ok(questions);
  assert.equal(questions?.[0]?.question_type, "choice");
});

test("quizFollowupAnswerImageAttachments maps usable answer images", () => {
  assert.deepEqual(
    quizFollowupAnswerImageAttachments([
      {
        base64: "abc",
        url: "https://example.test/a.png",
        filename: "a.png",
        mime: "image/png",
      },
      {
        base64: null,
        url: "https://example.test/b.jpg",
        filename: "b.jpg",
        mime: "image/jpeg",
      },
      {
        base64: null,
        url: null,
        filename: "empty.png",
        mime: "image/png",
      },
    ]),
    [
      {
        type: "image",
        base64: "abc",
        filename: "a.png",
        mime_type: "image/png",
      },
      {
        type: "image",
        url: "https://example.test/b.jpg",
        filename: "b.jpg",
        mime_type: "image/jpeg",
      },
    ],
  );
});

test("quizFollowupConfigWithMemory only adds memory references when present", () => {
  const config = { followup_question_context: { question_id: "q1" } };
  assert.equal(quizFollowupConfigWithMemory(config, []), config);
  assert.deepEqual(quizFollowupConfigWithMemory(config, ["profile"]), {
    followup_question_context: { question_id: "q1" },
    memory_references: ["profile"],
  });
});

test("quizFollowupSendPlan blocks empty or streaming follow-up sends", () => {
  const base = {
    content: "",
    isStreaming: false,
    isFirstSend: true,
    question: baseQuestion,
    userAnswer: "",
    isCorrect: null,
    parentQuizSessionId: null,
    answerImages: [],
    aiJudgment: "",
    attachments: [],
    selectedKnowledgeBases: [],
    selectedBookReferences: [],
    selectedNotebookRecords: [],
    selectedHistorySessions: [],
    selectedQuestionEntries: [],
    selectedMemoryFiles: [],
    selectedPersona: null,
    memoryReferences: [],
  };

  assert.equal(quizFollowupSendPlan(base), null);
  assert.equal(
    quizFollowupSendPlan({
      ...base,
      content: "Explain",
      isStreaming: true,
    }),
    null,
  );
});

test("quizFollowupSendPlan builds first-turn context and optional references", () => {
  const plan = quizFollowupSendPlan({
    content: "",
    isStreaming: false,
    isFirstSend: true,
    question: baseQuestion,
    userAnswer: "A",
    isCorrect: true,
    parentQuizSessionId: "quiz-session",
    answerImages: [
      {
        base64: "abc",
        url: null,
        filename: "answer.png",
        mime: "image/png",
      },
    ],
    aiJudgment: "Good",
    attachments: [],
    selectedKnowledgeBases: ["kb"],
    selectedBookReferences: [],
    selectedNotebookRecords: [],
    selectedHistorySessions: [],
    selectedQuestionEntries: [],
    selectedMemoryFiles: ["profile"],
    selectedPersona: "Socratic",
    memoryReferences: ["profile"],
  });

  assert.ok(plan);
  assert.equal(plan.content, "");
  assert.equal(plan.persona, "Socratic");
  assert.deepEqual(plan.answerImageAttachments, [
    {
      type: "image",
      base64: "abc",
      filename: "answer.png",
      mime_type: "image/png",
    },
  ]);
  assert.deepEqual(plan.config, {
    followup_question_context: {
      parent_quiz_session_id: "quiz-session",
      question_id: "q1",
      question: "Pick one",
      question_type: "choice",
      options: { A: "One", B: "Two" },
      correct_answer: "A",
      explanation: "A is correct",
      difficulty: undefined,
      concentration: undefined,
      knowledge_context: undefined,
      user_answer: "A",
      is_correct: true,
      user_answer_image_filenames: ["answer.png"],
      ai_judgment: "Good",
    },
    memory_references: ["profile"],
  });

  const followupTurn = quizFollowupSendPlan({
    content: "Next",
    isStreaming: false,
    isFirstSend: false,
    question: baseQuestion,
    userAnswer: "A",
    isCorrect: true,
    parentQuizSessionId: "quiz-session",
    answerImages: [
      {
        base64: "abc",
        url: null,
        filename: "answer.png",
        mime: "image/png",
      },
    ],
    aiJudgment: "Good",
    attachments: [],
    selectedKnowledgeBases: [],
    selectedBookReferences: [],
    selectedNotebookRecords: [],
    selectedHistorySessions: [],
    selectedQuestionEntries: [],
    selectedMemoryFiles: [],
    selectedPersona: null,
    memoryReferences: [],
  });
  assert.deepEqual(followupTurn?.answerImageAttachments, []);
});
