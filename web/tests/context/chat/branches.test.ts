import test from "node:test";
import assert from "node:assert/strict";

import {
  branchParentKey,
  branchSwitchPlan,
  editParentId,
  nextMessageParentIds,
  persistedMessageIdAt,
  userMessageIndexById,
} from "../../../context/chat/branches";
import type { MessageItem } from "../../../context/chat/state";

const messages: MessageItem[] = [
  { id: 1, role: "user", content: "first" },
  { id: 2, role: "assistant", content: "answer", parentMessageId: 1 },
  { id: -3, role: "user", content: "draft", parentMessageId: 2 },
];

test("branchParentKey uses the persisted root sentinel", () => {
  assert.equal(branchParentKey(null), "null");
  assert.equal(branchParentKey(12), "12");
});

test("branchSwitchPlan builds reducer action and persisted selections", () => {
  assert.deepEqual(
    branchSwitchPlan({
      key: "session-1",
      parentMessageId: 12,
      childId: 99,
      selectedBranches: { null: 1 },
    }),
    {
      action: {
        type: "SET_SELECTED_BRANCH",
        key: "session-1",
        parentKey: "12",
        childId: 99,
      },
      selectedBranches: { null: 1, "12": 99 },
    },
  );
});

test("nextMessageParentIds uses explicit parent ids for local and wire payloads", () => {
  assert.deepEqual(
    nextMessageParentIds({
      explicitParentId: null,
      messages,
      selectedBranches: {},
    }),
    { localParentId: null, wireParentId: null },
  );
});

test("nextMessageParentIds sends only persisted visible tips over the wire", () => {
  assert.deepEqual(
    nextMessageParentIds({
      messages,
      selectedBranches: {},
    }),
    { localParentId: -3 },
  );
  assert.deepEqual(
    nextMessageParentIds({
      messages: messages.slice(0, 2),
      selectedBranches: {},
    }),
    { localParentId: 2, wireParentId: 2 },
  );
});

test("userMessageIndexById ignores assistant rows with the same id", () => {
  assert.equal(userMessageIndexById(messages, 1), 0);
  assert.equal(userMessageIndexById(messages, 2), -1);
});

test("persistedMessageIdAt accepts only non-negative numeric ids", () => {
  assert.equal(persistedMessageIdAt(messages, 0, "user"), 1);
  assert.equal(persistedMessageIdAt(messages, 1, "user"), null);
  assert.equal(persistedMessageIdAt(messages, 2, "user"), null);
});

test("editParentId defaults missing parents to session root", () => {
  assert.equal(editParentId(messages[0]), null);
  assert.equal(editParentId(messages[2]), 2);
});
