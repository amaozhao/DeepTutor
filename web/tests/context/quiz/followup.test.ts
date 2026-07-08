import test from "node:test";
import assert from "node:assert/strict";

import {
  applyFollowupSessionEvent,
  applyFollowupStreamEvent,
  createEmptyThreadState,
  followupDoneState,
  followupFailedState,
  followupHydratedState,
  followupResumeState,
  followupSessionEventInfo,
  followupStartUserTurnState,
  shouldHydrateFollowupThread,
} from "../../../context/quiz/followup";
import type { StreamEvent } from "../../../lib/unified-ws";

function event(partial: Partial<StreamEvent>): StreamEvent {
  return {
    type: "content",
    source: "assistant",
    stage: "",
    content: "",
    metadata: {},
    timestamp: 1,
    ...partial,
  };
}

test("followupSessionEventInfo reads session ids from metadata first", () => {
  assert.deepEqual(
    followupSessionEventInfo(
      event({
        type: "session",
        session_id: "wire-session",
        turn_id: "wire-turn",
        metadata: { session_id: "meta-session", turn_id: "meta-turn" },
      }),
    ),
    { sessionId: "meta-session", turnId: "meta-turn" },
  );
  assert.equal(
    followupSessionEventInfo(event({ type: "session", metadata: {} })),
    null,
  );
});

test("applyFollowupSessionEvent stores session and active turn", () => {
  const state = applyFollowupSessionEvent(createEmptyThreadState(), {
    sessionId: "session-1",
    turnId: "turn-1",
  });

  assert.equal(state.sessionId, "session-1");
  assert.equal(state.activeTurnId, "turn-1");
});

test("followupDoneState clears streaming status", () => {
  const state = followupDoneState({
    ...createEmptyThreadState(),
    isStreaming: true,
    currentStage: "thinking",
    activeTurnId: "turn-1",
  });

  assert.equal(state.isStreaming, false);
  assert.equal(state.currentStage, "");
  assert.equal(state.activeTurnId, null);
});

test("followupFailedState clears streaming and preserves existing errors", () => {
  const failed = followupFailedState(
    {
      ...createEmptyThreadState(),
      isStreaming: true,
      currentStage: "responding",
      activeTurnId: "turn-1",
    },
    "connection closed",
  );
  assert.equal(failed.isStreaming, false);
  assert.equal(failed.currentStage, "");
  assert.equal(failed.activeTurnId, null);
  assert.equal(failed.error, "connection closed");

  const preserved = followupFailedState(
    { ...failed, error: "first error" },
    "second error",
  );
  assert.equal(preserved.error, "first error");
});

test("followupStartUserTurnState opens and starts a user turn", () => {
  const state = followupStartUserTurnState(
    {
      ...createEmptyThreadState(),
      input: "draft",
      error: "old error",
      messages: [{ role: "assistant", content: "previous" }],
    },
    "next question",
  );

  assert.equal(state.isOpen, true);
  assert.equal(state.input, "");
  assert.equal(state.isStreaming, true);
  assert.equal(state.error, null);
  assert.deepEqual(state.messages, [
    { role: "assistant", content: "previous" },
    { role: "user", content: "next question" },
  ]);
});

test("followupResumeState resumes a paused turn", () => {
  const state = followupResumeState({
    ...createEmptyThreadState(),
    isStreaming: false,
    error: "needs answer",
  });

  assert.equal(state.isStreaming, true);
  assert.equal(state.error, null);
});

test("followupHydratedState stores session and normalizes message events", () => {
  const state = followupHydratedState(createEmptyThreadState(), "session-1", [
    { role: "user", content: "question" },
    {
      role: "assistant",
      content: "answer",
      events: [event({ type: "content", content: "answer" })],
    },
  ]);

  assert.equal(state.sessionId, "session-1");
  assert.deepEqual(state.messages, [
    { role: "user", content: "question", events: [] },
    {
      role: "assistant",
      content: "answer",
      events: [event({ type: "content", content: "answer" })],
    },
  ]);
});

test("shouldHydrateFollowupThread only hydrates empty idle threads", () => {
  assert.equal(shouldHydrateFollowupThread(undefined), true);
  assert.equal(shouldHydrateFollowupThread(createEmptyThreadState()), true);
  assert.equal(
    shouldHydrateFollowupThread({
      ...createEmptyThreadState(),
      messages: [{ role: "user", content: "draft" }],
    }),
    false,
  );
  assert.equal(
    shouldHydrateFollowupThread({
      ...createEmptyThreadState(),
      isStreaming: true,
    }),
    false,
  );
});

test("applyFollowupStreamEvent appends event content to assistant message", () => {
  const state = applyFollowupStreamEvent(
    {
      ...createEmptyThreadState(),
      messages: [{ role: "user", content: "Explain" }],
    },
    event({
      type: "content",
      content: "answer",
      turn_id: "turn-1",
    }),
  );

  const assistant = state.messages.at(-1);
  assert.equal(state.activeTurnId, "turn-1");
  assert.equal(assistant?.role, "assistant");
  assert.equal(assistant?.content, "answer");
  assert.equal(assistant?.events?.length, 1);
});

test("applyFollowupStreamEvent handles stages and terminal errors", () => {
  let state = applyFollowupStreamEvent(
    { ...createEmptyThreadState(), isStreaming: true },
    event({ type: "stage_start", stage: "reasoning" }),
  );
  assert.equal(state.currentStage, "reasoning");

  state = applyFollowupStreamEvent(
    state,
    event({
      type: "error",
      content: "failed",
      metadata: { turn_terminal: true },
    }),
  );

  assert.equal(state.error, "failed");
  assert.equal(state.isStreaming, false);
  assert.equal(state.currentStage, "");
  assert.equal(state.activeTurnId, null);
});
