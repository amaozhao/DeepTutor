import test from "node:test";
import assert from "node:assert/strict";

import {
  initialDraftSessionAction,
  loadSessionActionFromDetail,
  newSessionAction,
  renameSessionTitleAction,
  subscribeTurnMessageFromDetail,
  type SessionDetailInput,
} from "../../../context/chat/session";

function sessionDetail(
  overrides: Partial<SessionDetailInput> = {},
): SessionDetailInput {
  return {
    id: "internal-id",
    session_id: "session-1",
    title: "Loaded",
    messages: [],
    ...overrides,
  };
}

test("loadSessionActionFromDetail maps session detail to reducer action", () => {
  const action = loadSessionActionFromDetail(
    sessionDetail({
      preferences: {
        capability: "chat",
        tools: ["reason"],
        knowledge_bases: ["kb"],
        llm_selection: { profile_id: "p1", model_id: "m1" },
        persona: "mentor",
        selected_branches: { null: 3, bad: -1 },
      },
      active_turns: [
        {
          id: "turn-row",
          turn_id: "turn-1",
        },
      ],
    }),
    "zh",
  );

  assert.equal(action.type, "LOAD_SESSION");
  assert.equal(action.key, "session-1");
  assert.equal(action.sessionId, "session-1");
  assert.equal(action.title, "Loaded");
  assert.equal(action.status, "running");
  assert.equal(action.activeTurnId, "turn-1");
  assert.deepEqual(action.tools, ["reason"]);
  assert.deepEqual(action.knowledgeBases, ["kb"]);
  assert.deepEqual(action.llmSelection, { profile_id: "p1", model_id: "m1" });
  assert.equal(action.personaSelection, "mentor");
  assert.equal(action.language, "zh");
  assert.deepEqual(action.selectedBranches, { null: 3 });
});

test("subscribeTurnMessageFromDetail returns null without an active turn", () => {
  assert.equal(subscribeTurnMessageFromDetail(sessionDetail()), null);
});

test("subscribeTurnMessageFromDetail builds subscribe message for active turn", () => {
  assert.deepEqual(
    subscribeTurnMessageFromDetail(
      sessionDetail({
        active_turns: [
          {
            id: "turn-row",
            turn_id: "turn-1",
          },
        ],
      }),
    ),
    {
      key: "session-1",
      message: { type: "subscribe_turn", turn_id: "turn-1", after_seq: 0 },
    },
  );
});

test("renameSessionTitleAction uses server title or requested fallback", () => {
  assert.deepEqual(
    renameSessionTitleAction({
      key: "draft",
      requestedTitle: "Requested",
      updatedTitle: "Server",
    }),
    { type: "SET_SESSION_TITLE", key: "draft", title: "Server" },
  );
  assert.deepEqual(
    renameSessionTitleAction({
      key: "draft",
      requestedTitle: "Requested",
      updatedTitle: "",
    }),
    { type: "SET_SESSION_TITLE", key: "draft", title: "Requested" },
  );
});

test("newSessionAction starts a draft session", () => {
  assert.deepEqual(newSessionAction("draft-1"), {
    type: "NEW_SESSION",
    key: "draft-1",
  });
});

test("initialDraftSessionAction only creates a draft without a selected key", () => {
  assert.deepEqual(
    initialDraftSessionAction({
      selectedKey: null,
      makeDraftKey: () => "draft-1",
    }),
    { type: "NEW_SESSION", key: "draft-1" },
  );
  assert.equal(
    initialDraftSessionAction({
      selectedKey: "session-1",
      makeDraftKey: () => {
        throw new Error("should not allocate draft key");
      },
    }),
    null,
  );
});
