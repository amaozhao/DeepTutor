import test from "node:test";
import assert from "node:assert/strict";

import {
  effectiveRunnerKey,
  eventStatus,
  isRegenerateRejection,
  moveRunner,
  sessionEventIds,
  sessionMetaTitle,
  terminalErrorInfo,
  type ChatRunnerMap,
} from "../../../context/chat/transport";
import type { StreamEvent } from "../../../lib/unified-ws";

function event(partial: Partial<StreamEvent>): StreamEvent {
  return {
    type: "content",
    source: "server",
    stage: "",
    content: "",
    metadata: {},
    timestamp: 1,
    ...partial,
  };
}

test("moveRunner renames the stored runner key in place", () => {
  const runners: ChatRunnerMap = new Map([
    ["draft", { key: "draft", client: {} as never }],
  ]);

  moveRunner(runners, "draft", "session-1");

  assert.equal(runners.has("draft"), false);
  assert.equal(runners.get("session-1")?.key, "session-1");
  assert.equal(effectiveRunnerKey(runners, "draft"), "draft");
  assert.equal(effectiveRunnerKey(runners, "session-1"), "session-1");
});

test("session metadata helpers prefer metadata over event fields", () => {
  const ids = sessionEventIds(
    event({
      type: "session",
      session_id: "event-session",
      turn_id: "event-turn",
      metadata: { session_id: "meta-session", turn_id: "meta-turn" },
    }),
  );

  assert.deepEqual(ids, {
    sessionId: "meta-session",
    turnId: "meta-turn",
  });
  assert.equal(
    sessionMetaTitle(
      event({ type: "session_meta", metadata: { title: " T " } }),
    ),
    "T",
  );
});

test("terminal error helpers normalize status and regenerate reasons", () => {
  const info = terminalErrorInfo(
    event({
      type: "error",
      metadata: {
        turn_terminal: true,
        reason: "regenerate_busy",
        status: "rejected",
      },
    }),
  );

  assert.deepEqual(info, {
    terminal: true,
    reason: "regenerate_busy",
    status: "rejected",
  });
  assert.equal(isRegenerateRejection(info.reason), true);
  assert.equal(eventStatus(event({ metadata: {} }), "completed"), "completed");
});
