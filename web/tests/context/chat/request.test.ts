import test from "node:test";
import assert from "node:assert/strict";

import {
  buildEffectiveChatRequest,
  chatStartTurnActions,
} from "../../../context/chat/request";
import { createSessionEntry } from "../../../context/chat/state";

test("buildEffectiveChatRequest builds snapshot and wire payload from session state", () => {
  const session = {
    ...createSessionEntry("draft", "s1"),
    activeCapability: "chat",
    enabledTools: ["web_search"],
    knowledgeBases: ["kb"],
    llmSelection: { profile_id: "p1", model_id: "m1" },
    personaSelection: "mentor",
  };
  const request = buildEffectiveChatRequest({
    content: "hello",
    attachments: [
      {
        type: "image",
        filename: "a.png",
        base64: "abc",
      },
    ],
    config: { depth: "brief" },
    notebookReferences: [{ notebook_id: "n1", record_ids: ["r1"] }],
    historyReferences: ["h1"],
    questionNotebookReferences: [7],
    memoryReferences: ["summary"],
    options: {
      bookReferences: [{ book_id: "b1", page_ids: ["p1"] }],
      parentMessageId: 1,
    },
    session,
    language: "zh",
    wireParentId: 2,
  });

  assert.deepEqual(request.requestSnapshot, {
    content: "hello",
    capability: "chat",
    enabledTools: ["web_search"],
    knowledgeBases: ["kb"],
    language: "zh",
    attachments: [
      {
        type: "image",
        filename: "a.png",
        base64: "abc",
        url: undefined,
        mime_type: undefined,
      },
    ],
    config: { depth: "brief" },
    notebookReferences: [{ notebook_id: "n1", record_ids: ["r1"] }],
    historyReferences: ["h1"],
    questionNotebookReferences: [7],
    bookReferences: [{ book_id: "b1", page_ids: ["p1"] }],
    persona: "mentor",
    memoryReferences: ["summary"],
    llmSelection: { profile_id: "p1", model_id: "m1" },
  });
  assert.deepEqual(request.turnMessage, {
    type: "start_turn",
    content: "hello",
    tools: ["web_search"],
    capability: "chat",
    knowledge_bases: ["kb"],
    session_id: "s1",
    attachments: [
      {
        type: "image",
        filename: "a.png",
        base64: "abc",
        url: undefined,
        mime_type: undefined,
      },
    ],
    language: "zh",
    notebook_references: [{ notebook_id: "n1", record_ids: ["r1"] }],
    history_references: ["h1"],
    question_notebook_references: [7],
    book_references: [{ book_id: "b1", page_ids: ["p1"] }],
    persona: "mentor",
    memory_references: ["summary"],
    llm_selection: { profile_id: "p1", model_id: "m1" },
    config: { depth: "brief" },
    parent_message_id: 2,
  });
});

test("buildEffectiveChatRequest lets replay snapshots override session state", () => {
  const session = {
    ...createSessionEntry("draft", "s1"),
    activeCapability: "chat",
    enabledTools: ["web_search"],
    knowledgeBases: ["kb"],
    personaSelection: "mentor",
  };
  const replay = {
    content: "old",
    capability: "deep_research",
    enabledTools: ["paper_search"],
    knowledgeBases: ["kb2"],
    language: "en",
    config: { mode: "fast" },
    persona: "",
  };
  const request = buildEffectiveChatRequest({
    content: "new",
    config: { ignored: true },
    persona: "ignored",
    options: {
      requestSnapshotOverride: replay,
      persistUserMessage: false,
    },
    session,
    language: "zh",
  });

  assert.equal(request.requestSnapshot, replay);
  assert.deepEqual(request.turnMessage, {
    type: "start_turn",
    content: "new",
    tools: ["paper_search"],
    capability: "deep_research",
    knowledge_bases: ["kb2"],
    session_id: "s1",
    attachments: undefined,
    language: "en",
    persona: "",
    config: { ignored: true, _persist_user_message: false },
  });
});

test("chatStartTurnActions builds optimistic user row and stream start", () => {
  const request = {
    capability: "chat",
    attachments: [{ type: "image" as const, filename: "a.png" }],
    requestSnapshot: {
      content: "hello",
      capability: "chat",
      enabledTools: [],
      knowledgeBases: [],
      language: "zh",
    },
  };

  assert.deepEqual(
    chatStartTurnActions({
      key: "draft",
      content: "hello",
      request,
      parentMessageId: 3,
    }),
    [
      {
        type: "ADD_USER_MSG",
        key: "draft",
        content: "hello",
        capability: "chat",
        attachments: [{ type: "image", filename: "a.png" }],
        requestSnapshot: request.requestSnapshot,
        parentMessageId: 3,
      },
      { type: "STREAM_START", key: "draft" },
    ],
  );

  assert.deepEqual(
    chatStartTurnActions({
      key: "draft",
      content: "hello",
      request,
      parentMessageId: null,
      displayUserMessage: false,
    }),
    [{ type: "STREAM_START", key: "draft" }],
  );
});
