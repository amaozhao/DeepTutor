import test from "node:test";
import assert from "node:assert/strict";

import {
  runningSessionStatuses,
  selectedChatState,
  selectedSessionRecord,
} from "../../../context/chat/selectors";
import { createSessionEntry, initialState } from "../../../context/chat/state";

test("selectedChatState returns only the selected chat fields", () => {
  const session = {
    ...createSessionEntry("s1", "s1"),
    sessionTitle: "Title",
    enabledTools: ["reason"],
  };

  const selected = selectedChatState({
    ...initialState,
    selectedKey: "s1",
    sessions: { s1: session },
  });

  assert.equal(selected.sessionId, "s1");
  assert.equal(selected.sessionTitle, "Title");
  assert.deepEqual(selected.enabledTools, ["reason"]);
  assert.equal((selected as { key?: string }).key, undefined);
});

test("selectedSessionRecord returns the selected key and session when present", () => {
  const session = createSessionEntry("s1", "session-1");

  assert.deepEqual(
    selectedSessionRecord({
      ...initialState,
      selectedKey: "s1",
      sessions: { s1: session },
    }),
    { key: "s1", session },
  );
});

test("selectedSessionRecord returns null when no selected session exists", () => {
  assert.equal(selectedSessionRecord(initialState), null);
  assert.equal(
    selectedSessionRecord({
      ...initialState,
      selectedKey: "missing",
      sessions: {},
    }),
    null,
  );
});

test("runningSessionStatuses includes only persisted running sessions", () => {
  const running = {
    ...createSessionEntry("running", "session-running"),
    status: "running" as const,
    activeTurnId: "turn-1",
    updatedAt: 123,
  };
  const idle = {
    ...createSessionEntry("idle", "session-idle"),
    status: "idle" as const,
  };
  const draft = {
    ...createSessionEntry("draft"),
    status: "running" as const,
  };

  assert.deepEqual(
    runningSessionStatuses({
      running,
      idle,
      draft,
    }),
    {
      "session-running": {
        sessionId: "session-running",
        status: "running",
        activeTurnId: "turn-1",
        updatedAt: 123,
      },
    },
  );
});
