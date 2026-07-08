import test from "node:test";
import assert from "node:assert/strict";

import {
  buildRegenerateMessage,
  buildSubmitUserReplyMessage,
  cancelStreamingAction,
  regenerateStartActions,
  regenerateSessionPlan,
  userReplyTurnId,
} from "../../../context/chat/commands";
import type { StreamEvent } from "../../../lib/unified-ws";

test("buildSubmitUserReplyMessage supports legacy text replies", () => {
  assert.deepEqual(buildSubmitUserReplyMessage("turn-1", "answer"), {
    type: "submit_user_reply",
    turn_id: "turn-1",
    text: "answer",
  });
});

test("buildSubmitUserReplyMessage supports structured answers", () => {
  assert.deepEqual(
    buildSubmitUserReplyMessage("turn-1", {
      text: "fallback",
      answers: [{ questionId: "q1", text: "a1" }],
    }),
    {
      type: "submit_user_reply",
      turn_id: "turn-1",
      text: "fallback",
      answers: [{ questionId: "q1", text: "a1" }],
    },
  );
});

test("buildRegenerateMessage pins language override", () => {
  assert.deepEqual(buildRegenerateMessage("session-1", "zh"), {
    type: "regenerate",
    session_id: "session-1",
    overrides: { language: "zh" },
  });
});

test("cancelStreamingAction marks the stream cancelled", () => {
  assert.deepEqual(cancelStreamingAction("session-1"), {
    type: "STREAM_END",
    key: "session-1",
    status: "cancelled",
  });
});

test("regenerateStartActions pop the previous assistant before streaming", () => {
  assert.deepEqual(regenerateStartActions("session-1"), [
    { type: "POP_LAST_ASSISTANT", key: "session-1" },
    { type: "STREAM_START", key: "session-1" },
  ]);
});

test("userReplyTurnId requires an active turn", () => {
  assert.equal(userReplyTurnId(null), null);
  assert.equal(
    userReplyTurnId({ activeTurnId: null, isStreaming: true, messages: [] }),
    null,
  );
});

test("userReplyTurnId allows live streaming turns", () => {
  assert.equal(
    userReplyTurnId({
      activeTurnId: "turn-1",
      isStreaming: true,
      messages: [],
    }),
    "turn-1",
  );
});

test("userReplyTurnId allows paused turns with pending ask_user", () => {
  const askUserEvent: StreamEvent = {
    type: "tool_result",
    source: "server",
    stage: "",
    content: "",
    metadata: {
      tool_call_id: "call-1",
      tool_metadata: { ask_user: { questions: [{ id: "q", prompt: "Q?" }] } },
    },
    turn_id: "turn-1",
    timestamp: 1,
  };
  assert.equal(
    userReplyTurnId({
      activeTurnId: "turn-1",
      isStreaming: false,
      messages: [{ role: "assistant", content: "", events: [askUserEvent] }],
    }),
    "turn-1",
  );
  assert.equal(
    userReplyTurnId({
      activeTurnId: "turn-2",
      isStreaming: false,
      messages: [{ role: "assistant", content: "", events: [askUserEvent] }],
    }),
    null,
  );
});

test("regenerateSessionPlan blocks sessions that cannot regenerate", () => {
  assert.deepEqual(
    regenerateSessionPlan({ sessionId: null, isStreaming: false, messages: [] }),
    { canRegenerate: false },
  );
  assert.deepEqual(
    regenerateSessionPlan({
      sessionId: "session-1",
      isStreaming: true,
      messages: [{ role: "user", content: "hi" }],
    }),
    { canRegenerate: false },
  );
  assert.deepEqual(
    regenerateSessionPlan({
      sessionId: "session-1",
      isStreaming: false,
      messages: [{ role: "assistant", content: "hi" }],
    }),
    { canRegenerate: false },
  );
});

test("regenerateSessionPlan allows trailing user without restore snapshot", () => {
  assert.deepEqual(
    regenerateSessionPlan({
      sessionId: "session-1",
      isStreaming: false,
      messages: [{ role: "user", content: "hi" }],
    }),
    { canRegenerate: true },
  );
});

test("regenerateSessionPlan snapshots trailing assistant for rejected regenerate", () => {
  const assistant = {
    id: 2,
    role: "assistant" as const,
    content: "answer",
    events: [
      {
        type: "done" as const,
        source: "server",
        stage: "",
        content: "",
        metadata: {},
        timestamp: 1,
      },
    ],
  };
  const plan = regenerateSessionPlan({
    sessionId: "session-1",
    isStreaming: false,
    messages: [{ id: 1, role: "user", content: "hi" }, assistant],
  });
  assert.deepEqual(plan, { canRegenerate: true, restoreMessage: assistant });
  assert.notEqual(plan.restoreMessage, assistant);
});
