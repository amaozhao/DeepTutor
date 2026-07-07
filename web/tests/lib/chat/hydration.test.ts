import test from "node:test";
import assert from "node:assert/strict";

import {
  asLLMSelection,
  hydrateMessageAttachments,
  hydrateRequestSnapshot,
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
