import test from "node:test";
import assert from "node:assert/strict";

import {
  chatReducer,
  createSessionEntry,
  initialState,
  type ProviderState,
} from "../../../context/chat/state";
import type { StreamEvent } from "../../../lib/unified-ws";

function contentEvent(seq: number, content: string): StreamEvent {
  return {
    type: "content",
    source: "assistant",
    stage: "",
    content,
    metadata: {},
    turn_id: "turn-1",
    seq,
    timestamp: seq,
  };
}

function stateWithSession(): ProviderState {
  const session = createSessionEntry("s1", "s1");
  return {
    ...initialState,
    selectedKey: "s1",
    sessions: { s1: session },
  };
}

test("chatReducer appends stream content once per turn sequence", () => {
  let state = stateWithSession();
  state = chatReducer(state, { type: "STREAM_START", key: "s1" });
  state = chatReducer(state, {
    type: "STREAM_EVENT",
    key: "s1",
    event: contentEvent(1, "hello"),
  });
  state = chatReducer(state, {
    type: "STREAM_EVENT",
    key: "s1",
    event: contentEvent(1, "hello"),
  });

  const session = state.sessions.s1;
  const assistant = session.messages.at(-1);
  assert.equal(session.isStreaming, true);
  assert.equal(session.lastSeq, 1);
  assert.equal(assistant?.role, "assistant");
  assert.equal(assistant?.content, "hello");
  assert.equal(assistant?.events?.length, 1);
});

test("chatReducer marks cancelled streams as ended", () => {
  let state = stateWithSession();
  state = chatReducer(state, { type: "STREAM_START", key: "s1" });
  state = chatReducer(state, {
    type: "STREAM_END",
    key: "s1",
    status: "cancelled",
  });

  assert.equal(state.sessions.s1.isStreaming, false);
  assert.equal(state.sessions.s1.status, "cancelled");
  assert.equal(state.sessions.s1.activeTurnId, null);
  assert.equal(state.sidebarRefreshToken, 1);
});

test("chatReducer reconciles optimistic turn ids from DONE metadata", () => {
  let state = stateWithSession();
  state = chatReducer(state, {
    type: "LOAD_SESSION",
    key: "s1",
    sessionId: "s1",
    messages: [
      { id: -2, role: "user", content: "question" },
      {
        id: -1,
        role: "assistant",
        content: "answer",
        parentMessageId: -2,
        events: [contentEvent(1, "answer")],
      },
    ],
  });
  state = chatReducer(state, {
    type: "RECONCILE_TURN",
    key: "s1",
    turnId: "turn-1",
    userMessageId: 12,
    assistantMessageId: 13,
  });

  assert.deepEqual(
    state.sessions.s1.messages.map((message) => message.id),
    [12, 13],
  );
  assert.equal(state.sessions.s1.messages[1].parentMessageId, 12);
});

test("chatReducer deletes a user turn with its paired assistant", () => {
  let state = stateWithSession();
  state = chatReducer(state, {
    type: "LOAD_SESSION",
    key: "s1",
    sessionId: "s1",
    messages: [
      { id: 1, role: "user", content: "question" },
      { id: 2, role: "assistant", content: "answer" },
      { id: 3, role: "user", content: "next" },
    ],
  });
  state = chatReducer(state, {
    type: "DELETE_TURN",
    key: "s1",
    messageId: 1,
  });

  assert.deepEqual(
    state.sessions.s1.messages.map((message) => message.id),
    [3],
  );
  assert.equal(state.sessions.s1.status, "idle");
  assert.equal(state.sidebarRefreshToken, 1);
});
