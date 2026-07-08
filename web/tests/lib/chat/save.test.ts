import test from "node:test";
import assert from "node:assert/strict";

import {
  chatNotebookSaveMessages,
  chatNotebookSavePayload,
} from "../../../lib/chat/save";

test("chatNotebookSaveMessages keeps modal fields only", () => {
  assert.deepEqual(
    chatNotebookSaveMessages([
      { role: "user", content: "Question", capability: "chat" },
      { role: "assistant", content: "Answer" },
    ]),
    [
      { role: "user", content: "Question", capability: "chat" },
      { role: "assistant", content: "Answer", capability: undefined },
    ],
  );
});

test("chatNotebookSavePayload returns null without messages", () => {
  assert.equal(
    chatNotebookSavePayload({
      messages: [],
      firstUserTitle: "",
      activeCapability: null,
      language: "en",
      sessionId: null,
    }),
    null,
  );
});

test("chatNotebookSavePayload builds chat metadata", () => {
  assert.deepEqual(
    chatNotebookSavePayload({
      messages: [{ role: "user", content: "Question" }],
      firstUserTitle: "Question",
      activeCapability: null,
      language: "zh",
      sessionId: "s1",
    }),
    {
      recordType: "chat",
      title: "Question",
      userQuery: "",
      output: "",
      metadata: {
        source: "chat",
        capability: "chat",
        ui_language: "zh",
        session_id: "s1",
        total_message_count: 1,
      },
    },
  );
});
