import test from "node:test";
import assert from "node:assert/strict";

import { chatVisualizePromptFromEvent } from "../../../lib/chat/prefill";

test("chatVisualizePromptFromEvent extracts non-empty string details", () => {
  assert.equal(
    chatVisualizePromptFromEvent(new CustomEvent("dt:visualize-prompt", {
      detail: "Explain this node",
    })),
    "Explain this node",
  );
});

test("chatVisualizePromptFromEvent ignores empty or non-string details", () => {
  assert.equal(
    chatVisualizePromptFromEvent(new CustomEvent("dt:visualize-prompt", {
      detail: "",
    })),
    null,
  );
  assert.equal(
    chatVisualizePromptFromEvent(new CustomEvent("dt:visualize-prompt", {
      detail: 42,
    })),
    null,
  );
});
