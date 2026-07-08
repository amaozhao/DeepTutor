import test from "node:test";
import assert from "node:assert/strict";

import {
  defaultModelLabel,
  formatCompactTokens,
  formatDimensionBadge,
  formatVoiceBadge,
} from "../../../components/settings/format";

test("default model labels respect language and clamp bad indexes", () => {
  assert.equal(defaultModelLabel("en", 2), "Model 2");
  assert.equal(defaultModelLabel("zh", 0), "\u6a21\u578b1");
});

test("compact token badges parse numbers from strings", () => {
  assert.equal(formatCompactTokens("1,000,000"), "1M");
  assert.equal(formatCompactTokens("65536"), "66K");
  assert.equal(formatCompactTokens("bad"), "");
});

test("dimension and voice badges stay compact", () => {
  assert.equal(formatDimensionBadge("3,072"), "3072d");
  assert.equal(formatDimensionBadge("-1"), "1d");
  assert.equal(formatVoiceBadge("model:long-voice-name"), "long-voice-na\u2026");
});
