import test from "node:test";
import assert from "node:assert/strict";

import {
  chatCapabilitySendConfigPlan,
  chatConfirmedOutlineSendPlan,
  chatConfigWithSubagentBudget,
  chatOutgoingAttachments,
  chatQuizPdfAttachment,
  chatSendPlan,
} from "../../../lib/chat/send";

const t = (key: string) => key;
const quizConfig = {
  mode: "custom" as const,
  topic: "",
  num_questions: 3,
  difficulty: "auto",
  question_types: [],
  per_type_counts: {},
  paper_path: "",
  max_questions: 10,
};
const visualizeConfig = {
  render_mode: "auto" as const,
  quality: "medium" as const,
  style_hint: " clean ",
};
const researchConfig = {
  mode: "report" as const,
  depth: "deep" as const,
};
const base = {
  content: "",
  isStreaming: false,
  attachments: [],
  bookReferences: [],
  notebookRecords: [],
  historySessions: [],
  agentSessions: [],
  questionEntries: [],
  memoryFiles: [],
  memoryReferences: [],
  t,
};

test("chatSendPlan blocks empty or streaming sends", () => {
  assert.equal(chatSendPlan(base), null);
  assert.equal(
    chatSendPlan({ ...base, content: "hello", isStreaming: true }),
    null,
  );
});

test("chatSendPlan keeps typed content", () => {
  assert.deepEqual(chatSendPlan({ ...base, content: "hello" }), {
    content: "hello",
  });
});

test("chatSendPlan falls back to context prompt", () => {
  assert.deepEqual(
    chatSendPlan({ ...base, notebookRecords: [{}] }),
    { content: "Please use the selected context to help with this request." },
  );
  assert.deepEqual(
    chatSendPlan({ ...base, memoryFiles: [{}], memoryReferences: [{}] }),
    { content: "Please use the selected context to help with this request." },
  );
});

test("chatSendPlan falls back to image prompt", () => {
  assert.deepEqual(
    chatSendPlan({ ...base, attachments: [{ type: "image" }] }),
    { content: "Please analyze the attached image(s)." },
  );
});

test("chatOutgoingAttachments maps pending attachment mime fields", () => {
  assert.deepEqual(
    chatOutgoingAttachments([
      {
        type: "image",
        filename: "a.png",
        base64: "abc",
        mimeType: "image/png",
      },
    ]),
    [
      {
        type: "image",
        filename: "a.png",
        base64: "abc",
        mime_type: "image/png",
      },
    ],
  );
});

test("chatQuizPdfAttachment builds the mimic paper attachment payload", () => {
  assert.deepEqual(chatQuizPdfAttachment("paper.pdf", "abc"), {
    type: "pdf",
    filename: "paper.pdf",
    base64: "abc",
    mime_type: "application/pdf",
  });
});

test("chatCapabilitySendConfigPlan returns no config for plain chat", () => {
  assert.deepEqual(
    chatCapabilitySendConfigPlan({
      isQuizMode: false,
      isVisualizeMode: false,
      isResearchMode: false,
      quizConfig,
      visualizeConfig,
      researchConfig,
      researchConfigValid: true,
    }),
    { attachQuizPdf: false },
  );
});

test("chatCapabilitySendConfigPlan marks quiz mimic PDF attachment", () => {
  assert.deepEqual(
    chatCapabilitySendConfigPlan({
      isQuizMode: true,
      isVisualizeMode: false,
      isResearchMode: false,
      quizConfig: {
        ...quizConfig,
        mode: "mimic",
        paper_path: " paper.pdf ",
        max_questions: 7,
      },
      visualizeConfig,
      researchConfig,
      researchConfigValid: true,
    }),
    {
      attachQuizPdf: true,
      config: {
        mode: "mimic",
        paper_path: "paper.pdf",
        max_questions: 7,
      },
    },
  );
});

test("chatCapabilitySendConfigPlan builds visualize and research configs", () => {
  assert.deepEqual(
    chatCapabilitySendConfigPlan({
      isQuizMode: false,
      isVisualizeMode: true,
      isResearchMode: false,
      quizConfig,
      visualizeConfig,
      researchConfig,
      researchConfigValid: true,
    }),
    {
      attachQuizPdf: false,
      config: {
        render_mode: "auto",
        quality: "medium",
        style_hint: "clean",
      },
    },
  );

  assert.deepEqual(
    chatCapabilitySendConfigPlan({
      isQuizMode: false,
      isVisualizeMode: false,
      isResearchMode: true,
      quizConfig,
      visualizeConfig,
      researchConfig,
      researchConfigValid: true,
    }),
    {
      attachQuizPdf: false,
      config: { mode: "report", depth: "deep" },
    },
  );
});

test("chatCapabilitySendConfigPlan blocks invalid research settings", () => {
  assert.equal(
    chatCapabilitySendConfigPlan({
      isQuizMode: false,
      isVisualizeMode: false,
      isResearchMode: true,
      quizConfig,
      visualizeConfig,
      researchConfig,
      researchConfigValid: false,
    }),
    null,
  );
});

test("chatConfigWithSubagentBudget preserves config without an agent budget", () => {
  const config = { mode: "chat" };
  assert.equal(
    chatConfigWithSubagentBudget({
      config,
      selectedAgent: null,
      subagentBudget: 3,
    }),
    config,
  );
  assert.equal(
    chatConfigWithSubagentBudget({
      config,
      selectedAgent: "agent",
      subagentBudget: 0,
    }),
    config,
  );
  assert.equal(
    chatConfigWithSubagentBudget({
      config,
      selectedAgent: "agent",
      subagentBudget: null,
    }),
    config,
  );
});

test("chatConfigWithSubagentBudget merges selected agent budget", () => {
  assert.deepEqual(
    chatConfigWithSubagentBudget({
      config: { mode: "chat" },
      selectedAgent: "agent",
      subagentBudget: 2,
    }),
    { mode: "chat", subagent_consult_budget: 2 },
  );
  assert.deepEqual(
    chatConfigWithSubagentBudget({
      selectedAgent: "agent",
      subagentBudget: 2,
    }),
    { subagent_consult_budget: 2 },
  );
});

test("chatConfirmedOutlineSendPlan builds a fresh research config", () => {
  const outline = [{ title: "A", overview: "B" }];
  assert.deepEqual(
    chatConfirmedOutlineSendPlan({
      outline,
      topic: "topic",
      researchConfig: { mode: "report", depth: "deep" },
    }),
    {
      content: "topic",
      attachments: [],
      config: {
        mode: "report",
        depth: "deep",
        confirmed_outline: outline,
      },
      notebookReferences: undefined,
      historyReferences: undefined,
      options: {
        displayUserMessage: false,
        persistUserMessage: false,
        bookReferences: undefined,
      },
      questionNotebookReferences: undefined,
      persona: undefined,
      memoryReferences: undefined,
    },
  );
});

test("chatConfirmedOutlineSendPlan preserves replay snapshot context", () => {
  const outline = [{ title: "A", overview: "B" }];
  const originalSnapshot = {
    content: "old",
    capability: "chat",
    enabledTools: ["web_search"],
    knowledgeBases: ["kb1"],
    language: "zh",
    attachments: [{ type: "image" }],
    notebookReferences: [{ notebook_id: "n1", record_ids: ["r1"] }],
    historyReferences: ["h1"],
    bookReferences: [{ book_id: "b1", page_ids: ["p1"] }],
    questionNotebookReferences: [1],
    persona: "mentor",
    memoryReferences: ["summary" as const],
  };

  const plan = chatConfirmedOutlineSendPlan({
    outline,
    topic: "topic",
    researchConfig: { mode: "report", depth: "deep" },
    originalConfig: { mode: "notes" },
    originalSnapshot,
  });

  assert.deepEqual(plan.config, {
    mode: "notes",
    confirmed_outline: outline,
  });
  assert.deepEqual(plan.options.requestSnapshotOverride, {
    ...originalSnapshot,
    content: "topic",
    capability: "deep_research",
    config: plan.config,
  });
  assert.equal(plan.attachments, originalSnapshot.attachments);
  assert.equal(plan.options.bookReferences, originalSnapshot.bookReferences);
});
