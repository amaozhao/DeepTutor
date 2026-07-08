import test from "node:test";
import assert from "node:assert/strict";

import { chatMessagesScrollStyle } from "../../../lib/chat/style";

test("chatMessagesScrollStyle is absent without messages", () => {
  assert.equal(chatMessagesScrollStyle(false), undefined);
});

test("chatMessagesScrollStyle adds bottom padding and fade mask", () => {
  const style = chatMessagesScrollStyle(true);

  assert.equal(style?.paddingBottom, "48px");
  assert.equal(style?.WebkitMaskImage, style?.maskImage);
  assert.match(style?.maskImage ?? "", /calc\(100% - 40px\)/);
});
