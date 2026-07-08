import test from "node:test";
import assert from "node:assert/strict";

import {
  asLLMSelection,
  hydrateMessageAttachments,
  hydrateRequestSnapshot,
  hydrateSessionMessages,
  normalizeSelectedBranches,
} from "../../../lib/chat/hydration";

test("hydrateMessageAttachments keeps preview-safe attachment fields", () => {
  const attachments = hydrateMessageAttachments([
    {
      type: "file",
      filename: "notes.pdf",
      url: "/api/attachments/a1",
      mime_type: "application/pdf",
      id: "a1",
      extracted_text: "hello",
      generated: true,
      size_bytes: 42,
    },
  ]);

  assert.deepEqual(attachments, [
    {
      type: "file",
      filename: "notes.pdf",
      base64: undefined,
      url: "/api/attachments/a1",
      mime_type: "application/pdf",
      id: "a1",
      extracted_text: "hello",
      generated: true,
      size_bytes: 42,
    },
  ]);
});

test("hydrateRequestSnapshot normalizes stored request metadata", () => {
  const snapshot = hydrateRequestSnapshot(
    {
      capability: "chat",
      metadata: {
        request_snapshot: {
          content: "actual",
          capability: "deep_research",
          enabledTools: ["web_search", 1, ""],
          knowledgeBases: ["kb"],
          language: "zh",
          notebookReferences: [{ notebook_id: "n1", record_ids: ["r1", ""] }],
          historyReferences: ["s1", ""],
          questionNotebookReferences: ["2", 3, "x"],
          bookReferences: [{ book_id: "b1", page_ids: ["p1", "p1"] }],
          persona: "mentor",
          memoryReferences: ["summary", "bad"],
          llmSelection: { profile_id: " p ", model_id: " m " },
        },
      },
      attachments: [],
    },
    "fallback",
    [],
  );

  assert.deepEqual(snapshot, {
    content: "actual",
    capability: "deep_research",
    enabledTools: ["web_search"],
    knowledgeBases: ["kb"],
    language: "zh",
    notebookReferences: [{ notebook_id: "n1", record_ids: ["r1"] }],
    historyReferences: ["s1"],
    questionNotebookReferences: [2, 3],
    bookReferences: [{ book_id: "b1", page_ids: ["p1"] }],
    persona: "mentor",
    memoryReferences: ["summary"],
    llmSelection: { profile_id: "p", model_id: "m" },
  });
});

test("selection helpers reject incomplete values", () => {
  assert.equal(asLLMSelection({ profile_id: "p" }), null);
  assert.deepEqual(normalizeSelectedBranches({ a: "2", b: -1, c: "x" }), {
    a: 2,
  });
});

test("hydrateSessionMessages filters system rows and hydrates chat messages", () => {
  const messages = hydrateSessionMessages([
    {
      id: 1,
      role: "system",
      content: "hidden",
      attachments: [],
    },
    {
      id: 2,
      role: "user",
      content: [{ type: "text", text: "hello" }],
      capability: "chat",
      attachments: [],
      events: [],
      parent_message_id: null,
      metadata: {
        request_snapshot: {
          content: "hello",
          enabledTools: ["web_search"],
          knowledgeBases: ["kb"],
          language: "en",
        },
      },
    },
    {
      id: 3,
      role: "assistant",
      content: "##Heading",
      capability: "chat",
      attachments: [
        {
          type: "file",
          filename: "out.txt",
          url: "/api/attachments/out",
        },
      ],
      events: [{ type: "done", source: "server", stage: "", timestamp: 1 }],
      parent_message_id: 2,
    },
  ]);

  assert.equal(messages.length, 2);
  assert.equal(messages[0].content, "hello");
  assert.deepEqual(messages[0].requestSnapshot, {
    content: "hello",
    capability: "chat",
    enabledTools: ["web_search"],
    knowledgeBases: ["kb"],
    language: "en",
  });
  assert.equal(messages[1].content, "##Heading");
  assert.equal(messages[1].parentMessageId, 2);
  assert.equal(messages[1].attachments[0].filename, "out.txt");
  assert.equal(messages[1].events[0].type, "done");
});
