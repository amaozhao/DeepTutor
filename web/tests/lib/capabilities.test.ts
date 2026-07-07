import test from "node:test";
import assert from "node:assert/strict";

import { ALL_TOOLS, CAPABILITIES, getCapability } from "../../lib/capabilities";

test("getCapability falls back to chat", () => {
  assert.equal(getCapability(null).value, "");
  assert.equal(getCapability("missing").value, "");
});

test("capabilities only reference known tools", () => {
  const toolNames = new Set(ALL_TOOLS.map((tool) => tool.name));
  for (const capability of CAPABILITIES) {
    for (const tool of [...capability.allowedTools, ...capability.defaultTools]) {
      assert.equal(toolNames.has(tool), true, `${capability.value}:${tool}`);
    }
  }
});
