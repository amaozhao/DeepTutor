import test from "node:test";
import assert from "node:assert/strict";

import {
  decideSessionTitleCommit,
  firstUserMessageTitle,
  resolveSessionTitle,
} from "../../../lib/chat/title";

test("firstUserMessageTitle derives a compact title from the first user message", () => {
  const title = firstUserMessageTitle([
    { role: "assistant", content: "ignored" },
    { role: "user", content: "  explain\n\nFourier\tseries  " },
    { role: "user", content: "ignored later" },
  ]);

  assert.equal(title, "explain Fourier series");
});

test("firstUserMessageTitle truncates long titles", () => {
  assert.equal(
    firstUserMessageTitle([{ role: "user", content: "x".repeat(100) }]),
    "x".repeat(80),
  );
});

test("resolveSessionTitle prefers persisted, then first user, then fallback", () => {
  assert.equal(resolveSessionTitle("  Saved  ", "First", "New chat"), "Saved");
  assert.equal(resolveSessionTitle("", "First", "New chat"), "First");
  assert.equal(resolveSessionTitle("", "", "New chat"), "New chat");
});

test("decideSessionTitleCommit closes empty or unchanged edits", () => {
  assert.deepEqual(
    decideSessionTitleCommit({
      canRename: true,
      displayTitle: "Current",
      draftTitle: "   ",
      persistedTitle: "Current",
    }),
    { type: "close", draftTitle: "Current" },
  );
  assert.deepEqual(
    decideSessionTitleCommit({
      canRename: true,
      displayTitle: "Current",
      draftTitle: "  Current  ",
      persistedTitle: "Current",
    }),
    { type: "close", draftTitle: "Current" },
  );
});

test("decideSessionTitleCommit saves trimmed changed titles only when renaming is allowed", () => {
  assert.deepEqual(
    decideSessionTitleCommit({
      canRename: true,
      displayTitle: "Current",
      draftTitle: "  Next  ",
      persistedTitle: "Current",
    }),
    { type: "save", title: "Next" },
  );
  assert.deepEqual(
    decideSessionTitleCommit({
      canRename: false,
      displayTitle: "Current",
      draftTitle: "  Next  ",
      persistedTitle: "Current",
    }),
    { type: "close", draftTitle: "Next" },
  );
});
